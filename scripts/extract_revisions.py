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
import re
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


# ---------------------------------------------------------------------------
# Word Auto-Numbering Resolver  (w:numPr → visible prefix)
# ---------------------------------------------------------------------------

def _chinese_counting(n: int) -> str:
    """Convert integer to Chinese counting form (一二三...十一...二十一)."""
    digits = "零一二三四五六七八九"
    if n <= 0:
        return str(n)
    if n < 10:
        return digits[n]
    if n == 10:
        return "十"
    if n <= 19:
        return f"十{digits[n % 10]}" if n % 10 else "十"
    if n <= 99:
        t, o = divmod(n, 10)
        return f"{digits[t]}十{digits[o] if o else ''}"
    return str(n)  # > 99 fallback


def _format_num(n: int, num_fmt: str) -> str:
    """Format a number according to a Word numFmt value."""
    if num_fmt in ("decimal", "decimalZero"):
        return str(n)
    if num_fmt in ("chineseCountingThousand", "chineseCounting",
                   "ideographTraditional", "taiwaneseCounting"):
        return _chinese_counting(n)
    if num_fmt == "lowerLetter":
        return chr(ord("a") + n - 1) if 1 <= n <= 26 else str(n)
    if num_fmt == "upperLetter":
        return chr(ord("A") + n - 1) if 1 <= n <= 26 else str(n)
    if num_fmt == "lowerRoman":
        vals = [(1000,"m"),(900,"cm"),(500,"d"),(400,"cd"),(100,"c"),
                (90,"xc"),(50,"l"),(40,"xl"),(10,"x"),(9,"ix"),(5,"v"),(4,"iv"),(1,"i")]
        r = ""
        for v, s in vals:
            while n >= v:
                r += s; n -= v
        return r
    if num_fmt == "upperRoman":
        return _format_num(n, "lowerRoman").upper()
    if num_fmt == "none":
        return ""
    return str(n)


class NumberingResolver:
    """Resolve Word auto-numbering (w:numPr) to visible prefix text.

    Reads word/numbering.xml and tracks sequential counters so that each
    paragraph's numId + ilvl produces the correct rendered prefix
    (e.g. "第一章", "1、", "（1）").
    """

    def __init__(self, zf: zipfile.ZipFile):
        self._levels: dict[str, dict[str, dict]] = {}  # abstractNumId → {ilvl → def}
        self._num_to_abstract: dict[str, str] = {}     # numId → abstractNumId
        self._start_overrides: dict[str, dict[str, int]] = {}  # numId → {ilvl → start}
        self._counters: dict[tuple[str, str], int] = {} # (numId, ilvl) → current count
        self._last_ilvl: dict[str, int] = {}            # numId → last seen ilvl
        self._parse(zf)

    def _parse(self, zf: zipfile.ZipFile) -> None:
        if "word/numbering.xml" not in zf.namelist():
            return
        W = NAMESPACES["w"]
        with zf.open("word/numbering.xml") as f:
            root = ET.parse(f).getroot()

        # Parse abstractNum definitions
        for abst in root.iter(f"{{{W}}}abstractNum"):
            abst_id = abst.get(f"{{{W}}}abstractNumId")
            lvl_map: dict[str, dict] = {}
            for lvl in abst.iter(f"{{{W}}}lvl"):
                ilvl = lvl.get(f"{{{W}}}ilvl")
                start_el = lvl.find(f"w:start", NAMESPACES)
                fmt_el = lvl.find(f"w:numFmt", NAMESPACES)
                txt_el = lvl.find(f"w:lvlText", NAMESPACES)
                suff_el = lvl.find(f"w:suff", NAMESPACES)
                lvl_map[ilvl] = {
                    "start": int(start_el.get(f"{{{W}}}val", "1")) if start_el is not None else 1,
                    "numFmt": fmt_el.get(f"{{{W}}}val", "decimal") if fmt_el is not None else "decimal",
                    "lvlText": txt_el.get(f"{{{W}}}val", "") if txt_el is not None else "",
                    "suff": suff_el.get(f"{{{W}}}val", "tab") if suff_el is not None else "tab",
                }
            self._levels[abst_id] = lvl_map

        # Parse num → abstractNum mappings + overrides
        for num in root.iter(f"{{{W}}}num"):
            num_id = num.get(f"{{{W}}}numId")
            abst_ref = num.find(f"w:abstractNumId", NAMESPACES)
            if abst_ref is not None:
                self._num_to_abstract[num_id] = abst_ref.get(f"{{{W}}}val")
            for ovr in num.iter(f"{{{W}}}lvlOverride"):
                ovr_ilvl = ovr.get(f"{{{W}}}ilvl")
                start_ovr = ovr.find(f"w:startOverride", NAMESPACES)
                if start_ovr is not None:
                    self._start_overrides.setdefault(num_id, {})[ovr_ilvl] = \
                        int(start_ovr.get(f"{{{W}}}val", "1"))

    @staticmethod
    def _is_para_deleted(para: ET.Element) -> bool:
        """True if the entire paragraph is deleted via track changes.

        A paragraph is considered fully deleted when its paragraph mark
        carries ``w:rsidDel`` **and** it contains no surviving ``w:t`` text
        (all content is inside ``w:del`` / ``w:delText``).
        """
        W = NAMESPACES["w"]
        if not para.get(f"{{{W}}}rsidDel"):
            return False
        # Any w:t outside w:del means partial deletion — still alive
        for t in para.iter(f"{{{W}}}t"):
            # Walk ancestors to check if inside w:del
            node = t
            inside_del = False
            while node is not None:
                if node.tag == f"{{{W}}}del":
                    inside_del = True
                    break
                node = node.get("__parent__")  # ET has no parent; use fallback
            if not inside_del:
                return False
        # Fallback: check if *any* plain w:t text exists
        # (ET doesn't track parents, so use a simpler heuristic)
        all_text = "".join((t.text or "") for t in para.iter(f"{{{W}}}t"))
        del_text = "".join((t.text or "") for t in para.iter(f"{{{W}}}delText"))
        return len(all_text) == 0 and len(del_text) > 0

    def resolve(self, para: ET.Element) -> str | None:
        """Return the rendered numbering prefix for a paragraph, or None.

        Paragraphs that are entirely deleted (track changes) are skipped
        without incrementing the counter, matching Word's Final-view
        numbering.
        """
        W = NAMESPACES["w"]
        pPr = para.find(f"w:pPr", NAMESPACES)
        if pPr is None:
            return None
        numPr = pPr.find(f"w:numPr", NAMESPACES)
        if numPr is None:
            return None
        ilvl_el = numPr.find(f"w:ilvl", NAMESPACES)
        numId_el = numPr.find(f"w:numId", NAMESPACES)
        if ilvl_el is None or numId_el is None:
            return None
        ilvl = ilvl_el.get(f"{{{W}}}val", "0")
        num_id = numId_el.get(f"{{{W}}}val", "0")
        if num_id == "0":  # numId 0 = no numbering
            return None

        abst_id = self._num_to_abstract.get(num_id)
        if abst_id is None or abst_id not in self._levels:
            return None
        lvl_def = self._levels[abst_id].get(ilvl)
        if lvl_def is None:
            return None

        # Skip entirely-deleted paragraphs — don't advance counter
        if self._is_para_deleted(para):
            return None

        # Counter management: reset sub-levels when parent advances
        ilvl_int = int(ilvl)
        last = self._last_ilvl.get(num_id, -1)
        if ilvl_int <= last:
            # Parent or same level — reset deeper counters
            for key in list(self._counters):
                if key[0] == num_id and int(key[1]) > ilvl_int:
                    del self._counters[key]
        self._last_ilvl[num_id] = ilvl_int

        # Determine start value
        key = (num_id, ilvl)
        if key not in self._counters:
            start = self._start_overrides.get(num_id, {}).get(ilvl, lvl_def["start"])
            self._counters[key] = start
        else:
            self._counters[key] += 1

        # Format prefix from lvlText template (e.g. "第%1章", "%1、", "（%1）")
        prefix = lvl_def["lvlText"]
        # Replace %1, %2, etc. with formatted numbers
        # %N refers to level N-1's current counter value
        for i in range(9, 0, -1):  # %9 down to %1
            placeholder = f"%{i}"
            if placeholder in prefix:
                target_ilvl = str(i - 1)
                if target_ilvl == ilvl:
                    val = self._counters[key]
                else:
                    val = self._counters.get((num_id, target_ilvl), 1)
                prefix = prefix.replace(placeholder, _format_num(val, lvl_def["numFmt"]))

        # Append suffix separator (tab→space, space→space, nothing→"")
        suff = lvl_def.get("suff", "tab")
        if suff != "nothing":
            prefix += " "

        return prefix


# ---------------------------------------------------------------------------
# Heading heuristic: regex patterns for Chinese/English contract numbering
# ---------------------------------------------------------------------------
_RE_ZHANG = re.compile(r'^第[一二三四五六七八九十百千\d]+章')          # 第X章
_RE_TIAO = re.compile(r'^第[一二三四五六七八九十百千\d]+条')          # 第X条
_RE_CN_ORDINAL = re.compile(r'^[一二三四五六七八九十]{1,3}[、，．.\s]')  # 一、
_RE_CN_PAREN = re.compile(r'^[（(][一二三四五六七八九十]{1,3}[）)]')    # （一）
_RE_ARABIC_ORDINAL = re.compile(r'^\d+[、，．.](?!\d)')      # 1、 2、 1. 2． (but NOT 1.1)
_RE_DECIMAL = re.compile(r'^(\d+(?:\.\d+)+)')                         # 1.1 / 1.1.1
_RE_ARTICLE = re.compile(
    r'^Article\s+\d+',                                      # Article 1 …
    re.IGNORECASE,
)
# English letter / roman / parenthesised numbering
_RE_LETTER_UPPER = re.compile(r'^[A-Z][.．]\s')                       # A. B. C.
_RE_LETTER_LOWER_PAREN = re.compile(r'^\([a-z]\)\s')                 # (a) (b) (c)
_RE_ROMAN_LOWER_PAREN = re.compile(r'^\([ivxlcdm]+\)\s')                  # (i) (ii) (iii)
_RE_ARABIC_PAREN = re.compile(r'^\(\d+\)\s')                       # (1) (2) (3)
_RE_APPENDIX = re.compile(
    r'^(附件[一二三四五六七八九十\d]|附录[一二三四五六七八九十\d]'
    r'|Appendix\s*[A-Z\d]|Schedule\s*[A-Z\d]'
    r'|Annex\s*[A-Z\d]|Exhibit\s*[A-Z\d])',
    re.IGNORECASE,
)


def _scan_doc_patterns(paragraphs: list[dict]) -> dict:
    """First pass: detect which numbering patterns exist in the document.

    Returns a dict of boolean flags used by ``_guess_heading_level`` to
    resolve level ambiguity (e.g. 第X条 is L1 when no 章, L2 when 章 exists).
    """
    pats: dict = {
        "has_zhang": False,           # 第X章
        "has_tiao": False,            # 第X条
        "has_cn_ordinal": False,      # 一、
        "has_arabic_ordinal": False,  # 1、 2、
        "has_cn_paren": False,        # （一）
        "has_decimal": False,         # X.X
        "has_article": False,         # Article X
        "has_letter_upper": False,    # A. B.
        "has_letter_lower_paren": False,  # (a)
        "has_roman_lower_paren": False,   # (i)
        "has_arabic_paren": False,        # (1)
        "has_heading_styles": False,  # Word heading styles
        "has_any_numbering": False,
    }
    for p in paragraphs:
        text = (p.get("text") or "").strip()
        if not text:
            continue
        if p.get("heading_level", 0) > 0:
            pats["has_heading_styles"] = True
        if _RE_ZHANG.match(text):
            pats["has_zhang"] = True
        if _RE_TIAO.match(text):
            pats["has_tiao"] = True
        if _RE_CN_ORDINAL.match(text):
            pats["has_cn_ordinal"] = True
        if _RE_CN_PAREN.match(text):
            pats["has_cn_paren"] = True
        if _RE_ARABIC_ORDINAL.match(text):
            pats["has_arabic_ordinal"] = True
        if _RE_DECIMAL.match(text):
            pats["has_decimal"] = True
        if _RE_ARTICLE.match(text):
            pats["has_article"] = True
        if _RE_LETTER_UPPER.match(text):
            pats["has_letter_upper"] = True
        if _RE_LETTER_LOWER_PAREN.match(text):
            pats["has_letter_lower_paren"] = True
        if _RE_ROMAN_LOWER_PAREN.match(text):
            pats["has_roman_lower_paren"] = True
        if _RE_ARABIC_PAREN.match(text):
            pats["has_arabic_paren"] = True
    pats["has_any_numbering"] = any([
        pats["has_zhang"], pats["has_tiao"],
        pats["has_cn_ordinal"], pats["has_arabic_ordinal"],
        pats["has_decimal"], pats["has_cn_paren"],
        pats["has_article"],
        pats["has_letter_upper"], pats["has_letter_lower_paren"],
        pats["has_roman_lower_paren"], pats["has_arabic_paren"],
    ])
    return pats


def _classify_heading_type(text: str) -> str:
    """Classify a heading text into a type string for ancestor context."""
    if _RE_APPENDIX.match(text):
        return "appendix"
    if _RE_ARTICLE.match(text):
        return "article"
    if _RE_ZHANG.match(text):
        return "zhang"
    if _RE_TIAO.match(text):
        return "tiao"
    if _RE_LETTER_UPPER.match(text):
        return "letter_upper"
    if _RE_LETTER_LOWER_PAREN.match(text):
        return "letter_lower"
    if _RE_ROMAN_LOWER_PAREN.match(text):
        return "roman_lower"
    if _RE_ARABIC_PAREN.match(text):
        return "arabic_paren"
    if _RE_CN_ORDINAL.match(text):
        return "cn_ordinal"
    if _RE_CN_PAREN.match(text):
        return "cn_paren"
    if _RE_DECIMAL.match(text):
        return "decimal"
    if _RE_ARABIC_ORDINAL.match(text):
        return "arabic_ordinal"
    return "other"


def _guess_heading_level(
    text: str,
    fmt: dict,
    doc_pats: dict,
    ancestor_type: str | None = None,
    last_heading_fmt: dict | None = None,
) -> int:
    """Guess heading level from text numbering patterns + visual formatting.

    Rules:
    * Numbered patterns (第X章 / 第X条 / 一、 / （一） / X.X) are always active.
    * English letter / roman / parenthesised patterns use ancestor context
      to resolve nesting depth.
    * Bold-only fallback fires only when the document has NO numbered patterns.
    * Returns 0 for body text, 1-4 for heading levels.
    """
    text = text.strip()
    if not text:
        return 0

    # -- Numbered patterns (always active) --------------------------------

    # 第X章 / Article X → always L1
    if _RE_ZHANG.match(text):
        return 1
    if _RE_ARTICLE.match(text):
        return 1

    # 第X条 → L1 (no 章) / L2 (has 章)
    if _RE_TIAO.match(text):
        return 2 if doc_pats["has_zhang"] else 1

    # 一、 → L1 / L2 / L3 depending on higher patterns
    if _RE_CN_ORDINAL.match(text):
        if doc_pats["has_zhang"] and doc_pats["has_tiao"]:
            return 3
        if doc_pats["has_zhang"] or doc_pats["has_tiao"]:
            return 2
        return 1

    # （一）→ L2 / L3
    if _RE_CN_PAREN.match(text):
        if doc_pats["has_tiao"] or doc_pats["has_cn_ordinal"] or doc_pats["has_arabic_ordinal"]:
            return 3
        return 2

    # X.X / X.X.X → L2 / L3  (count dots for depth)
    m = _RE_DECIMAL.match(text)
    if m:
        dots = m.group(1).count(".")
        base = 3 if (doc_pats["has_zhang"] or doc_pats["has_tiao"]) else 2
        return min(base + dots - 1, 4)

    # 1、 / 2、 (Arabic ordinal + separator) — same level logic as 一、
    if _RE_ARABIC_ORDINAL.match(text):
        if doc_pats["has_zhang"] and doc_pats["has_tiao"]:
            return 3
        if doc_pats["has_zhang"] or doc_pats["has_tiao"]:
            return 2
        return 1

    # -- English letter / roman / parenthesised patterns --------------------
    last_fmt = last_heading_fmt or {}
    curr_indent = fmt.get("indent_left", 0)
    prev_indent = last_fmt.get("indent_left", 0)

    def _indent_deeper() -> bool:
        return curr_indent > prev_indent + 200

    # A. / B. / C.
    if _RE_LETTER_UPPER.match(text):
        if ancestor_type == "appendix":
            return 2
        if ancestor_type == "letter_upper":
            return 2  # sibling
        if ancestor_type in ("letter_lower", "roman_lower", "arabic_paren", "decimal", "cn_paren"):
            return 2  # likely sibling section under same parent (e.g. B. after (g))
        return 1

    # (a) / (b) / (c)  — but NOT single chars that are valid roman numerals
    # when the immediate ancestor is roman_lower at the same indent level.
    if _RE_LETTER_LOWER_PAREN.match(text):
        # Disambiguate: if this single letter is also a valid roman numeral
        # and we're inside a roman sequence, treat it as roman continuation.
        if _RE_ROMAN_LOWER_PAREN.match(text) and ancestor_type == "roman_lower" and not _indent_deeper():
            # Fall through to roman_lower branch below
            pass
        else:
            if ancestor_type in ("letter_upper", "article", "tiao", "decimal", "cn_ordinal", "arabic_ordinal"):
                return 3
            if ancestor_type == "letter_lower":
                return 4 if _indent_deeper() else 3
            if ancestor_type == "roman_lower":
                return 4 if _indent_deeper() else 3
            if ancestor_type in ("appendix",):
                return 2
            return 2

    # (i) / (ii) / (iii) — also catches single-char roman numerals that
    # fell through from the letter_lower branch above.
    if _RE_ROMAN_LOWER_PAREN.match(text):
        if ancestor_type == "letter_lower":
            return 4
        if ancestor_type == "roman_lower":
            return 4
        if ancestor_type in ("letter_upper", "decimal", "cn_paren", "arabic_ordinal"):
            return 3
        return 2

    # (1) / (2) / (3)
    if _RE_ARABIC_PAREN.match(text):
        if ancestor_type in ("letter_lower", "cn_paren"):
            return 4
        if ancestor_type == "arabic_paren":
            return 4
        if ancestor_type in ("letter_upper", "decimal", "cn_ordinal", "arabic_ordinal"):
            return 3
        return 2

    # 附件X / Appendix X → L1 (unless nested under another appendix)
    if _RE_APPENDIX.match(text):
        if ancestor_type == "appendix":
            return 2
        return 1

    # -- Bold fallback (only when NO numbering patterns in whole doc) -----
    if not doc_pats["has_any_numbering"]:
        is_bold = fmt.get("bold", False)
        is_center = fmt.get("align") == "center"
        has_colon = "：" in text or ":" in text
        if is_bold and not is_center and not has_colon and len(text) <= 25:
            return 1

    return 0


def _separate_appendices(clauses: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split clause tree into main body and appendices.

    Only top-level clauses (heading_level == 1) that match appendix patterns
    are treated as document-level appendices. Nested appendices (e.g. an
    Appendix inside a DPA clause) remain in the main tree.
    """
    main: list[dict] = []
    appendices: list[dict] = []
    for clause in clauses:
        title = clause.get("title", "").strip()
        level = clause.get("heading_level", 0)
        if level == 1 and _RE_APPENDIX.match(title):
            appendices.append(clause)
        else:
            main.append(clause)
    return main, appendices


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
    for prefix in ("heading", "标题"):
        if style_lower.startswith(prefix):
            remainder = style_lower[len(prefix):]
            try:
                return int(remainder)
            except ValueError:
                return 1
    return 0


def get_para_formatting(para: ET.Element) -> dict:
    """Extract visual formatting signals from a paragraph element.

    These signals help LLM identify document structure even when
    heading styles are not used (common in Chinese contracts).
    """
    W = NAMESPACES["w"]
    fmt: dict = {}

    pPr = para.find(f"w:pPr", NAMESPACES)
    if pPr is not None:
        # Outline level (0-based; many contracts set this without heading style)
        outlineLvl = pPr.find(f"w:outlineLvl", NAMESPACES)
        if outlineLvl is not None:
            val = outlineLvl.get(f"{{{W}}}val")
            if val is not None:
                fmt["outline_level"] = int(val)

        # Paragraph alignment: center = likely title/chapter heading
        jc = pPr.find(f"w:jc", NAMESPACES)
        if jc is not None:
            fmt["align"] = jc.get(f"{{{W}}}val", "")

        # Left indent in twips — deeper indent = deeper nesting
        ind = pPr.find(f"w:ind", NAMESPACES)
        if ind is not None:
            left = ind.get(f"{{{W}}}left") or ind.get(f"{{{W}}}leftChars")
            if left is not None:
                try:
                    fmt["indent_left"] = int(left)
                except ValueError:
                    pass

    # Run-level: check first run for bold / font size
    first_run = para.find(f"w:r", NAMESPACES)
    if first_run is not None:
        rPr = first_run.find(f"w:rPr", NAMESPACES)
        if rPr is not None:
            b = rPr.find(f"w:b", NAMESPACES)
            if b is not None:
                val = b.get(f"{{{W}}}val", "true")
                fmt["bold"] = val != "false" and val != "0"
            sz = rPr.find(f"w:sz", NAMESPACES)
            if sz is not None:
                val = sz.get(f"{{{W}}}val")
                if val is not None:
                    try:
                        fmt["font_size_half_pt"] = int(val)  # Word stores in half-points
                    except ValueError:
                        pass

    return fmt


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
    """Build a clause tree from flat paragraph list using heading levels.

    Uses a monotonic-stack approach to support arbitrary nesting depth.
    Heading level source: Word heading styles, or outline_level promoted
    during extraction.  Non-heading paragraphs attach to nearest ancestor.
    """
    # Sentinel root at level 0
    root: dict = {
        "heading_level": 0,
        "title": "前言/未分类",
        "para_idx": 0,
        "paragraphs": [],
        "subclauses": [],
    }
    # Stack: list of clause nodes with increasing heading_level
    stack: list[dict] = [root]

    for para in paragraphs:
        level = para.get("heading_level", 0)
        text = (para.get("text") or "").strip()

        if level > 0 and text:
            node: dict = {
                "heading_level": level,
                "title": text,
                "para_idx": para["para_idx"],
                "paragraphs": [para],
                "subclauses": [],
            }
            # Pop stack until we find a parent with smaller level
            while len(stack) > 1 and stack[-1]["heading_level"] >= level:
                stack.pop()
            stack[-1]["subclauses"].append(node)
            stack.append(node)
        else:
            # Body paragraph — attach to current deepest node
            stack[-1]["paragraphs"].append(para)

    # If root has subclauses, return them; otherwise return root itself
    if root["subclauses"]:
        # Move preamble paragraphs (before first heading) into a preamble node
        if root["paragraphs"]:
            preamble = {
                "heading_level": 0,
                "title": "前言/未分类",
                "para_idx": 0,
                "paragraphs": root["paragraphs"],
                "subclauses": [],
            }
            return [preamble] + root["subclauses"]
        return root["subclauses"]
    else:
        return [root]


def attach_location_paths(clauses: list[dict]) -> None:
    """Recursively attach location paths to every revision in the tree.

    Path format: 'Title A > Title B > Title C' with arbitrary depth.
    """

    def _walk(node: dict, parent_path: str) -> None:
        title = node.get("title", "")
        if node.get("heading_level", 0) == 0 and not parent_path:
            current_path = "前言/未分类"
        elif parent_path:
            current_path = f"{parent_path} > {title}" if title else parent_path
        else:
            current_path = title

        for para in node.get("paragraphs", []):
            rev_loc = current_path
            num_prefix = para.get("num_prefix", "")
            if num_prefix and num_prefix.strip():
                prefix = num_prefix.strip()
                if prefix not in current_path:
                    rev_loc = f"{current_path} > {prefix}" if current_path else prefix
            for rev in para.get("revisions", []):
                rev["location"] = rev_loc

        for sub in node.get("subclauses", []):
            _walk(sub, current_path)

    for clause in clauses:
        _walk(clause, "")


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

        # Initialize numbering resolver
        num_resolver = NumberingResolver(zf)

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
                heading_flag = is_heading(style)
                heading_level = get_heading_level(style) if heading_flag else 0
                fmt = get_para_formatting(para)

                # Resolve Word auto-numbering (w:numPr → visible prefix)
                num_prefix = num_resolver.resolve(para)
                if num_prefix and text:
                    text = num_prefix + text

                # Promote outline_level to heading if style didn't mark it
                if not heading_flag and "outline_level" in fmt:
                    heading_flag = True
                    heading_level = fmt["outline_level"] + 1  # 0-based → 1-based

                para_info = {
                    "para_idx": idx,
                    "text": text,
                    "style": style,
                    "is_heading": heading_flag,
                    "heading_level": heading_level,
                }
                if num_prefix:
                    para_info["num_prefix"] = num_prefix
                # Merge formatting signals (only non-empty)
                if fmt:
                    para_info["fmt"] = fmt

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

    # ---- Heading heuristic: enrich paragraphs before building tree ----
    doc_patterns = _scan_doc_patterns(paragraphs)
    last_heading_type = None
    last_heading_fmt: dict = {}
    for para in paragraphs:
        text = (para.get("text") or "").strip()
        if not text:
            continue
        # Update ancestor tracking for already-identified headings
        if para["heading_level"] > 0:
            last_heading_type = _classify_heading_type(text)
            last_heading_fmt = para.get("fmt", {})
            continue
        fmt = para.get("fmt", {})
        guessed = _guess_heading_level(text, fmt, doc_patterns, last_heading_type, last_heading_fmt)
        if guessed > 0:
            para["heading_level"] = guessed
            para["is_heading"] = True
            para["heading_source"] = "heuristic"
            last_heading_type = _classify_heading_type(text)
            last_heading_fmt = fmt
        if _RE_APPENDIX.match(text):
            para["is_appendix_title"] = True

    # Build clause tree and separate appendices
    clauses = build_clause_tree(paragraphs)
    main_clauses, appendices = _separate_appendices(clauses)

    # Aggregate revisions by clause
    def collect_clause_revisions(clause: dict) -> list[dict]:
        revs = []
        for p in clause.get("paragraphs", []):
            revs.extend(p.get("revisions", []))
        for sub in clause.get("subclauses", []):
            revs.extend(collect_clause_revisions(sub))
        return revs

    for clause in main_clauses + appendices:
        clause["revisions"] = collect_clause_revisions(clause)

    # Attach location paths using heading-based clause tree
    attach_location_paths(main_clauses)
    attach_location_paths(appendices)
    for rev in all_revisions:
        rev.setdefault("location", "前言/未分类")

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

    # Extract vendor (Party B) country from contract text
    party_metadata = _extract_party_metadata(paragraphs)

    # Build summary
    summary = {
        "total_paragraphs": len(paragraphs),
        "total_revisions": len(all_revisions),
        "insertions": sum(1 for r in all_revisions if r["type"] == "insertion"),
        "deletions": sum(1 for r in all_revisions if r["type"] == "deletion"),
        "existing": sum(1 for r in all_revisions if r["type"] == "existing"),
        "total_comments": len(comments),
        "total_clauses": len(main_clauses),
        "total_appendices": len(appendices),
        "has_revisions": has_revisions,
        "heading_source": (
            "styles" if doc_patterns["has_heading_styles"]
            else "heuristic" if doc_patterns["has_any_numbering"]
            else "bold_fallback" if any(p.get("heading_source") == "heuristic" for p in paragraphs)
            else "none"
        ),
        "doc_patterns": doc_patterns,
    }

    result = {
        "document": docx_path,
        "summary": summary,
        "paragraphs": paragraphs,
        "clauses": main_clauses,
        "appendices": appendices,
        "ordered_revisions": ordered_revisions,
        "comments": comments,
        "paragraph_comments": para_comments,
        "party_metadata": party_metadata,
    }

    return result


def _extract_party_metadata(paragraphs: list[dict]) -> dict:
    """Extract party metadata (vendor country, names) from contract text.

    Scans the first portion of the document for party identification
    paragraphs and attempts to detect the vendor's (Party B) country.
    """
    country_map = {
        "SG": ["singapore", "新加坡", "pte. ltd.", "pte ltd", "private limited", "pte limited"],
        "HK": ["hong kong", "香港", "hk limited", "hong kong limited"],
        "US": ["united states", "usa", "u.s.", "u.s.a.", "美国", "delaware", "california", "new york", "inc.", "llc", "corporation"],
        "CN": ["china", "中国", "北京", "上海", "广州", "深圳", "广东", "浙江", "江苏", "co., ltd.", "co.,ltd.", "有限责任公司"],
        "UK": ["united kingdom", "uk", "england", "london"],
    }

    # Collect text from first 150 paragraphs (usually covers parties section)
    combined_text = ""
    for para in paragraphs[:150]:
        combined_text += " " + para.get("text", "")
    combined_lower = combined_text.lower()

    # Find Party A marker to help exclude Party A's country from vendor detection
    party_a_markers = ["甲方", "party a", "甲方（", "party a ("]
    party_a_pos = -1
    for marker in party_a_markers:
        pos = combined_lower.find(marker)
        if pos != -1:
            party_a_pos = pos
            break

    # Find Party B marker
    party_b_markers = ["乙方", "party b", "乙方（", "party b ("]
    party_b_pos = -1
    for marker in party_b_markers:
        pos = combined_lower.find(marker)
        if pos != -1:
            party_b_pos = pos
            break

    vendor_country = None

    # Strategy 1: Search in Party B window (up to 600 chars after Party B marker)
    if party_b_pos != -1:
        party_b_window = combined_lower[party_b_pos:party_b_pos + 600]
        for country, keywords in country_map.items():
            for kw in keywords:
                if kw in party_b_window:
                    vendor_country = country
                    break
            if vendor_country:
                break

    # Strategy 2: Fallback — search text after Party A section (exclude Party A's own country)
    if not vendor_country and party_a_pos != -1:
        # Skip Party A's section (approx 600 chars) to reduce false positives
        search_start = party_a_pos + 600
        if search_start < len(combined_lower):
            search_text = combined_lower[search_start:]
            for country, keywords in country_map.items():
                for kw in keywords:
                    if kw in search_text:
                        vendor_country = country
                        break
                if vendor_country:
                    break

    # Strategy 3: Last resort — scan entire text
    if not vendor_country:
        for country, keywords in country_map.items():
            for kw in keywords:
                if kw in combined_lower:
                    vendor_country = country
                    break
            if vendor_country:
                break

    return {
        "vendor_country": vendor_country,
        "vendor_country_detected": vendor_country is not None,
    }


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
