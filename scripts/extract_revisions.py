#!/usr/bin/env python3
"""
DOCX Revision Extraction Helper for Kimi法宝

Extracts track changes (w:ins, w:del) and comments from a .docx file.
Outputs structured JSON organized by paragraph and clause hierarchy.

Usage:
    python extract_revisions.py <input.docx> [output.json]

Uses only standard library: zipfile, xml.etree, json
"""

import json
import sys
import zipfile
from xml.etree import ElementTree as ET


# XML namespaces in DOCX
NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
}

# Register namespaces for proper parsing
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def get_text(element: ET.Element) -> str:
    """Extract all text content from an element and its children."""
    text_parts = []
    for t in element.iter(f"{{{NAMESPACES['w']}}}t"):
        if t.text:
            text_parts.append(t.text)
    return "".join(text_parts)


def get_style(element: ET.Element) -> str | None:
    """Get paragraph style (e.g., Heading1, Heading2)."""
    pPr = element.find(f"w:pPr", NAMESPACES)
    if pPr is None:
        return None
    pStyle = pPr.find(f"w:pStyle", NAMESPACES)
    if pStyle is not None:
        return pStyle.get(f"{{{NAMESPACES['w']}}}val")
    return None


def is_heading(style: str | None) -> bool:
    """Check if style is a heading."""
    if style is None:
        return False
    style_lower = style.lower()
    return style_lower.startswith("heading") or style_lower.startswith("标题")


def get_heading_level(style: str | None) -> int:
    """Extract heading level from style name."""
    if style is None:
        return 0
    style_lower = style.lower()
    # Handle Heading1, Heading2, etc.
    for prefix in ("heading", "标题"):
        if style_lower.startswith(prefix):
            remainder = style_lower[len(prefix):]
            try:
                return int(remainder)
            except ValueError:
                return 1
    return 0


def _smart_truncate(text: str, max_len: int, direction: str = "tail") -> str:
    """Truncate text intelligently at sentence boundaries.
    direction='tail': keep the tail (last N chars)
    direction='head': keep the head (first N chars)
    """
    if len(text) <= max_len:
        return text

    if direction == "tail":
        # Find nearest sentence boundary from the cutoff point
        start = len(text) - max_len
        # Look for punctuation within a 20-char window
        window_start = max(0, start - 20)
        window = text[window_start:start + 20]
        for punct in "。；;!！?？":
            idx = window.rfind(punct, 0, 20)
            if idx != -1:
                return text[window_start + idx + 1:]
        return text[start:]
    else:
        # direction == 'head'
        window_end = min(len(text), max_len + 20)
        window = text[max_len - 20:window_end]
        for punct in "。；;!！?？":
            idx = window.find(punct)
            if idx != -1:
                return text[:max_len - 20 + idx + 1]
        return text[:max_len]


def extract_revisions_from_para(para: ET.Element, para_idx: int) -> list[dict]:
    """Extract all revisions (ins/del) from a single paragraph with context."""
    # Step 1: Build ordered segments of the paragraph
    segments = []
    for child in para:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag in ("ins", "del"):
            segments.append({"type": tag, "element": child, "text": get_text(child)})
        else:
            text = get_text(child)
            if text:
                segments.append({"type": "text", "text": text})

    # Step 2: For each revision, compute before/after context
    revisions = []
    pos = 0

    for rev_idx, seg in enumerate(segments):
        if seg["type"] not in ("ins", "del"):
            continue

        # Build before text (everything before this revision)
        before = "".join(s["text"] for s in segments[:rev_idx])

        # Build after text (everything after this revision)
        after = "".join(s["text"] for s in segments[rev_idx + 1:])

        # Full paragraph text with this revision highlighted
        full = before + seg["text"] + after

        child = seg["element"]
        revisions.append({
            "type": "insertion" if seg["type"] == "ins" else "deletion",
            "id": child.get(f"{{{NAMESPACES['w']}}}id"),
            "author": child.get(f"{{{NAMESPACES['w']}}}author"),
            "date": child.get(f"{{{NAMESPACES['w']}}}date"),
            "text": seg["text"],
            "para_idx": para_idx,
            "position_in_para": pos,
            "context": {
                "before": _smart_truncate(before, 100, direction="tail"),
                "after": _smart_truncate(after, 100, direction="head"),
                "full_sentence": full[:300] + ("..." if len(full) > 300 else ""),
            }
        })
        pos += 1

    return revisions


def extract_comments(docx_path: str) -> dict[str, dict]:
    """Extract comments from word/comments.xml."""
    comments_map = {}

    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            if "word/comments.xml" not in zf.namelist():
                return comments_map

            with zf.open("word/comments.xml") as f:
                tree = ET.parse(f)
                root = tree.getroot()

                for comment in root.iter(f"{{{NAMESPACES['w']}}}comment"):
                    cid = comment.get(f"{{{NAMESPACES['w']}}}id")
                    author = comment.get(f"{{{NAMESPACES['w']}}}author")
                    date = comment.get(f"{{{NAMESPACES['w']}}}date")
                    text = get_text(comment)

                    comments_map[cid] = {
                        "id": cid,
                        "author": author,
                        "date": date,
                        "text": text,
                    }
    except Exception:
        pass

    return comments_map


def extract_comment_refs(para: ET.Element) -> list[dict]:
    """Extract comment references from a paragraph."""
    refs = []

    for comment_range_start in para.iter(f"{{{NAMESPACES['w']}}}commentRangeStart"):
        cid = comment_range_start.get(f"{{{NAMESPACES['w']}}}id")
        refs.append({"type": "start", "id": cid})

    for comment_range_end in para.iter(f"{{{NAMESPACES['w']}}}commentRangeEnd"):
        cid = comment_range_end.get(f"{{{NAMESPACES['w']}}}id")
        refs.append({"type": "end", "id": cid})

    for comment_reference in para.iter(f"{{{NAMESPACES['w']}}}commentReference"):
        cid = comment_reference.get(f"{{{NAMESPACES['w']}}}id")
        refs.append({"type": "ref", "id": cid})

    return refs


def build_clause_tree(paragraphs: list[dict]) -> list[dict]:
    """Build a clause tree from flat paragraph list based on heading levels.
    Returns clauses with location paths attached to each paragraph's revisions."""
    clauses = []
    current_clause = None
    current_subclause = None

    for para in paragraphs:
        level = para.get("heading_level", 0)

        if level == 1:
            current_clause = {
                "heading_level": 1,
                "title": para.get("text", ""),
                "para_idx": para["para_idx"],
                "paragraphs": [para],
                "subclauses": [],
            }
            clauses.append(current_clause)
            current_subclause = None
        elif level == 2 and current_clause is not None:
            current_subclause = {
                "heading_level": 2,
                "title": para.get("text", ""),
                "para_idx": para["para_idx"],
                "paragraphs": [para],
                "subclauses": [],
            }
            current_clause["subclauses"].append(current_subclause)
        elif level == 3 and current_subclause is not None:
            subsub = {
                "heading_level": 3,
                "title": para.get("text", ""),
                "para_idx": para["para_idx"],
                "paragraphs": [para],
            }
            current_subclause["subclauses"].append(subsub)
        elif level == 3 and current_clause is not None and current_subclause is None:
            # Level 3 under level 1 directly
            subsub = {
                "heading_level": 3,
                "title": para.get("text", ""),
                "para_idx": para["para_idx"],
                "paragraphs": [para],
            }
            current_clause["subclauses"].append(subsub)
        else:
            # Regular paragraph - attach to current context
            if current_subclause is not None:
                current_subclause["paragraphs"].append(para)
            elif current_clause is not None:
                current_clause["paragraphs"].append(para)
            else:
                # Preamble or unclassified
                if clauses and "paragraphs" in clauses[-1]:
                    clauses[-1]["paragraphs"].append(para)
                else:
                    clauses.append({
                        "heading_level": 0,
                        "title": "前言/未分类",
                        "para_idx": para["para_idx"],
                        "paragraphs": [para],
                        "subclauses": [],
                    })

    return clauses


def attach_location_paths(clauses: list[dict]) -> None:
    """Attach location paths to each revision in the clause tree.
    Location format: '第X条 标题' or '第X条 标题 > 第X.X款 标题'."""

    def _attach_to_clause(clause: dict, parent_path: str = "") -> None:
        clause_title = clause.get("title", "")
        if clause.get("heading_level", 0) == 0:
            current_path = parent_path or "前言/未分类"
        else:
            current_path = clause_title

        for para in clause.get("paragraphs", []):
            for rev in para.get("revisions", []):
                rev["location"] = current_path

        for sub in clause.get("subclauses", []):
            sub_title = sub.get("title", "")
            if current_path and current_path != "前言/未分类":
                sub_path = f"{current_path} > {sub_title}"
            else:
                sub_path = sub_title

            for para in sub.get("paragraphs", []):
                for rev in para.get("revisions", []):
                    rev["location"] = sub_path

            for subsub in sub.get("subclauses", []):
                subsub_title = subsub.get("title", "")
                if sub_path:
                    subsub_path = f"{sub_path} > {subsub_title}"
                else:
                    subsub_path = subsub_title

                for para in subsub.get("paragraphs", []):
                    for rev in para.get("revisions", []):
                        rev["location"] = subsub_path

    for clause in clauses:
        _attach_to_clause(clause)


def docx_has_revisions(docx_path: str) -> bool:
    """Check if the DOCX contains any track changes (w:ins or w:del)."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return False
        with zf.open("word/document.xml") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            body = root.find(f".//w:body", NAMESPACES)
            if body is None:
                return False
            for para in body.iter(f"{{{NAMESPACES['w']}}}p"):
                for child in para:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag in ("ins", "del"):
                        return True
    return False


def extract_existing_from_para(
    para: ET.Element, para_idx: int, prev_text: str = "", next_text: str = ""
) -> dict | None:
    """Extract an 'existing' record from a paragraph in clean (no-track-changes) mode.

    Returns None if the paragraph is empty or is just a heading.
    """
    text = get_text(para)
    if not text or not text.strip():
        return None

    style = get_style(para)
    # Skip pure headings in existing mode - they serve as structure, not content
    if is_heading(style):
        return None

    full = text
    before = _smart_truncate(prev_text, 100, direction="tail") if prev_text else ""
    after = _smart_truncate(next_text, 100, direction="head") if next_text else ""

    return {
        "type": "existing",
        "id": str(para_idx),
        "author": None,
        "date": None,
        "text": text,
        "para_idx": para_idx,
        "position_in_para": 0,
        "context": {
            "before": before,
            "after": after,
            "full_sentence": full[:300] + ("..." if len(full) > 300 else ""),
        }
    }


def _build_fallback_locations(paragraphs: list[dict], existing_loc: dict[int, str]) -> dict[int, str]:
    """当自适应大纲解析失败时，用简单向上查找最近标题/编号段落作为 location。

    策略：
    1. 优先复用 existing_loc 中已有的解析结果
    2. 对未解析的段落，向上遍历找到最近的 heading style 或文本编号段落
    3. 返回完整的 para_idx → location 映射
    """
    import re

    # 常见编号模式（简化版，覆盖中文合同主要格式）
    numbering_patterns = [
        re.compile(r"^第[一二三四五六七八九十百千\d]+条"),          # 第X条
        re.compile(r"^第\d+\.\d+(?:\.\d+)*条"),                  # 第X.X条
        re.compile(r"^\d+\.\d+(?:\.\d+)*"),                      # X.X.X
        re.compile(r"^[一二三四五六七八九十]+[、，.]"),            # 一、
        re.compile(r"^\d+[、，.]"),                               # 1.
        re.compile(r"^[（(]\d+[)）]"),                            # (1)
        re.compile(r"^[（(][一二三四五六七八九十]+[)）]"),        # (一)
    ]

    para_to_loc: dict[int, str] = dict(existing_loc)
    current_loc = "前言/未分类"

    for p in paragraphs:
        idx = p["para_idx"]

        # 如果已有解析结果，复用之
        if idx in para_to_loc and para_to_loc[idx] != "前言/未分类":
            current_loc = para_to_loc[idx]
            continue

        text = p.get("text", "").strip()
        style = p.get("style", "")

        # 判断当前段落是否是标题/编号段落
        is_numbered = False
        for pat in numbering_patterns:
            if pat.match(text):
                is_numbered = True
                break

        is_heading_p = is_heading(style)

        if is_numbered or is_heading_p:
            # 截断过长标题，保留核心信息
            current_loc = text[:80] if len(text) <= 80 else text[:77] + "..."

        para_to_loc[idx] = current_loc

    return para_to_loc


def _outline_to_legacy_clauses(outline_tree: list[dict], paragraphs: list[dict]) -> list[dict]:
    """Convert outline_tree nodes to legacy clause format for backward compatibility.

    Legacy format: {heading_level, title, para_idx, paragraphs: [...], subclauses: [...], revisions: []}
    """
    # Build para lookup
    para_lookup = {p["para_idx"]: p for p in paragraphs}

    def _convert(node: dict, depth: int = 1) -> dict:
        # Gather paragraphs belonging to this node
        owned_paras = []
        # The node's own paragraph
        if node["para_idx"] in para_lookup:
            owned_paras.append(para_lookup[node["para_idx"]])
        # Body paragraphs attached to this node
        for pi in node.get("paragraphs", []):
            if pi in para_lookup:
                owned_paras.append(para_lookup[pi])

        clause = {
            "heading_level": depth,
            "title": node.get("title", ""),
            "para_idx": node.get("para_idx", 0),
            "paragraphs": owned_paras,
            "subclauses": [_convert(c, depth + 1) for c in node.get("children", [])],
            "revisions": [],  # populated later by collect_clause_revisions
        }
        return clause

    # Handle preamble (paragraphs before first outline node)
    clauses = []
    if outline_tree:
        first_idx = outline_tree[0].get("para_idx", 0)
        preamble_paras = [p for p in paragraphs if p["para_idx"] < first_idx]
        if preamble_paras:
            clauses.append({
                "heading_level": 0,
                "title": "前言/未分类",
                "para_idx": 0,
                "paragraphs": preamble_paras,
                "subclauses": [],
                "revisions": [],
            })

    for node in outline_tree:
        clauses.append(_convert(node))

    return clauses


def extract_revisions(docx_path: str) -> dict:
    """Main extraction function.

    Automatically detects whether the document has track changes.
    - If revisions exist: extracts w:ins/w:del as revision records.
    - If no revisions (clean/template mode): extracts each paragraph as an 'existing' record.
    """
    paragraphs = []
    all_revisions = []
    comment_refs_by_para = {}

    # Detect mode
    has_revisions = docx_has_revisions(docx_path)

    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("Invalid DOCX: word/document.xml not found")

        with zf.open("word/document.xml") as f:
            tree = ET.parse(f)
            root = tree.getroot()

            body = root.find(f".//w:body", NAMESPACES)
            if body is None:
                raise ValueError("Invalid DOCX: body element not found")

            all_paras = list(body.iter(f"{{{NAMESPACES['w']}}}p"))

            for idx, para in enumerate(all_paras):
                style = get_style(para)
                text = get_text(para)
                heading_level = get_heading_level(style) if is_heading(style) else 0

                # Extract w:numPr (Word auto-numbering)
                _num_id = None
                _ilvl = None
                _pPr = para.find(f"{{{NAMESPACES['w']}}}pPr", NAMESPACES)
                if _pPr is not None:
                    _numPr = _pPr.find(f"{{{NAMESPACES['w']}}}numPr")
                    if _numPr is not None:
                        _numId_el = _numPr.find(f"{{{NAMESPACES['w']}}}numId")
                        _ilvl_el = _numPr.find(f"{{{NAMESPACES['w']}}}ilvl")
                        if _numId_el is not None:
                            _num_id = _numId_el.get(f"{{{NAMESPACES['w']}}}val")
                        if _ilvl_el is not None:
                            try:
                                _ilvl = int(_ilvl_el.get(f"{{{NAMESPACES['w']}}}val", "0"))
                            except (ValueError, TypeError):
                                pass

                para_info = {
                    "para_idx": idx,
                    "text": text,
                    "style": style,
                    "is_heading": is_heading(style),
                    "heading_level": heading_level,
                    "num_id": _num_id,
                    "ilvl": _ilvl,
                }

                if has_revisions:
                    # Revision mode: extract w:ins / w:del
                    revs = extract_revisions_from_para(para, idx)
                else:
                    # Clean/template mode: extract paragraph as 'existing'
                    prev_text = get_text(all_paras[idx - 1]) if idx > 0 else ""
                    next_text = get_text(all_paras[idx + 1]) if idx < len(all_paras) - 1 else ""
                    existing = extract_existing_from_para(para, idx, prev_text, next_text)
                    revs = [existing] if existing else []

                para_info["revisions"] = revs
                all_revisions.extend(revs)

                # Extract comment references (only in revision mode)
                if has_revisions:
                    crefs = extract_comment_refs(para)
                    if crefs:
                        comment_refs_by_para[str(idx)] = crefs

                paragraphs.append(para_info)

    # Extract comments
    comments = extract_comments(docx_path)

    # Build outline structure using adaptive numbering detection
    from clause_numbering import parse_outline
    outline = parse_outline(paragraphs)

    # Attach location paths to all revisions using para_to_location mapping
    para_to_loc = outline["para_to_location"]

    # Fallback: if outline parsing failed (too few locations mapped),
    # use simple upward lookup to find the nearest heading/numbered paragraph.
    coverage = len(para_to_loc) / len(paragraphs) if paragraphs else 0
    if coverage < 0.3:
        para_to_loc = _build_fallback_locations(paragraphs, para_to_loc)

    for rev in all_revisions:
        rev["location"] = para_to_loc.get(rev["para_idx"], "前言/未分类")

    # Convert outline_tree to legacy clause format for backward compatibility
    clauses = _outline_to_legacy_clauses(outline["outline_tree"], paragraphs)

    # Aggregate revisions by clause
    def collect_clause_revisions(clause: dict) -> list[dict]:
        revs = []
        for p in clause.get("paragraphs", []):
            revs.extend(p.get("revisions", []))
        for sub in clause.get("subclauses", []):
            revs.extend(collect_clause_revisions(sub))
        return revs

    for clause in clauses:
        clause["revisions"] = collect_clause_revisions(clause)

    # Build ordered revisions list sorted by document position (top-to-bottom)
    ordered_revisions = sorted(
        all_revisions,
        key=lambda r: (r["para_idx"], r.get("position_in_para", 0))
    )

    # Map comments to paragraphs
    para_comments = {}
    for para_idx_str, refs in comment_refs_by_para.items():
        para_cids = set()
        for ref in refs:
            if ref["type"] in ("start", "ref"):
                para_cids.add(ref["id"])

        para_comments[para_idx_str] = []
        for cid in para_cids:
            if cid in comments:
                para_comments[para_idx_str].append(comments[cid])

    # Build summary
    summary = {
        "total_paragraphs": len(paragraphs),
        "total_revisions": len(all_revisions),
        "insertions": sum(1 for r in all_revisions if r["type"] == "insertion"),
        "deletions": sum(1 for r in all_revisions if r["type"] == "deletion"),
        "existing": sum(1 for r in all_revisions if r["type"] == "existing"),
        "total_comments": len(comments),
        "total_clauses": len(clauses),
        "has_revisions": has_revisions,
    }

    result = {
        "document": docx_path,
        "summary": summary,
        "paragraphs": paragraphs,
        "clauses": clauses,
        "ordered_revisions": ordered_revisions,
        "comments": comments,
        "paragraph_comments": para_comments,
        "outline": {
            "tree": outline["outline_tree"],
            "level_map": outline["level_map"],
            "scheme_info": outline["scheme_info"],
            "confidence_issues": outline["confidence_issues"],
            "consistency_issues": outline.get("consistency_issues", []),
            "learned_rules_applied": outline["learned_rules_applied"],
        },
    }

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_revisions.py <input.docx> [output.json]")
        sys.exit(1)

    docx_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    result = extract_revisions(docx_path)

    json_output = json.dumps(result, ensure_ascii=False, indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"Output written to: {output_path}")
    else:
        print(json_output)


if __name__ == "__main__":
    main()
