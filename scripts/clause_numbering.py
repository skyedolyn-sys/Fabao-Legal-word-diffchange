#!/usr/bin/env python3
"""
Adaptive Clause Numbering Detection for Chinese Legal Contracts.

Pure-stdlib 3-phase pipeline:
  Phase 1  MarkerExtractor   – regex + numPr + heading signals → markers
  Phase 2  SchemeDiscoverer  – containment analysis → type→level map
  Phase 3  HierarchyBuilder  – monotonic-stack outline tree

Public API:
    parse_outline(paragraphs, xml_root=None) -> dict

CLI:
    python clause_numbering.py <docx_path>
    python clause_numbering.py --learn-from-correction '{...}'
    python clause_numbering.py --show-rules
    python clause_numbering.py --clear-rules
"""
from __future__ import annotations

import json
import os
import re
import sys
import zipfile
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

# ──────────────────────────────────────────────────────────────
# Debug helper
# ──────────────────────────────────────────────────────────────
_DEBUG = os.environ.get("CLAUSE_DEBUG", "") == "1"


def _dbg(*args: Any) -> None:
    if _DEBUG:
        print("[clause_numbering]", *args, file=sys.stderr)


# ──────────────────────────────────────────────────────────────
# PatternType enum – 18 marker types
# ──────────────────────────────────────────────────────────────
class PatternType(str, Enum):
    CHINESE_PIAN = "CHINESE_PIAN"
    CHINESE_CHAPTER = "CHINESE_CHAPTER"
    CHINESE_SECTION = "CHINESE_SECTION"
    CHINESE_ARTICLE = "CHINESE_ARTICLE"
    CHINESE_KUAN = "CHINESE_KUAN"
    CHINESE_XIANG = "CHINESE_XIANG"
    DECIMAL_ARTICLE = "DECIMAL_ARTICLE"
    DECIMAL_4 = "DECIMAL_4"
    DECIMAL_3 = "DECIMAL_3"
    DECIMAL_2 = "DECIMAL_2"
    CHINESE_SINGLE = "CHINESE_SINGLE"
    CHINESE_PAREN = "CHINESE_PAREN"
    DECIMAL_SINGLE = "DECIMAL_SINGLE"
    NUM_PAREN = "NUM_PAREN"
    CIRCLED = "CIRCLED"
    ALPHA = "ALPHA"
    ALPHA_PAREN = "ALPHA_PAREN"
    ROMAN = "ROMAN"


# ──────────────────────────────────────────────────────────────
# Default priority (static fallback)
# ──────────────────────────────────────────────────────────────
DEFAULT_PRIORITY: dict[str, int] = {
    PatternType.CHINESE_PIAN: 0,
    PatternType.CHINESE_CHAPTER: 1,
    PatternType.CHINESE_SECTION: 2,
    PatternType.CHINESE_ARTICLE: 3,
    PatternType.CHINESE_SINGLE: 3,
    PatternType.DECIMAL_ARTICLE: 3,
    PatternType.DECIMAL_2: 4,
    PatternType.CHINESE_PAREN: 4,
    PatternType.CHINESE_KUAN: 4,
    PatternType.DECIMAL_3: 5,
    PatternType.CHINESE_XIANG: 5,
    PatternType.NUM_PAREN: 5,
    PatternType.DECIMAL_SINGLE: 5,
    PatternType.ALPHA: 5,
    PatternType.CIRCLED: 6,
    PatternType.ALPHA_PAREN: 6,
    PatternType.ROMAN: 6,
    PatternType.DECIMAL_4: 6,
}

# ──────────────────────────────────────────────────────────────
# Chinese numeral converter
# ──────────────────────────────────────────────────────────────
_CN_DIGITS = {
    "零": 0, "〇": 0,
    "一": 1, "壹": 1,
    "二": 2, "贰": 2, "两": 2,
    "三": 3, "叁": 3,
    "四": 4, "肆": 4,
    "五": 5, "伍": 5,
    "六": 6, "陆": 6,
    "七": 7, "柒": 7,
    "八": 8, "捌": 8,
    "九": 9, "玖": 9,
    "十": 10, "拾": 10,
    "百": 100, "佰": 100,
    "千": 1000, "仟": 1000,
}


def _chinese_to_int(s: str) -> int:
    """Convert Chinese numeral string to int.

    Handles: 一(1), 十(10), 十二(12), 二十(20), 二十一(21), 一百(100), etc.
    Falls back to int() for Arabic digit strings.
    """
    s = s.strip()
    if not s:
        return 0
    # Pure Arabic digits
    if s.isdigit():
        return int(s)
    # Single character shortcut
    if len(s) == 1 and s in _CN_DIGITS:
        val = _CN_DIGITS[s]
        return 10 if val == 10 else val  # bare 十 = 10

    result = 0
    current = 0
    for ch in s:
        v = _CN_DIGITS.get(ch)
        if v is None:
            continue
        if v >= 10:
            # Multiplier
            if current == 0:
                current = 1  # implicit leading 1 (e.g. 十二 = 12)
            result += current * v
            current = 0
        else:
            current = v
    result += current
    return result


# ──────────────────────────────────────────────────────────────
# Regex patterns – compiled once
# ──────────────────────────────────────────────────────────────
_CN_NUM = r"[零〇一二三四五六七八九十百千壹贰叁肆伍陆柒捌玖拾佰仟两\d]+"
_CIRCLED_CHARS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

PATTERNS: list[tuple[PatternType, re.Pattern]] = [
    # Order matters – more specific first
    (PatternType.CHINESE_PIAN,    re.compile(rf"^第({_CN_NUM})编")),
    (PatternType.CHINESE_CHAPTER, re.compile(rf"^第({_CN_NUM})章")),
    (PatternType.CHINESE_SECTION, re.compile(rf"^第({_CN_NUM})节")),
    (PatternType.DECIMAL_ARTICLE, re.compile(r"^第(\d+\.\d+(?:\.\d+)*)条")),
    (PatternType.CHINESE_ARTICLE, re.compile(rf"^第({_CN_NUM})条")),
    (PatternType.CHINESE_KUAN,    re.compile(rf"^第({_CN_NUM})款")),
    (PatternType.CHINESE_XIANG,   re.compile(rf"^第({_CN_NUM})项")),
    (PatternType.DECIMAL_4,       re.compile(r"^(\d+\.\d+\.\d+\.\d+)(?:\s|[、.]|$)")),
    (PatternType.DECIMAL_3,       re.compile(r"^(\d+\.\d+\.\d+)(?:\s|[、.]|$)")),
    (PatternType.DECIMAL_2,       re.compile(r"^(\d+\.\d+)(?:\s|[、.]|$)")),
    (PatternType.CHINESE_SINGLE,  re.compile(rf"^({_CN_NUM})[、，]\s*")),
    (PatternType.NUM_PAREN,       re.compile(r"^[（(](\d+)[)）]")),
    (PatternType.CHINESE_PAREN,   re.compile(rf"^[（(]({_CN_NUM})[)）]")),
    (PatternType.DECIMAL_SINGLE,  re.compile(r"^(\d+)[.、]\s*")),
    (PatternType.CIRCLED,         re.compile(rf"^([{_CIRCLED_CHARS}])")),
    (PatternType.ALPHA,           re.compile(r"^([a-zA-Z])[.)、]\s*")),
    (PatternType.ALPHA_PAREN,     re.compile(r"^[（(]([a-zA-Z])[)）]")),
    (PatternType.ROMAN,           re.compile(r"^[（(]((?:x{0,3})(?:ix|iv|v?i{0,3}))[)）]", re.IGNORECASE)),
]


# ──────────────────────────────────────────────────────────────
# Phase 1 – MarkerExtractor
# ──────────────────────────────────────────────────────────────
@dataclass
class Marker:
    para_idx: int
    pattern_type: PatternType
    raw_match: str
    ordinal: int  # numeric value of the marker
    source: str   # "numPr" | "heading_style" | "text_pattern"
    confidence: float
    text: str = ""


class MarkerExtractor:
    """Extract numbering markers from paragraphs.

    Signal priority: w:numPr > Heading style > text regex.
    """

    @staticmethod
    def extract_markers(paragraphs: list[dict]) -> list[Optional[Marker]]:
        """Return list parallel to paragraphs; None for non-marker paras."""
        result: list[Optional[Marker]] = []
        for p in paragraphs:
            marker = MarkerExtractor._extract_one(p)
            if marker:
                _dbg(f"  para {p['para_idx']:>4d}  {marker.pattern_type.value:<20s}"
                     f"  ord={marker.ordinal:<4d}  src={marker.source:<14s}"
                     f"  conf={marker.confidence:.2f}  | {p['text'][:60]}")
            result.append(marker)
        return result

    @staticmethod
    def _extract_one(p: dict) -> Optional[Marker]:
        idx = p["para_idx"]
        text = p.get("text", "").lstrip()
        style = p.get("style", "")
        is_heading = p.get("is_heading", False)
        heading_level = p.get("heading_level")
        num_id = p.get("num_id")
        ilvl = p.get("ilvl")

        # Signal 1: w:numPr (highest priority)
        if num_id is not None and ilvl is not None:
            pt, raw, ordinal = MarkerExtractor._match_text(text)
            if pt is not None:
                return Marker(idx, pt, raw, ordinal, "numPr", 1.0, text)
            # Fallback: numPr exists but no visible numbering in text
            # (Word auto-numbering may not appear in <w:t> elements)
            return Marker(idx, PatternType.DECIMAL_SINGLE, f"[ilvl:{ilvl}]", int(ilvl) + 1, "numPr", 0.85, text)

        # Signal 2: Heading style
        if is_heading and heading_level is not None:
            pt, raw, ordinal = MarkerExtractor._match_text(text)
            if pt is not None:
                return Marker(idx, pt, raw, ordinal, "heading_style", 0.95, text)
            # Fallback: heading style exists but no visible numbering in text
            return Marker(idx, PatternType.DECIMAL_SINGLE, f"[H{heading_level}]", heading_level, "heading_style", 0.85, text)

        # Signal 3: text regex
        pt, raw, ordinal = MarkerExtractor._match_text(text)
        if pt is not None:
            return Marker(idx, pt, raw, ordinal, "text_pattern", 0.9, text)

        return None

    @staticmethod
    def _match_text(text: str) -> tuple[Optional[PatternType], str, int]:
        """Match text against all 18 patterns. Return (type, raw, ordinal) or (None, '', 0)."""
        if not text:
            return None, "", 0
        for pt, rx in PATTERNS:
            m = rx.match(text)
            if m:
                raw = m.group(0)
                inner = m.group(1)
                ordinal = MarkerExtractor._to_ordinal(pt, inner)
                return pt, raw, ordinal
        return None, "", 0

    @staticmethod
    def _to_ordinal(pt: PatternType, inner: str) -> int:
        if pt == PatternType.CIRCLED:
            pos = _CIRCLED_CHARS.find(inner)
            return pos + 1 if pos >= 0 else 0
        if pt in (PatternType.ALPHA, PatternType.ALPHA_PAREN):
            ch = inner.lower()
            return ord(ch) - ord("a") + 1 if ch.isalpha() else 0
        if pt == PatternType.ROMAN:
            return _roman_to_int(inner)
        if pt == PatternType.DECIMAL_ARTICLE:
            return 0  # composite – no single ordinal
        if pt in (PatternType.DECIMAL_2, PatternType.DECIMAL_3, PatternType.DECIMAL_4):
            return 0
        return _chinese_to_int(inner)


def _roman_to_int(s: str) -> int:
    s = s.lower().strip()
    vals = {"i": 1, "v": 5, "x": 10}
    total = 0
    prev = 0
    for ch in reversed(s):
        v = vals.get(ch, 0)
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total


# ──────────────────────────────────────────────────────────────
# Phase 2 – SchemeDiscoverer
# ──────────────────────────────────────────────────────────────
class SchemeDiscoverer:
    """Discover type→level mapping via containment analysis."""

    TOLERANCE = 0.10  # 10% violation tolerance

    @classmethod
    def discover(
        cls,
        markers: list[Optional[Marker]],
        paragraphs: list[dict],
    ) -> tuple[dict[str, int], str]:
        """Return (level_map: {PatternType.value: level}, discovery_method)."""
        # Collect positions per type
        positions: dict[str, list[int]] = defaultdict(list)
        for m in markers:
            if m is not None:
                positions[m.pattern_type.value].append(m.para_idx)

        types_present = sorted(positions.keys())
        if not types_present:
            return {}, "empty"

        # Step 1: ilvl ground truth
        ilvl_map: dict[str, int] = cls._ilvl_ground_truth(markers)

        # Step 2: containment matrix
        contains = cls._containment_matrix(positions)

        # Step 3: topological sort → ordering
        topo_order = cls._topo_sort(types_present, contains)

        # Step 4: merge – ilvl > topo > default
        level_map, method = cls._merge(types_present, ilvl_map, topo_order)

        _dbg(f"  SchemeDiscoverer: types={types_present}  method={method}")
        _dbg(f"  level_map = {level_map}")
        return level_map, method

    @classmethod
    def _ilvl_ground_truth(cls, markers: list[Optional[Marker]]) -> dict[str, int]:
        """Extract ilvl values from markers that came from numPr."""
        # We don't have ilvl stored on Marker, but we can look at the para dicts
        # This is called at discover-time so we rely on Marker.source == "numPr"
        # and the associated para's ilvl. We pass-through from caller's paragraphs.
        return {}  # filled by discover_with_paras

    @classmethod
    def discover_with_paras(
        cls,
        markers: list[Optional[Marker]],
        paragraphs: list[dict],
    ) -> tuple[dict[str, int], str]:
        """Full discovery including ilvl extraction from paragraph dicts."""
        positions: dict[str, list[int]] = defaultdict(list)
        for m in markers:
            if m is not None:
                positions[m.pattern_type.value].append(m.para_idx)

        types_present = sorted(positions.keys())
        if not types_present:
            return {}, "empty"

        # ilvl / heading_level ground truth
        ilvl_map: dict[str, int] = {}
        for m, p in zip(markers, paragraphs):
            if m is None:
                continue
            pt_val = m.pattern_type.value
            if m.source == "numPr" and p.get("ilvl") is not None:
                ilvl_val = int(p["ilvl"])
                if pt_val not in ilvl_map:
                    ilvl_map[pt_val] = ilvl_val
            elif m.source == "heading_style" and p.get("heading_level") is not None:
                hl_val = int(p["heading_level"])
                if pt_val not in ilvl_map:
                    ilvl_map[pt_val] = hl_val

        if ilvl_map:
            _dbg(f"  ilvl ground truth: {ilvl_map}")

        # Containment matrix
        contains = cls._containment_matrix(positions)

        # Topo sort
        topo_order = cls._topo_sort(types_present, contains)

        # Merge
        level_map, method = cls._merge(types_present, ilvl_map, topo_order)
        _dbg(f"  SchemeDiscoverer: types={types_present}  method={method}")
        _dbg(f"  level_map = {level_map}")
        return level_map, method

    @classmethod
    def _containment_matrix(
        cls, positions: dict[str, list[int]]
    ) -> dict[tuple[str, str], bool]:
        """For each pair (A, B): does A contain B?

        A contains B iff all B positions fall between consecutive A positions
        (with TOLERANCE % violations allowed).
        """
        contains: dict[tuple[str, str], bool] = {}
        types = list(positions.keys())
        for a in types:
            a_pos = sorted(positions[a])
            if len(a_pos) < 2:
                continue
            for b in types:
                if a == b:
                    continue
                b_pos = sorted(positions[b])
                if not b_pos:
                    continue
                violations = 0
                for bp in b_pos:
                    # Check if bp falls between some consecutive a_pos pair
                    found = False
                    for i in range(len(a_pos) - 1):
                        if a_pos[i] < bp < a_pos[i + 1]:
                            found = True
                            break
                    if not found:
                        violations += 1
                ratio = violations / len(b_pos) if b_pos else 1.0
                contains[(a, b)] = ratio <= cls.TOLERANCE

        if _DEBUG:
            for (a, b), v in contains.items():
                if v:
                    _dbg(f"  containment: {a} ⊃ {b}")
        return contains

    @classmethod
    def _topo_sort(
        cls,
        types: list[str],
        contains: dict[tuple[str, str], bool],
    ) -> list[str]:
        """Kahn's algorithm on containment DAG. Edge A→B means A contains B (A is parent)."""
        adj: dict[str, list[str]] = defaultdict(list)
        in_deg: dict[str, int] = {t: 0 for t in types}

        for (a, b), v in contains.items():
            if v and a in in_deg and b in in_deg:
                adj[a].append(b)
                in_deg[b] += 1

        queue: deque[str] = deque()
        for t in types:
            if in_deg[t] == 0:
                queue.append(t)

        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            _dbg(f"  topo: dequeue {node}")
            for nb in adj[node]:
                in_deg[nb] -= 1
                if in_deg[nb] == 0:
                    queue.append(nb)

        # Append any remaining (cycle members) in default priority order
        remaining = [t for t in types if t not in order]
        remaining.sort(key=lambda t: DEFAULT_PRIORITY.get(PatternType(t), 99))
        order.extend(remaining)
        return order

    @classmethod
    def _merge(
        cls,
        types_present: list[str],
        ilvl_map: dict[str, int],
        topo_order: list[str],
    ) -> tuple[dict[str, int], str]:
        """Merge sources: ilvl > topo > default."""
        level_map: dict[str, int] = {}
        method_parts: list[str] = []

        # Start with default for all present types
        for t in types_present:
            level_map[t] = DEFAULT_PRIORITY.get(PatternType(t), 6)

        has_default_only = True

        # Apply topo ordering (assign levels based on order position)
        if topo_order:
            # Group by topo rank – types at same default level get same rank
            rank = 0
            prev_default = -1
            topo_levels: dict[str, int] = {}
            for t in topo_order:
                dp = DEFAULT_PRIORITY.get(PatternType(t), 6)
                if dp != prev_default:
                    rank = dp  # Align topo rank with default priority scale
                    prev_default = dp
                topo_levels[t] = rank

            # Only override if topo actually differs from default
            for t, lv in topo_levels.items():
                if t in level_map:
                    level_map[t] = lv
            if len(topo_order) > 1:
                method_parts.append("containment")
                has_default_only = False

        # Apply ilvl (highest priority)
        if ilvl_map:
            for t, lv in ilvl_map.items():
                level_map[t] = lv
            method_parts.append("ilvl")
            has_default_only = False

        if has_default_only:
            method_parts.append("default_priority")

        return level_map, "+".join(method_parts) if method_parts else "default_priority"


# ──────────────────────────────────────────────────────────────
# Phase 3 – HierarchyBuilder
# ──────────────────────────────────────────────────────────────
@dataclass
class OutlineNode:
    level: int
    title: str
    para_idx: int
    pattern_type: Optional[str]
    raw_match: str
    confidence: float
    children: list[OutlineNode] = field(default_factory=list)
    paragraphs: list[int] = field(default_factory=list)
    location_path: str = ""

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "title": self.title,
            "para_idx": self.para_idx,
            "pattern_type": self.pattern_type,
            "raw_match": self.raw_match,
            "confidence": self.confidence,
            "children": [c.to_dict() for c in self.children],
            "paragraphs": self.paragraphs,
            "location_path": self.location_path,
        }


class HierarchyBuilder:
    """Build N-level outline tree using monotonic stack."""

    @classmethod
    def build(
        cls,
        markers: list[Optional[Marker]],
        paragraphs: list[dict],
        level_map: dict[str, int],
        max_jump: int = 2,
        discovery_method: str = "default_priority",
    ) -> list[OutlineNode]:
        """Return list of root-level OutlineNode."""
        # Monotonic stack: list of OutlineNode, in increasing level order
        roots: list[OutlineNode] = []
        stack: list[OutlineNode] = []

        for i, (m, p) in enumerate(zip(markers, paragraphs)):
            if m is not None:
                pt_val = m.pattern_type.value
                level = level_map.get(pt_val, DEFAULT_PRIORITY.get(PatternType(pt_val), 6))
                title = p.get("text", "").strip()
                confidence = m.confidence
                if "containment" not in discovery_method and "ilvl" not in discovery_method and "learned" not in discovery_method:
                    # Only penalize confidence when using pure default fallback
                    confidence = min(confidence, 0.7)

                node = OutlineNode(
                    level=level,
                    title=title,
                    para_idx=m.para_idx,
                    pattern_type=pt_val,
                    raw_match=m.raw_match,
                    confidence=confidence,
                )

                # Fix level jumps
                if stack:
                    parent_level = stack[-1].level
                    if level - parent_level > max_jump:
                        cls._insert_placeholders(stack, roots, parent_level, level, m.para_idx)

                # Pop stack entries >= current level
                while stack and stack[-1].level >= level:
                    stack.pop()

                # Attach to parent or root
                if stack:
                    stack[-1].children.append(node)
                else:
                    roots.append(node)

                stack.append(node)
            else:
                # Non-marker paragraph → attach to nearest parent
                if stack:
                    stack[-1].paragraphs.append(p["para_idx"])

        # Generate location paths
        for root in roots:
            cls._assign_paths(root, "")

        return roots

    @classmethod
    def _insert_placeholders(
        cls,
        stack: list[OutlineNode],
        roots: list[OutlineNode],
        parent_level: int,
        target_level: int,
        para_idx: int,
    ) -> None:
        """Insert synthetic placeholder nodes to bridge level gaps > max_jump."""
        for lv in range(parent_level + 1, target_level):
            placeholder = OutlineNode(
                level=lv,
                title="[...]",
                para_idx=para_idx,
                pattern_type=None,
                raw_match="",
                confidence=0.0,
            )
            if stack:
                stack[-1].children.append(placeholder)
            else:
                roots.append(placeholder)
            stack.append(placeholder)

    @classmethod
    def _assign_paths(cls, node: OutlineNode, parent_path: str) -> None:
        # Build this node's segment
        seg = node.raw_match.rstrip() if node.raw_match else node.title
        # Append a brief title excerpt
        title_body = node.title
        if node.raw_match and title_body.startswith(node.raw_match):
            title_body = title_body[len(node.raw_match):].strip()
        if title_body:
            seg = f"{node.raw_match.rstrip()} {title_body[:20]}" if node.raw_match else title_body[:30]

        if parent_path:
            node.location_path = f"{parent_path} > {seg}"
        else:
            node.location_path = seg

        for child in node.children:
            cls._assign_paths(child, node.location_path)


# ──────────────────────────────────────────────────────────────
# LearnedSchemeStore
# ──────────────────────────────────────────────────────────────
@dataclass
class LearnedRule:
    pattern_type: str
    context_pattern: str  # "before_type>pattern_type>after_type"
    correct_level: int
    source_doc: str
    created_at: str
    reasoning: str
    confidence: float
    usage_count: int = 1


class LearnedSchemeStore:
    """Read/write learned rules from rules/learned_schemes.json."""

    def __init__(self, rules_path: Path | None = None) -> None:
        # Path: <script_dir>/../rules/learned_schemes.json
        self._path = rules_path or Path(__file__).resolve().parent.parent / "rules" / "learned_schemes.json"
        self._rules: list[LearnedRule] = []
        self._load()

    def _load(self) -> None:
        self._rules = []
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for r in data.get("rules", []):
                    self._rules.append(LearnedRule(**r))
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"rules": [asdict(r) for r in self._rules]}
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_from_llm_correction(self, correction: dict) -> None:
        """Add rule from LLM correction. Only if user_confirmed=True.

        Expected keys: pattern_type, before_type, after_type, correct_level,
                       source_doc, reasoning, user_confirmed, confidence (optional).
        """
        if not correction.get("user_confirmed", False):
            return

        pt = correction["pattern_type"]
        before = correction.get("before_type", "*")
        after = correction.get("after_type", "*")
        ctx = f"{before}>{pt}>{after}"

        # Dedup: if identical context exists, increment usage_count
        for r in self._rules:
            if r.context_pattern == ctx and r.correct_level == correction["correct_level"]:
                r.usage_count += 1
                self.save()
                return

        rule = LearnedRule(
            pattern_type=pt,
            context_pattern=ctx,
            correct_level=int(correction["correct_level"]),
            source_doc=correction.get("source_doc", ""),
            created_at=datetime.now(timezone.utc).isoformat(),
            reasoning=correction.get("reasoning", ""),
            confidence=float(correction.get("confidence", 0.85)),
        )
        self._rules.append(rule)
        self.save()

    def query(self, pattern_type: str, context_types: tuple[str, str] = ("*", "*")) -> Optional[LearnedRule]:
        """Exact match first, then loose match (ignore after_type with '*')."""
        before, after = context_types
        exact_ctx = f"{before}>{pattern_type}>{after}"
        loose_ctx = f"{before}>{pattern_type}>*"

        # Exact match
        for r in self._rules:
            if r.context_pattern == exact_ctx:
                return r
        # Loose match
        for r in self._rules:
            if r.context_pattern == loose_ctx:
                return r
        return None

    @property
    def rules(self) -> list[LearnedRule]:
        return list(self._rules)

    def clear(self) -> None:
        self._rules = []
        self.save()


# ──────────────────────────────────────────────────────────────
# ConsistencyValidator
# ──────────────────────────────────────────────────────────────
class ConsistencyValidator:
    """上下块一致性校验器：检查编号连续性、层级跳跃、重复编号、父级缺失、格式突变。"""

    MAX_LEVEL_JUMP = 2  # 允许的最大层级跳跃

    def validate(
        self,
        markers: list[Optional[Marker]],
        level_map: dict[str, int],
    ) -> list[dict]:
        issues = []
        valid_markers = [(i, m) for i, m in enumerate(markers) if m is not None]
        if len(valid_markers) < 2:
            return issues

        issues.extend(self._check_ordinal_continuity(valid_markers, level_map))
        issues.extend(self._check_level_jumps(valid_markers, level_map))
        issues.extend(self._check_duplicate_numbers(valid_markers))
        issues.extend(self._check_parent_missing(valid_markers, level_map))
        issues.extend(self._check_format_consistency(valid_markers, level_map))
        return issues

    @staticmethod
    def _parse_numbers(raw: str) -> tuple[int, ...]:
        """从raw_match中提取数字序列。'3.4' -> (3, 4), '第3条' -> (3,)"""
        nums = re.findall(r'\d+', raw)
        if nums:
            return tuple(int(n) for n in nums)
        cn_nums = re.findall(r'[一二三四五六七八九十百千]+', raw)
        if cn_nums:
            return tuple(_chinese_to_int(n) for n in cn_nums)
        return ()

    def _check_ordinal_continuity(self, valid_markers, level_map):
        """检查同类型、同层级的编号连续性。3.1→3.3 缺 3.2 时报异常。"""
        issues = []
        prev_by_type_level = {}

        for idx, m in valid_markers:
            nums = self._parse_numbers(m.raw_match)
            if not nums:
                continue

            pt = m.pattern_type.value
            level = level_map.get(pt, DEFAULT_PRIORITY.get(m.pattern_type, 6))
            key = (pt, level)

            if key in prev_by_type_level:
                prev_m, prev_nums = prev_by_type_level[key]

                if len(nums) == len(prev_nums):
                    gap = nums[-1] - prev_nums[-1]
                    if gap > 1:
                        expected_parts = list(prev_nums[:-1]) + [prev_nums[-1] + 1]
                        expected = '.'.join(str(n) for n in expected_parts)
                        issues.append({
                            "type": "ordinal_gap",
                            "para_idx": m.para_idx,
                            "message": f"{pt} 编号不连续: {prev_m.raw_match} → {m.raw_match} (间隔 {gap-1} 个)",
                            "current": m.raw_match,
                            "expected": expected,
                            "suggestion": "检查文档是否删除了中间条款，或编号识别有误",
                        })

            prev_by_type_level[key] = (m, nums)

        return issues

    def _check_level_jumps(self, valid_markers, level_map):
        """检查相邻marker之间的层级跳跃是否过大。"""
        issues = []
        for i in range(1, len(valid_markers)):
            _, prev_m = valid_markers[i - 1]
            _, curr_m = valid_markers[i]

            prev_level = level_map.get(prev_m.pattern_type.value, DEFAULT_PRIORITY.get(prev_m.pattern_type, 6))
            curr_level = level_map.get(curr_m.pattern_type.value, DEFAULT_PRIORITY.get(curr_m.pattern_type, 6))

            jump = curr_level - prev_level
            if jump > self.MAX_LEVEL_JUMP:
                issues.append({
                    "type": "level_jump",
                    "para_idx": curr_m.para_idx,
                    "message": f"层级跳跃过大: level {prev_level} → {curr_level} (跳跃 {jump})",
                    "current": f"level {curr_level} ({curr_m.raw_match})",
                    "expected": f"level <= {prev_level + self.MAX_LEVEL_JUMP}",
                    "suggestion": f"该标题可能被错误归级，建议核查其应为 level {prev_level + 1} 或 {prev_level + 2}",
                })
            elif jump < -self.MAX_LEVEL_JUMP:
                issues.append({
                    "type": "level_regress",
                    "para_idx": curr_m.para_idx,
                    "message": f"层级大幅回退: level {prev_level} → {curr_level} (回退 {abs(jump)})",
                    "current": f"level {curr_level} ({curr_m.raw_match})",
                    "expected": f"level >= {prev_level - self.MAX_LEVEL_JUMP}",
                    "suggestion": "确认是否为新章节开始，否则可能是归级错误",
                })

        return issues

    def _check_duplicate_numbers(self, valid_markers):
        """检查重复编号。"""
        issues = []
        seen = {}

        for idx, m in valid_markers:
            key = (m.pattern_type.value, m.raw_match)
            if key in seen:
                issues.append({
                    "type": "duplicate_number",
                    "para_idx": m.para_idx,
                    "message": f"重复编号: {m.raw_match} (首次出现在 para {seen[key]})",
                    "current": m.raw_match,
                    "expected": "唯一编号",
                    "suggestion": "检查文档是否有重复条款或编号识别错误",
                })
            else:
                seen[key] = m.para_idx

        return issues

    def _check_parent_missing(self, valid_markers, level_map):
        """检查子级编号是否有对应的父级。如 '3.1' 需要 '3' 或 '第3条'。"""
        issues = []
        all_numbers = {}
        for idx, m in valid_markers:
            nums = self._parse_numbers(m.raw_match)
            level = level_map.get(m.pattern_type.value, DEFAULT_PRIORITY.get(m.pattern_type, 6))
            all_numbers[m.para_idx] = {"nums": nums, "level": level}

        for idx, m in valid_markers:
            nums = self._parse_numbers(m.raw_match)
            level = level_map.get(m.pattern_type.value, DEFAULT_PRIORITY.get(m.pattern_type, 6))

            if len(nums) >= 2:
                parent_nums = nums[:-1]

                has_parent = False
                for info in all_numbers.values():
                    if info["nums"] == parent_nums and info["level"] < level:
                        has_parent = True
                        break

                if not has_parent:
                    parent_str = ".".join(str(n) for n in parent_nums)
                    issues.append({
                        "type": "parent_missing",
                        "para_idx": m.para_idx,
                        "message": f"父级缺失: {m.raw_match} 缺少父级编号 ({parent_str})",
                        "current": m.raw_match,
                        "expected": f"存在父级如 '{parent_str}' 或 '第{parent_nums[0]}条'",
                        "suggestion": f"检查文档是否缺少 '{parent_str}' 级别条款，或该条款应直接改为 '{parent_str}' 级别",
                    })

        return issues

    def _check_format_consistency(self, valid_markers, level_map):
        """检查同层级下格式是否一致。如 level 1 全部应为 CHINESE_ARTICLE，不应混用 DECIMAL_2。"""
        issues = []
        level_types = {}

        for idx, m in valid_markers:
            level = level_map.get(m.pattern_type.value, DEFAULT_PRIORITY.get(m.pattern_type, 6))
            pt = m.pattern_type.value
            if level not in level_types:
                level_types[level] = {}
            level_types[level][pt] = level_types[level].get(pt, 0) + 1

        for level, type_counts in level_types.items():
            if len(type_counts) <= 1:
                continue

            dominant = max(type_counts, key=type_counts.get)
            dominant_count = type_counts[dominant]
            total = sum(type_counts.values())

            # 主要类型占比达到或超过60%时，提示少数类型
            if dominant_count / total >= 0.6:
                for pt, count in type_counts.items():
                    if pt != dominant:
                        # 找到这个异常类型的第一个 marker
                        for idx, m in valid_markers:
                            m_level = level_map.get(m.pattern_type.value, DEFAULT_PRIORITY.get(m.pattern_type, 6))
                            if m.pattern_type.value == pt and m_level == level:
                                issues.append({
                                    "type": "format_inconsistency",
                                    "para_idx": m.para_idx,
                                    "message": f"格式不一致: level {level} 主要使用 {dominant} ({dominant_count}/{total})，但此处使用 {pt}",
                                    "current": f"{pt} ({m.raw_match})",
                                    "expected": dominant,
                                    "suggestion": f"建议统一为 {dominant} 格式，或确认该条款层级是否正确",
                                })
                                break

        return issues


# ──────────────────────────────────────────────────────────────
# Top-level API
# ──────────────────────────────────────────────────────────────
def parse_outline(paragraphs: list[dict], xml_root: Optional[ET.Element] = None) -> dict:
    """Main entry point.

    Args:
        paragraphs: list of dicts with keys:
            para_idx, text, style, is_heading, heading_level,
            num_id (optional), ilvl (optional)
        xml_root: optional xml.etree.ElementTree.Element for w:numPr parsing

    Returns:
        {
            "outline_tree": list[dict],
            "level_map": dict[str, int],
            "para_to_location": dict[int, str],
            "confidence_issues": list[dict],
            "learned_rules_applied": int,
            "scheme_info": {"types_found": list[str], "discovery_method": str},
        }
    """
    _dbg(f"parse_outline: {len(paragraphs)} paragraphs")

    # Phase 1: Extract markers
    markers = MarkerExtractor.extract_markers(paragraphs)

    # Phase 2: Discover scheme
    level_map, method = SchemeDiscoverer.discover_with_paras(markers, paragraphs)

    # Apply learned rules
    store = LearnedSchemeStore()
    learned_applied = 0
    marker_types = [m.pattern_type.value if m else None for m in markers]
    for i, m in enumerate(markers):
        if m is None:
            continue
        # Build context (before_type, after_type)
        before = "*"
        after = "*"
        for j in range(i - 1, -1, -1):
            if marker_types[j] is not None:
                before = marker_types[j]
                break
        for j in range(i + 1, len(marker_types)):
            if marker_types[j] is not None:
                after = marker_types[j]
                break
        rule = store.query(m.pattern_type.value, (before, after))
        if rule is not None:
            _dbg(f"  learned rule hit: {rule.context_pattern} → level {rule.correct_level}")
            level_map[m.pattern_type.value] = rule.correct_level
            learned_applied += 1

    # Phase 3: Build hierarchy
    roots = HierarchyBuilder.build(markers, paragraphs, level_map, discovery_method=method)

    # Collect outputs
    outline_tree = [r.to_dict() for r in roots]
    para_to_location: dict[int, str] = {}

    def _collect_locations(node: OutlineNode) -> None:
        para_to_location[node.para_idx] = node.location_path
        for pi in node.paragraphs:
            para_to_location[pi] = node.location_path
        for child in node.children:
            _collect_locations(child)

    for r in roots:
        _collect_locations(r)

    # Confidence issues
    confidence_issues: list[dict] = []
    for m in markers:
        if m is not None and m.confidence < 0.8:
            confidence_issues.append({
                "para_idx": m.para_idx,
                "pattern_type": m.pattern_type.value,
                "confidence": m.confidence,
                "text": m.text[:80],
            })

    types_found = sorted(set(m.pattern_type.value for m in markers if m is not None))

    # Phase 4: Consistency validation
    consistency_issues = ConsistencyValidator().validate(markers, level_map)

    return {
        "outline_tree": outline_tree,
        "level_map": {k: v for k, v in level_map.items()},
        "para_to_location": {k: v for k, v in para_to_location.items()},
        "confidence_issues": confidence_issues,
        "consistency_issues": consistency_issues,
        "learned_rules_applied": learned_applied,
        "scheme_info": {
            "types_found": types_found,
            "discovery_method": method,
        },
    }


# ──────────────────────────────────────────────────────────────
# Standalone DOCX reader (for CLI mode)
# ──────────────────────────────────────────────────────────────
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _parse_docx(path: str) -> tuple[list[dict], ET.Element]:
    """Read a .docx file and return (paragraphs, xml_root)."""
    with zipfile.ZipFile(path, "r") as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    body = root.find(f"{{{_W_NS}}}body")
    if body is None:
        return [], root

    paragraphs: list[dict] = []
    for i, para in enumerate(body.findall(f"{{{_W_NS}}}p")):
        text_parts: list[str] = []
        for t in para.iter(f"{{{_W_NS}}}t"):
            if t.text:
                text_parts.append(t.text)
        text = "".join(text_parts)

        # Style
        style = ""
        is_heading = False
        heading_level: Optional[int] = None
        ppr = para.find(f"{{{_W_NS}}}pPr")
        if ppr is not None:
            pstyle = ppr.find(f"{{{_W_NS}}}pStyle")
            if pstyle is not None:
                style = pstyle.get(f"{{{_W_NS}}}val", "")
                if style.lower().startswith("heading"):
                    is_heading = True
                    try:
                        heading_level = int(style.replace("Heading", "").replace("heading", "").strip())
                    except ValueError:
                        heading_level = None

        # numPr
        num_id: Optional[str] = None
        ilvl: Optional[int] = None
        if ppr is not None:
            numpr = ppr.find(f"{{{_W_NS}}}numPr")
            if numpr is not None:
                ilvl_el = numpr.find(f"{{{_W_NS}}}ilvl")
                numid_el = numpr.find(f"{{{_W_NS}}}numId")
                if ilvl_el is not None:
                    ilvl = int(ilvl_el.get(f"{{{_W_NS}}}val", "0"))
                if numid_el is not None:
                    num_id = numid_el.get(f"{{{_W_NS}}}val")

        paragraphs.append({
            "para_idx": i,
            "text": text,
            "style": style,
            "is_heading": is_heading,
            "heading_level": heading_level,
            "num_id": num_id,
            "ilvl": ilvl,
        })

    return paragraphs, root


# ──────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────
def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Clause numbering detection for Chinese contracts")
    parser.add_argument("docx_path", nargs="?", help="Path to .docx file")
    parser.add_argument("--learn-from-correction", type=str, help="JSON string with correction data")
    parser.add_argument("--show-rules", action="store_true", help="Show learned rules")
    parser.add_argument("--clear-rules", action="store_true", help="Clear all learned rules")
    args = parser.parse_args()

    store = LearnedSchemeStore()

    if args.show_rules:
        rules = store.rules
        if not rules:
            print("No learned rules.")
        else:
            for i, r in enumerate(rules, 1):
                print(f"  [{i}] {r.context_pattern}  →  level {r.correct_level}"
                      f"  (used {r.usage_count}x, conf={r.confidence:.2f},"
                      f" src={r.source_doc})")
                if r.reasoning:
                    print(f"       reason: {r.reasoning}")
        return

    if args.clear_rules:
        store.clear()
        print("Learned rules cleared.")
        return

    if args.learn_from_correction:
        correction = json.loads(args.learn_from_correction)
        store.add_from_llm_correction(correction)
        print(f"Rule added/updated for {correction.get('pattern_type', '?')}")
        return

    if not args.docx_path:
        parser.print_help()
        sys.exit(1)

    paragraphs, xml_root = _parse_docx(args.docx_path)
    result = parse_outline(paragraphs, xml_root)

    # Pretty-print outline
    print(f"\n{'='*60}")
    print(f"  Clause Outline  ({len(paragraphs)} paragraphs)")
    print(f"  Types found: {result['scheme_info']['types_found']}")
    print(f"  Discovery:   {result['scheme_info']['discovery_method']}")
    print(f"  Level map:   {result['level_map']}")
    print(f"{'='*60}\n")

    def _print_tree(nodes: list[dict], indent: int = 0) -> None:
        for n in nodes:
            prefix = "  " * indent
            conf = f"[{n['confidence']:.1f}]" if n['confidence'] < 1.0 else ""
            title = n["title"][:70]
            print(f"{prefix}{'├─ ' if indent else ''}{title}  {conf}")
            _print_tree(n["children"], indent + 1)

    _print_tree(result["outline_tree"])

    if result["confidence_issues"]:
        print(f"\n⚠ Confidence issues ({len(result['confidence_issues'])}):")
        for ci in result["confidence_issues"]:
            print(f"  para {ci['para_idx']}: {ci['pattern_type']} conf={ci['confidence']:.2f}"
                  f"  | {ci['text'][:50]}")

    if result["learned_rules_applied"]:
        print(f"\n✓ Applied {result['learned_rules_applied']} learned rule(s)")


if __name__ == "__main__":
    _cli()
