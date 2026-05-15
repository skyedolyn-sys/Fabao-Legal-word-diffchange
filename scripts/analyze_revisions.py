#!/usr/bin/env python3
"""
Kimi法宝 — 合同修订分析引擎

基于 extract_revisions.py 提取的原始修订数据，应用规则库进行：
1. 条款类型自动分类
2. 初步风险等级标记
3. 关联修订聚类

Usage:
    python analyze_revisions.py <input.docx> [output.json]

Uses only standard library: json, os, sys, re, pathlib
"""

import json
import os
import re
import sys
from pathlib import Path

# Import extraction module (same directory)
from extract_revisions import extract_revisions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_rules_dir(playbook: str | None = None) -> Path:
    """Locate the rules/ directory.

    If playbook is specified, returns the playbook subdirectory
    (e.g., rules/playbooks/nda/).

    Resolution order:
    1. KIMI_FABAO_RULES environment variable
    2. Standard relative path (../rules from scripts/)
    3. Current working directory (./rules)
    4. Common installation paths
    """
    # 1. Environment variable override
    env_path = os.environ.get("KIMI_FABAO_RULES")
    if env_path:
        p = Path(env_path)
        if p.exists():
            if playbook:
                pb = p / "playbooks" / playbook
                if pb.exists():
                    return pb
            return p

    # 2. Standard relative path
    script_dir = Path(__file__).resolve().parent
    rules_dir = script_dir.parent / "rules"
    if rules_dir.exists():
        if playbook:
            pb = rules_dir / "playbooks" / playbook
            if pb.exists():
                return pb
            # Playbook specified but not found — warn and fall back to base rules
            print(f"Warning: Playbook '{playbook}' not found. Using base rules.", file=sys.stderr)
        return rules_dir

    # 3. Current working directory
    cwd_rules = Path.cwd() / "rules"
    if cwd_rules.exists():
        if playbook:
            pb = cwd_rules / "playbooks" / playbook
            if pb.exists():
                return pb
        return cwd_rules

    # 4. Common installation paths
    home = Path.home()
    common_paths = [
        home / ".claude" / "skills" / "kimi-fabao" / "rules",
        home / ".local" / "share" / "kimi-fabao" / "rules",
        Path("/usr/local/share/kimi-fabao/rules"),
    ]
    for p in common_paths:
        if p.exists():
            if playbook:
                pb = p / "playbooks" / playbook
                if pb.exists():
                    return pb
            return p

    raise FileNotFoundError(
        f"Rules directory not found. "
        f"Searched: {rules_dir}, {cwd_rules}, and common paths. "
        f"Set KIMI_FABAO_RULES environment variable to override."
    )


def load_json_rules(filename: str, playbook: str | None = None) -> dict:
    """Load a JSON rule file from the rules directory.

    If playbook is specified, loads from rules/playbooks/<playbook>/.
    Falls back to base rules directory if playbook-specific file not found.
    """
    rules_dir = get_rules_dir(playbook=playbook)
    path = rules_dir / filename

    # If playbook-specific file doesn't exist, try base rules
    if playbook and not path.exists():
        base_dir = get_rules_dir(playbook=None)
        path = base_dir / filename

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, strip whitespace."""
    return text.lower().strip() if text else ""


def contains_any(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the given keywords."""
    norm = normalize_text(text)
    for kw in keywords:
        if normalize_text(kw) in norm:
            return True
    return False


def regex_matches_any(text: str, patterns: list[str]) -> bool:
    """Check if text matches any of the given regex patterns."""
    if not text:
        return False
    for pattern in patterns:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


# ---------------------------------------------------------------------------
# Clause Type Classification
# ---------------------------------------------------------------------------

class ClauseClassifier:
    def __init__(self, patterns_config: dict):
        self.patterns = patterns_config.get("patterns", {})
        self.priority_order = patterns_config.get("priority_order", [])
        self.matching = patterns_config.get("matching", {})
        self.fallback = self.matching.get("fallback_type", "其他")

    def classify(self, clause_title: str) -> str:
        """Classify a clause title into one of the predefined types."""
        if not clause_title:
            return self.fallback

        norm_title = normalize_text(clause_title)
        matches = []

        for clause_type, config in self.patterns.items():
            keywords = config.get("keywords", [])
            for kw in keywords:
                norm_kw = normalize_text(kw)
                if norm_kw in norm_title:
                    matches.append((clause_type, len(norm_kw), config.get("priority", 99)))
                    break

        if not matches:
            return self.fallback

        # Sort by: longest match first, then by priority
        matches.sort(key=lambda x: (-x[1], x[2]))
        return matches[0][0]


# ---------------------------------------------------------------------------
# Risk Assessment
# ---------------------------------------------------------------------------

class RiskAssessor:
    def __init__(self, rules_config: dict):
        self.rules = rules_config.get("rules", [])
        self.risk_levels = rules_config.get("risk_levels", {})
        self.scoring = rules_config.get("scoring", {})

    def assess(self, revision: dict, clause_type: str, mode: str = "revision", vendor_country: str | None = None) -> list[dict]:
        """Apply all matching risk rules to a revision.

        Args:
            revision: The revision/existing record to assess.
            clause_type: The classified clause type.
            mode: "revision" (default) or "template".
            vendor_country: Detected vendor (Party B) country code (e.g., "US", "HK", "SG").

        Returns list of matched rule results."""
        matched = []
        rev_type = revision.get("type", "")
        rev_text = revision.get("text", "")
        context_full = revision.get("context", {}).get("full_sentence", "")

        # In template mode, "existing" records match against "existing" or "insertion" patterns
        # In revision mode, each type matches its own patterns
        pattern_type_priority = [rev_type]
        if mode == "template" and rev_type == "existing":
            pattern_type_priority = ["existing", "insertion", "any"]
        elif rev_type == "existing":
            # Should not happen in revision mode, but handle gracefully
            pattern_type_priority = ["existing", "insertion"]

        for rule in self.rules:
            # Check clause type filter
            applicable_types = rule.get("applies_to_clause_types", [])
            if applicable_types and clause_type not in applicable_types:
                continue

            # Check revision type filter
            applicable_rev_types = rule.get("applies_to_revision_types", [])
            if applicable_rev_types:
                # In template mode, "existing" records can match rules for "insertion"
                # because the risky content is already present in the template
                if mode == "template" and rev_type == "existing":
                    if "existing" not in applicable_rev_types and "insertion" not in applicable_rev_types:
                        continue
                elif rev_type not in applicable_rev_types:
                    continue

            # Check mode filter (optional, default applies to all modes)
            applicable_modes = rule.get("applies_to_modes", ["revision", "template"])
            if mode not in applicable_modes:
                continue

            # Check vendor country filter (optional, default applies to all countries)
            applicable_countries = rule.get("applies_to_vendor_countries", [])
            if applicable_countries:
                # If vendor country is explicitly detected, it must be in the list
                if vendor_country is not None and vendor_country not in applicable_countries:
                    continue
                # If vendor country is not detected, "general" must be in the list
                if vendor_country is None and "general" not in applicable_countries:
                    continue

            # Check text patterns
            patterns = rule.get("patterns", {})
            matched_patterns = False

            # Try matching against revision text first, then full context
            texts_to_check = [rev_text, context_full]

            for check_text in texts_to_check:
                if not check_text:
                    continue

                # Try each pattern type in priority order
                for ptype in pattern_type_priority:
                    # Try regex patterns for this type
                    regex_key = f"{ptype}_regex"
                    if regex_key in patterns:
                        if regex_matches_any(check_text, patterns[regex_key]):
                            matched_patterns = True
                            break

                    # Try plain keyword patterns for this type
                    if ptype in patterns:
                        if contains_any(check_text, patterns[ptype]):
                            matched_patterns = True
                            break

                if matched_patterns:
                    break

                # Try general patterns (no type prefix)
                if not matched_patterns:
                    if "" in patterns or "any" in patterns:
                        general = patterns.get("", []) + patterns.get("any", [])
                        if contains_any(check_text, general):
                            matched_patterns = True
                            break

            if matched_patterns:
                matched.append({
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "risk_level": rule["risk_level"],
                    "rationale": rule["rationale"],
                })

        return matched


# ---------------------------------------------------------------------------
# Revision Clustering (cross-clause关联)
# ---------------------------------------------------------------------------

class RevisionClusterer:
    """Group related revisions by theme."""

    CLUSTERS = [
        {
            "group_id": "liability_expansion",
            "theme": "责任范围扩大",
            "keywords": ["违约", "赔偿", "损失", "责任", "索赔"],
            "min_revisions": 2,
            "min_keyword_matches": 1,
        },
        {
            "group_id": "ip_transfer",
            "theme": "知识产权转让",
            "keywords": ["知识产权", "归甲方", "转让给甲方"],
            "min_revisions": 2,
            "min_keyword_matches": 1,
        },
        {
            "group_id": "payment_worsening",
            "theme": "付款条件恶化",
            "keywords": ["付款", "账期", "发票", "费用", "价格"],
            "min_revisions": 2,
            "min_keyword_matches": 1,
        },
        {
            "group_id": "service_expansion",
            "theme": "服务义务扩大",
            "keywords": ["服务", "范围", "需求", "包括但不限于", "免费"],
            "min_revisions": 2,
            "min_keyword_matches": 1,
        },
        {
            "group_id": "data_security",
            "theme": "数据安全义务加重",
            "keywords": ["数据", "泄露", "安全", "第三方索赔"],
            "min_revisions": 2,
            "min_keyword_matches": 1,
        },
    ]

    def cluster(self, analyzed_revisions: list[dict]) -> list[dict]:
        """Group revisions into thematic clusters.
        A revision must match at least min_keyword_matches keywords to be included."""
        clusters = []

        for cluster_def in self.CLUSTERS:
            theme = cluster_def["theme"]
            keywords = cluster_def["keywords"]
            min_revs = cluster_def["min_revisions"]
            min_matches = cluster_def.get("min_keyword_matches", 1)
            matched_ids = []

            for rev in analyzed_revisions:
                text = rev.get("text", "")
                clause_type = rev.get("clause_type", "")
                full = rev.get("context", {}).get("full_sentence", "")
                combined = f"{text} {clause_type} {full}"
                norm_combined = normalize_text(combined)

                match_count = sum(1 for kw in keywords if normalize_text(kw) in norm_combined)

                if match_count >= min_matches:
                    matched_ids.append(rev.get("id"))

            if len(matched_ids) >= min_revs:
                clusters.append({
                    "group_id": cluster_def["group_id"],
                    "theme": theme,
                    "revision_ids": matched_ids,
                    "count": len(matched_ids),
                })

        return clusters


# ---------------------------------------------------------------------------
# Main Analysis Pipeline
# ---------------------------------------------------------------------------

def analyze_revisions(docx_path: str, playbook: str | None = None, mode: str = "revision") -> dict:
    """Full analysis pipeline: extract → classify → assess → cluster.

    Args:
        docx_path: Path to the .docx file.
        playbook: Optional playbook ID (e.g., 'nda') for contract-type-specific rules.
        mode: "revision" (default, analyzes track changes) or "template" (analyzes clean contract).
    """

    # Step 1: Extract raw revisions
    raw = extract_revisions(docx_path)

    # Auto-detect mode from document if not explicitly specified
    has_revisions = raw["summary"].get("has_revisions", True)
    if mode == "revision" and not has_revisions:
        mode = "template"

    # Step 2: Load rules (with optional playbook override)
    clause_patterns = load_json_rules("clause_patterns.json", playbook=playbook)
    risk_rules = load_json_rules("risk_rules.json", playbook=playbook)

    classifier = ClauseClassifier(clause_patterns)
    assessor = RiskAssessor(risk_rules)
    clusterer = RevisionClusterer()

    # Step 3: Analyze each ordered revision
    analyzed = []
    risk_counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}

    vendor_country = raw.get("party_metadata", {}).get("vendor_country")

    for rev in raw["ordered_revisions"]:
        location = rev.get("location", "")
        clause_type = classifier.classify(location)

        rule_matches = assessor.assess(rev, clause_type, mode=mode, vendor_country=vendor_country)

        # Determine preliminary risk level
        if rule_matches:
            levels = [m["risk_level"] for m in rule_matches]
            # Take highest risk
            if "high" in levels:
                preliminary_level = "high"
            elif "medium" in levels:
                preliminary_level = "medium"
            else:
                preliminary_level = "low"
        else:
            preliminary_level = "unknown"

        risk_counts[preliminary_level] = risk_counts.get(preliminary_level, 0) + 1

        analyzed.append({
            "id": rev.get("id"),
            "type": rev.get("type"),
            "text": rev.get("text"),
            "author": rev.get("author"),
            "location": location,
            "clause_type": clause_type,
            "preliminary_risk_level": preliminary_level,
            "matched_rules": rule_matches,
            "context": rev.get("context", {}),
        })

    # Step 4: Cluster related revisions
    clusters = clusterer.cluster(analyzed)

    # Step 5: Build summary
    summary = {
        **raw["summary"],
        "high_risk_revisions": risk_counts["high"],
        "medium_risk_revisions": risk_counts["medium"],
        "low_risk_revisions": risk_counts["low"],
        "unclassified_revisions": risk_counts["unknown"],
        "revision_clusters": len(clusters),
    }

    # Step 6: Build summary_by_risk (LLM-friendly pre-aggregated view)
    summary_by_risk = {
        "high": [r for r in analyzed if r["preliminary_risk_level"] == "high"],
        "medium": [r for r in analyzed if r["preliminary_risk_level"] == "medium"],
        "low": [r for r in analyzed if r["preliminary_risk_level"] == "low"],
        "unknown": [r for r in analyzed if r["preliminary_risk_level"] == "unknown"],
    }

    result = {
        "document": docx_path,
        "mode": mode,
        "playbook": playbook,
        "vendor_country": vendor_country,
        "summary": summary,
        "analyzed_revisions": analyzed,
        "revision_clusters": clusters,
        "summary_by_risk": summary_by_risk,
        "paragraphs": raw["paragraphs"],
        "raw": {
            "clauses": raw["clauses"],
            "appendices": raw.get("appendices", []),
            "comments": raw["comments"],
            "paragraph_comments": raw["paragraph_comments"],
        },
    }

    # Include playbook metadata if applicable
    if playbook:
        result["playbook_info"] = {
            "id": playbook,
            "name": clause_patterns.get("playbook_name", playbook),
            "version": clause_patterns.get("version", "unknown"),
        }

    return result


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: python analyze_revisions.py <input.docx> [output.json] [--playbook <id>] [--mode <mode>]")
        print("\nOptions:")
        print("  --playbook <id>    Use contract-type-specific playbook (e.g., 'nda')")
        print("  --mode <mode>      Analysis mode: 'revision' (default) or 'template'")
        print("                     'revision': analyze track changes (w:ins/w:del)")
        print("                     'template': analyze clean contract text")
        print("\nExamples:")
        print("  python analyze_revisions.py contract.docx")
        print("  python analyze_revisions.py contract.docx result.json")
        print("  python analyze_revisions.py nda.docx result.json --playbook nda")
        print("  python analyze_revisions.py template.docx result.json --mode template")
        sys.exit(0 if not args else 1)

    docx_path = args[0]
    output_path = None
    playbook = None
    mode = "revision"

    # Parse remaining arguments
    i = 1
    while i < len(args):
        if args[i] == "--playbook" and i + 1 < len(args):
            playbook = args[i + 1]
            i += 2
        elif args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]
            i += 2
        elif output_path is None and not args[i].startswith("--"):
            output_path = args[i]
            i += 1
        else:
            i += 1

    result = analyze_revisions(docx_path, playbook=playbook, mode=mode)

    json_output = json.dumps(result, ensure_ascii=False, indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"Output written to: {output_path}")
    else:
        print(json_output)


if __name__ == "__main__":
    main()
