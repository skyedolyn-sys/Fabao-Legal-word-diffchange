#!/usr/bin/env python3
"""Comprehensive unit tests for clause_numbering.py."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from clause_numbering import (
    HierarchyBuilder,
    LearnedSchemeStore,
    Marker,
    MarkerExtractor,
    OutlineNode,
    PatternType,
    SchemeDiscoverer,
    _chinese_to_int,
    parse_outline,
)


# ──────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────
def make_para(idx: int, text: str, **kwargs) -> dict:
    """Build a paragraph dict with sensible defaults."""
    return {
        "para_idx": idx,
        "text": text,
        "style": kwargs.get("style", None),
        "is_heading": kwargs.get("is_heading", False),
        "heading_level": kwargs.get("heading_level", None),
        **{k: v for k, v in kwargs.items() if k not in ("style", "is_heading", "heading_level")},
    }


def _extract_one(text: str, **para_kw) -> Optional[Marker]:
    """Shorthand: extract marker from a single paragraph."""
    paras = [make_para(0, text, **para_kw)]
    return MarkerExtractor.extract_markers(paras)[0]


# ──────────────────────────────────────────────────────────────
# TestChineseToInt
# ──────────────────────────────────────────────────────────────
class TestChineseToInt:
    def test_single_digits(self):
        assert _chinese_to_int("一") == 1
        assert _chinese_to_int("二") == 2
        assert _chinese_to_int("九") == 9

    def test_ten(self):
        assert _chinese_to_int("十") == 10

    def test_teens(self):
        assert _chinese_to_int("十二") == 12
        assert _chinese_to_int("十九") == 19

    def test_tens(self):
        assert _chinese_to_int("二十") == 20
        assert _chinese_to_int("三十") == 30

    def test_compound(self):
        assert _chinese_to_int("二十一") == 21
        assert _chinese_to_int("九十九") == 99

    def test_arabic_passthrough(self):
        assert _chinese_to_int("42") == 42
        assert _chinese_to_int("0") == 0

    def test_empty_and_whitespace(self):
        assert _chinese_to_int("") == 0
        assert _chinese_to_int("  ") == 0

    def test_hundred(self):
        assert _chinese_to_int("一百") == 100
        assert _chinese_to_int("二百") == 200

    def test_formal_digits(self):
        assert _chinese_to_int("壹") == 1
        assert _chinese_to_int("贰") == 2
        assert _chinese_to_int("拾") == 10

    def test_liang(self):
        assert _chinese_to_int("两") == 2


# ──────────────────────────────────────────────────────────────
# TestMarkerExtractor
# ──────────────────────────────────────────────────────────────
class TestMarkerExtractor:
    """Test all 18 pattern types, priority, whitespace, and None cases."""

    # ── Pattern recognition ─────────────────────────────────
    def test_chinese_pian(self):
        m = _extract_one("第一编 总则")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_PIAN
        assert m.ordinal == 1

    def test_chinese_chapter(self):
        m = _extract_one("第二章 合同标的")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_CHAPTER
        assert m.ordinal == 2

    def test_chinese_section(self):
        m = _extract_one("第三节 服务内容")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_SECTION
        assert m.ordinal == 3

    def test_chinese_article(self):
        m = _extract_one("第四条 定义与解释")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_ARTICLE
        assert m.ordinal == 4

    def test_decimal_article(self):
        m = _extract_one("第1.2条 服务费用")
        assert m is not None
        assert m.pattern_type == PatternType.DECIMAL_ARTICLE
        assert m.ordinal == 0  # composite – no single ordinal

    def test_chinese_kuan(self):
        m = _extract_one("第一款 付款方式")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_KUAN
        assert m.ordinal == 1

    def test_chinese_xiang(self):
        m = _extract_one("第二项 违约责任")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_XIANG
        assert m.ordinal == 2

    def test_decimal_4(self):
        m = _extract_one("1.2.3.4 详细条款")
        assert m is not None
        assert m.pattern_type == PatternType.DECIMAL_4

    def test_decimal_3(self):
        m = _extract_one("1.2.3 子条款")
        assert m is not None
        assert m.pattern_type == PatternType.DECIMAL_3

    def test_decimal_2(self):
        m = _extract_one("1.1 本合同所称")
        assert m is not None
        assert m.pattern_type == PatternType.DECIMAL_2

    def test_chinese_single(self):
        m = _extract_one("一、甲方权利义务")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_SINGLE
        assert m.ordinal == 1

    def test_chinese_paren(self):
        m = _extract_one("（一）总则")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_PAREN
        assert m.ordinal == 1

    def test_chinese_paren_halfwidth(self):
        m = _extract_one("(二)定义")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_PAREN
        assert m.ordinal == 2

    def test_num_paren(self):
        m = _extract_one("(1) 合同解释")
        assert m is not None
        assert m.pattern_type == PatternType.NUM_PAREN
        assert m.ordinal == 1

    def test_num_paren_fullwidth(self):
        m = _extract_one("（3）保密义务")
        assert m is not None
        assert m.pattern_type == PatternType.NUM_PAREN
        assert m.ordinal == 3

    def test_decimal_single(self):
        m = _extract_one("1. 概述")
        assert m is not None
        assert m.pattern_type == PatternType.DECIMAL_SINGLE

    def test_circled(self):
        m = _extract_one("①甲方应当")
        assert m is not None
        assert m.pattern_type == PatternType.CIRCLED
        assert m.ordinal == 1

    def test_circled_high(self):
        m = _extract_one("⑩第十项")
        assert m is not None
        assert m.pattern_type == PatternType.CIRCLED
        assert m.ordinal == 10

    def test_alpha(self):
        m = _extract_one("a. 第一小节")
        assert m is not None
        assert m.pattern_type == PatternType.ALPHA
        assert m.ordinal == 1

    def test_alpha_paren(self):
        m = _extract_one("(a) definitions")
        assert m is not None
        assert m.pattern_type == PatternType.ALPHA_PAREN
        assert m.ordinal == 1

    def test_alpha_paren_fullwidth(self):
        m = _extract_one("（b）scope of work")
        assert m is not None
        assert m.pattern_type == PatternType.ALPHA_PAREN
        assert m.ordinal == 2

    def test_roman(self):
        m = _extract_one("(iii) some clause")
        assert m is not None
        assert m.pattern_type == PatternType.ROMAN
        assert m.ordinal == 3

    # ── Source priority ─────────────────────────────────────
    def test_numPr_priority(self):
        m = _extract_one("第一条 定义", num_id="1", ilvl=0)
        assert m is not None
        assert m.source == "numPr"
        assert m.confidence == 1.0

    def test_heading_style_priority(self):
        m = _extract_one("第一条 定义", is_heading=True, heading_level=1)
        assert m is not None
        assert m.source == "heading_style"
        assert m.confidence == 0.95

    def test_text_pattern_fallback(self):
        m = _extract_one("第一条 定义")
        assert m is not None
        assert m.source == "text_pattern"
        assert m.confidence == 0.9

    def test_numPr_beats_heading(self):
        """numPr + heading both present: numPr wins."""
        m = _extract_one("第一条 定义", num_id="1", ilvl=0, is_heading=True, heading_level=1)
        assert m.source == "numPr"

    # ── None / edge cases ───────────────────────────────────
    def test_plain_paragraph_returns_none(self):
        m = _extract_one("这是一段普通文本，不包含编号。")
        assert m is None

    def test_empty_paragraph_returns_none(self):
        m = _extract_one("")
        assert m is None

    def test_leading_whitespace_stripped(self):
        m = _extract_one("   第一条 定义")
        assert m is not None
        assert m.pattern_type == PatternType.CHINESE_ARTICLE

    def test_parallel_list_matches_input_length(self):
        paras = [
            make_para(0, "第一章 总则"),
            make_para(1, "普通段落"),
            make_para(2, "第一条 定义"),
        ]
        markers = MarkerExtractor.extract_markers(paras)
        assert len(markers) == 3
        assert markers[0] is not None
        assert markers[1] is None
        assert markers[2] is not None

    def test_marker_text_field(self):
        m = _extract_one("第一条 定义与解释")
        assert m is not None
        assert "定义与解释" in m.text


# ──────────────────────────────────────────────────────────────
# TestSchemeDiscoverer
# ──────────────────────────────────────────────────────────────
class TestSchemeDiscoverer:
    """Test scheme discovery for different contract styles."""

    @staticmethod
    def _make_markers_and_paras(specs: list[tuple[int, str]]):
        """Build (markers, paragraphs) from [(para_idx, text), ...]
        with filler plain paragraphs between them.
        """
        max_idx = max(idx for idx, _ in specs) if specs else 0
        paragraphs = [make_para(i, f"filler {i}") for i in range(max_idx + 1)]
        for idx, text in specs:
            paragraphs[idx] = make_para(idx, text)
        markers = MarkerExtractor.extract_markers(paragraphs)
        return markers, paragraphs

    def test_tech_service_contract(self):
        """第一章 → 第一条 → 1.1 → (1) → ①"""
        specs = [
            (0, "第一章 总则"),
            (3, "第一条 定义"),
            (5, "1.1 本合同所称"),
            (8, "(1) 甲方指"),
            (10, "①甲方应当"),
            (12, "第二章 服务内容"),
            (15, "第二条 服务范围"),
            (17, "2.1 乙方提供"),
        ]
        markers, paras = self._make_markers_and_paras(specs)
        level_map, method = SchemeDiscoverer.discover(markers, paras)

        # Chapter should be parent of Article
        assert level_map["CHINESE_CHAPTER"] < level_map["CHINESE_ARTICLE"]
        # Article should be parent of DECIMAL_2
        assert level_map["CHINESE_ARTICLE"] < level_map["DECIMAL_2"]
        # DECIMAL_2 should be parent of NUM_PAREN
        assert level_map["DECIMAL_2"] < level_map["NUM_PAREN"]
        # NUM_PAREN should be parent of or equal to CIRCLED
        assert level_map["NUM_PAREN"] <= level_map["CIRCLED"]

    def test_simple_business_contract(self):
        """一、 → （一） → (1)"""
        specs = [
            (0, "一、甲方权利义务"),
            (2, "（一）甲方有权"),
            (4, "(1) 检查权"),
            (6, "二、乙方权利义务"),
            (8, "（二）乙方有权"),
        ]
        markers, paras = self._make_markers_and_paras(specs)
        level_map, method = SchemeDiscoverer.discover(markers, paras)

        assert level_map["CHINESE_SINGLE"] < level_map["CHINESE_PAREN"]
        assert level_map["CHINESE_PAREN"] < level_map["NUM_PAREN"]

    def test_english_esa_contract(self):
        """1.1 → (a) → 2.1 → (a) → (b)"""
        specs = [
            (0, "1.1 Definitions"),
            (2, "(a) definitions of terms"),
            (5, "2.1 Scope of Services"),
            (7, "(a) core services"),
            (8, "(b) optional services"),
        ]
        markers, paras = self._make_markers_and_paras(specs)
        level_map, method = SchemeDiscoverer.discover(markers, paras)

        assert level_map["DECIMAL_2"] < level_map["ALPHA_PAREN"]

    def test_single_type_document(self):
        """Only CHINESE_ARTICLE throughout → level_map still has it."""
        specs = [
            (0, "第一条 合同主体"),
            (3, "第二条 服务内容"),
            (6, "第三条 服务费用"),
        ]
        markers, paras = self._make_markers_and_paras(specs)
        level_map, method = SchemeDiscoverer.discover(markers, paras)

        assert "CHINESE_ARTICLE" in level_map

    def test_empty_markers(self):
        """All None markers → empty level_map."""
        paras = [make_para(0, "plain text"), make_para(1, "more text")]
        markers = MarkerExtractor.extract_markers(paras)
        level_map, method = SchemeDiscoverer.discover(markers, paras)

        assert level_map == {}
        assert method == "empty"


# ──────────────────────────────────────────────────────────────
# TestHierarchyBuilder
# ──────────────────────────────────────────────────────────────
class TestHierarchyBuilder:
    """Test tree building, orphan attachment, and location paths."""

    @staticmethod
    def _quick_build(specs, level_map, discovery_method="containment"):
        """Build tree from (idx, text) specs and a provided level_map."""
        max_idx = max(idx for idx, _ in specs) if specs else 0
        paragraphs = [make_para(i, f"filler {i}") for i in range(max_idx + 1)]
        for idx, text in specs:
            paragraphs[idx] = make_para(idx, text)
        markers = MarkerExtractor.extract_markers(paragraphs)
        return HierarchyBuilder.build(markers, paragraphs, level_map, discovery_method=discovery_method)

    def test_n_level_tree(self):
        """Build a 4-level tree and verify nesting."""
        specs = [
            (0, "第一章 总则"),
            (1, "第一条 定义"),
            (2, "1.1 甲方"),
            (3, "(1) 包括"),
            (5, "第二条 范围"),
        ]
        level_map = {
            "CHINESE_CHAPTER": 1,
            "CHINESE_ARTICLE": 3,
            "DECIMAL_2": 4,
            "NUM_PAREN": 5,
        }
        roots = self._quick_build(specs, level_map)

        # One root: 第一章
        assert len(roots) == 1
        root = roots[0]
        assert root.pattern_type == "CHINESE_CHAPTER"
        assert root.level == 1

        # Children of 第一章: 第一条 and 第二条
        assert len(root.children) == 2
        art1 = root.children[0]
        assert art1.pattern_type == "CHINESE_ARTICLE"
        assert art1.level == 3

        # Children of 第一条: 1.1
        assert len(art1.children) == 1
        dec = art1.children[0]
        assert dec.pattern_type == "DECIMAL_2"

        # Children of 1.1: (1)
        assert len(dec.children) == 1
        np = dec.children[0]
        assert np.pattern_type == "NUM_PAREN"

    def test_orphan_paragraphs(self):
        """Non-marker paragraphs attached to the nearest parent on stack."""
        specs = [
            (0, "第一条 定义"),
            (1, "这是定义的内容"),   # plain – should attach to 第一条
            (2, "详细说明如下"),     # plain – should attach to 第一条
            (3, "第二条 服务"),
        ]
        level_map = {"CHINESE_ARTICLE": 3}
        roots = self._quick_build(specs, level_map)

        # 第一条 should own paras 1, 2
        art1 = roots[0]
        assert 1 in art1.paragraphs
        assert 2 in art1.paragraphs

    def test_location_paths(self):
        """Verify '>' separated path format."""
        specs = [
            (0, "第一章 总则"),
            (1, "第一条 定义"),
            (2, "1.1 甲方指"),
        ]
        level_map = {
            "CHINESE_CHAPTER": 1,
            "CHINESE_ARTICLE": 3,
            "DECIMAL_2": 4,
        }
        roots = self._quick_build(specs, level_map)

        # Walk to deepest node
        chapter = roots[0]
        article = chapter.children[0]
        decimal = article.children[0]

        # Each path should contain '>'
        assert ">" in decimal.location_path
        # Path should include parent segments
        assert "第一章" in decimal.location_path
        assert "第一条" in decimal.location_path

    def test_multiple_roots(self):
        """Two chapters at the same level → two roots."""
        specs = [
            (0, "第一章 总则"),
            (3, "第二章 服务"),
        ]
        level_map = {"CHINESE_CHAPTER": 1}
        roots = self._quick_build(specs, level_map)
        assert len(roots) == 2

    def test_to_dict(self):
        """OutlineNode.to_dict() returns all expected keys."""
        specs = [(0, "第一条 定义")]
        level_map = {"CHINESE_ARTICLE": 3}
        roots = self._quick_build(specs, level_map)

        d = roots[0].to_dict()
        for key in ("level", "title", "para_idx", "pattern_type",
                     "raw_match", "confidence", "children", "paragraphs",
                     "location_path"):
            assert key in d


# ──────────────────────────────────────────────────────────────
# TestLearnedSchemeStore
# ──────────────────────────────────────────────────────────────
class TestLearnedSchemeStore:
    """Test add, query, dedup/strengthen, persistence, user_confirmed gate."""

    def _correction(self, **overrides) -> dict:
        base = {
            "pattern_type": "NUM_PAREN",
            "before_type": "DECIMAL_2",
            "after_type": "CIRCLED",
            "correct_level": 5,
            "source_doc": "test.docx",
            "reasoning": "test reason",
            "user_confirmed": True,
        }
        base.update(overrides)
        return base

    def test_add_and_query(self, tmp_path: Path):
        store = LearnedSchemeStore(rules_path=tmp_path / "rules.json")
        store.add_from_llm_correction(self._correction())

        rule = store.query("NUM_PAREN", ("DECIMAL_2", "CIRCLED"))
        assert rule is not None
        assert rule.correct_level == 5
        assert rule.pattern_type == "NUM_PAREN"

    def test_query_no_match(self, tmp_path: Path):
        store = LearnedSchemeStore(rules_path=tmp_path / "rules.json")
        assert store.query("ALPHA", ("*", "*")) is None

    def test_user_confirm_required(self, tmp_path: Path):
        store = LearnedSchemeStore(rules_path=tmp_path / "rules.json")
        store.add_from_llm_correction(self._correction(user_confirmed=False))

        assert len(store.rules) == 0
        assert store.query("NUM_PAREN", ("DECIMAL_2", "CIRCLED")) is None

    def test_duplicate_strengthens(self, tmp_path: Path):
        store = LearnedSchemeStore(rules_path=tmp_path / "rules.json")
        store.add_from_llm_correction(self._correction())
        store.add_from_llm_correction(self._correction())

        assert len(store.rules) == 1
        assert store.rules[0].usage_count == 2

    def test_persistence(self, tmp_path: Path):
        rules_file = tmp_path / "rules.json"
        store1 = LearnedSchemeStore(rules_path=rules_file)
        store1.add_from_llm_correction(self._correction())
        assert rules_file.exists()

        # Re-open from disk
        store2 = LearnedSchemeStore(rules_path=rules_file)
        assert len(store2.rules) == 1
        rule = store2.query("NUM_PAREN", ("DECIMAL_2", "CIRCLED"))
        assert rule is not None
        assert rule.correct_level == 5

    def test_clear(self, tmp_path: Path):
        store = LearnedSchemeStore(rules_path=tmp_path / "rules.json")
        store.add_from_llm_correction(self._correction())
        assert len(store.rules) == 1
        store.clear()
        assert len(store.rules) == 0

    def test_loose_match(self, tmp_path: Path):
        """Query with mismatched after_type falls back to wildcard match."""
        store = LearnedSchemeStore(rules_path=tmp_path / "rules.json")
        # Add rule with wildcard after_type
        store.add_from_llm_correction(self._correction(after_type="*"))

        rule = store.query("NUM_PAREN", ("DECIMAL_2", "ANYTHING"))
        assert rule is not None
        assert rule.correct_level == 5


# ──────────────────────────────────────────────────────────────
# TestParseOutline
# ──────────────────────────────────────────────────────────────
class TestParseOutline:
    """Integration tests for the full parse_outline pipeline."""

    def test_full_pipeline_chinese(self):
        """4-level Chinese contract end-to-end."""
        paras = [
            make_para(0, "第一章 总则"),
            make_para(1, "本合同由甲乙双方签订"),
            make_para(2, "第一条 定义"),
            make_para(3, "1.1 甲方"),
            make_para(4, "(1) 指注册公司"),
            make_para(5, "第二章 服务内容"),
            make_para(6, "第二条 服务范围"),
            make_para(7, "2.1 乙方提供"),
        ]
        result = parse_outline(paras)

        assert "outline_tree" in result
        assert "level_map" in result
        assert "para_to_location" in result
        assert "confidence_issues" in result
        assert "learned_rules_applied" in result
        assert "scheme_info" in result

        assert len(result["outline_tree"]) >= 1
        assert result["scheme_info"]["types_found"]

        # para_to_location should have entries
        assert len(result["para_to_location"]) > 0

    def test_full_pipeline_english(self):
        """2-level English contract."""
        paras = [
            make_para(0, "1.1 Definitions"),
            make_para(1, "(a) Client means the party"),
            make_para(2, "(b) Provider means the other"),
            make_para(3, "2.1 Scope of Services"),
            make_para(4, "(a) core services as described"),
        ]
        result = parse_outline(paras)

        assert len(result["outline_tree"]) >= 1
        assert "DECIMAL_2" in result["scheme_info"]["types_found"]
        assert "ALPHA_PAREN" in result["scheme_info"]["types_found"]

    def test_empty_document(self):
        """Empty paragraph list."""
        result = parse_outline([])

        assert result["outline_tree"] == []
        assert result["level_map"] == {}
        assert result["para_to_location"] == {}
        assert result["confidence_issues"] == []
        assert result["learned_rules_applied"] == 0
        assert result["scheme_info"]["discovery_method"] == "empty"

    def test_no_markers_document(self):
        """Document with only plain paragraphs → no tree."""
        paras = [
            make_para(0, "这是一份备忘录。"),
            make_para(1, "主要内容如下所述。"),
            make_para(2, "以上。"),
        ]
        result = parse_outline(paras)

        assert result["outline_tree"] == []
        assert result["level_map"] == {}

    def test_para_to_location_coverage(self):
        """Every marker paragraph should appear in para_to_location."""
        paras = [
            make_para(0, "第一条 定义"),
            make_para(1, "内容段落"),
            make_para(2, "第二条 服务"),
        ]
        result = parse_outline(paras)

        # Both marker paras should be mapped
        assert 0 in result["para_to_location"]
        assert 2 in result["para_to_location"]

    def test_scheme_info_structure(self):
        """scheme_info has expected keys."""
        paras = [make_para(0, "第一条 定义")]
        result = parse_outline(paras)

        info = result["scheme_info"]
        assert "types_found" in info
        assert "discovery_method" in info
        assert isinstance(info["types_found"], list)
