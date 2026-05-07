#!/usr/bin/env python3
"""
Kimi法宝 — Write Plan 生成器（Post-Processing Step 5）

读取 analyze_revisions.py 输出的 engine_output.json，
基于 preliminary_risk_level 和 matched_rules 生成 write_plan_template.json。

生成逻辑（纯规则驱动，不接触 LLM）：
  1. 筛选 preliminary_risk_level 为 high/medium 的修订
  2. 对每个 matched_rule，从 write_actions.json 查找对应模板
  3. 填充 engine_ref 和 action 模板，输出 write_plan_template

Usage:
    python write_plan_generator.py <engine_output.json> [write_plan_template.json] [--playbook nda]
"""

import argparse
import json
import sys
from pathlib import Path


def get_skill_dir() -> Path:
    """定位 kimi-fabao skill 根目录。"""
    script_dir = Path(__file__).resolve().parent.parent.parent
    if (script_dir / "rules").exists():
        return script_dir
    # fallback
    return Path.home() / ".claude" / "skills" / "kimi-fabao"


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_write_actions(playbook: str | None = None) -> dict:
    """加载 write_actions.json（支持 playbook 子目录）。"""
    skill_dir = get_skill_dir()
    paths_to_try = []

    if playbook:
        paths_to_try.append(skill_dir / "rules" / "playbooks" / playbook / "write_actions.json")
    paths_to_try.append(skill_dir / "rules" / "write_actions.json")

    for p in paths_to_try:
        if p.exists():
            return load_json(str(p))

    # 如果都不存在，返回空结构
    return {"action_templates": {}, "default_action": {"disposition": "negotiable", "action": {"type": "add_comment", "comment_text": "建议评估此条款风险。"}}}


def generate_write_plan(
    engine_output: dict,
    write_actions: dict,
    playbook: str | None = None,
) -> dict:
    """
    基于 engine_output 和 write_actions 生成 write_plan_template。

    Args:
        engine_output: analyze_revisions.py 的输出 dict。
        write_actions: write_actions.json 的内容。
        playbook: 可选的 playbook ID。

    Returns:
        write_plan_template dict。
    """
    analyzed = engine_output.get("analyzed_revisions", [])
    action_templates = write_actions.get("action_templates", {})
    default_action = write_actions.get("default_action", {})

    items = []
    item_counter = 0

    for rev in analyzed:
        risk_level = rev.get("preliminary_risk_level", "unknown")

        # 筛选策略：high/medium 必须生成；unknown 跳过（由 LLM 在 Step 6 判断）；low 跳过
        if risk_level not in ("high", "medium"):
            continue

        matched_rules = rev.get("matched_rules", [])
        if not matched_rules:
            # 有 risk_level 但没有 matched_rules（理论上不应发生），使用默认动作
            item_counter += 1
            items.append(_build_item(item_counter, rev, default_action, risk_level))
            continue

        for rule in matched_rules:
            rule_id = rule.get("rule_id", "")
            template = action_templates.get(rule_id)
            if template is None:
                # 规则无映射，使用默认动作但保留规则信息
                item_counter += 1
                items.append(_build_item(item_counter, rev, default_action, risk_level, rule_id=rule_id))
                continue

            item_counter += 1
            items.append(_build_item(item_counter, rev, template, risk_level, rule_id=rule_id))

    return {
        "source_engine": "analyze_revisions.py",
        "source_document": engine_output.get("document", ""),
        "playbook": playbook or engine_output.get("playbook", ""),
        "mode": engine_output.get("mode", "revision"),
        "generation_method": "rule_driven_template",
        "items": items,
        "stats": {
            "total_analyzed": len(analyzed),
            "high_risk_items": sum(1 for i in items if i.get("engine_ref", {}).get("preliminary_risk_level") == "high"),
            "medium_risk_items": sum(1 for i in items if i.get("engine_ref", {}).get("preliminary_risk_level") == "medium"),
            "mandatory_items": sum(1 for i in items if i.get("disposition") == "mandatory"),
            "negotiable_items": sum(1 for i in items if i.get("disposition") == "negotiable"),
        }
    }


def _build_item(
    item_id: int,
    rev: dict,
    template: dict,
    risk_level: str,
    rule_id: str | None = None,
) -> dict:
    """构建单个 write_plan item。"""
    matched_rules = rev.get("matched_rules", [])
    actual_rule_id = rule_id or (matched_rules[0]["rule_id"] if matched_rules else "")
    actual_rule_name = ""
    for r in matched_rules:
        if r.get("rule_id") == actual_rule_id:
            actual_rule_name = r.get("rule_name", "")
            break

    disposition = template.get("disposition", "negotiable")
    action_template = template.get("action", {})

    # 从 revision 的 context 中提取可能用于填充占位符的文本
    context = rev.get("context", {})
    full_sentence = context.get("full_sentence", "")

    item = {
        "id": f"item_{item_id:03d}",
        "engine_ref": {
            "revision_id": rev.get("id"),
            "location": rev.get("location", ""),
            "clause_type": rev.get("clause_type", ""),
            "preliminary_risk_level": risk_level,
            "matched_rule_id": actual_rule_id,
            "matched_rule_name": actual_rule_name,
        },
        "disposition": disposition,
        "status": "template",  # template → pending → executed / skipped
        "action": {
            **action_template,
            "_placeholders": _extract_placeholders(action_template),
        },
        "context": {
            "full_sentence": full_sentence,
            "before": context.get("before", ""),
            "after": context.get("after", ""),
        },
        "rationale": template.get("rationale", ""),
        "fallback": action_template.get("fallback", ""),
    }

    # 如果 disposition 为 mandatory，默认标记为待执行
    if disposition == "mandatory":
        item["status"] = "pending"

    return item


def _extract_placeholders(action: dict) -> list[str]:
    """从 action 的文本字段中提取 {placeholder} 占位符。"""
    placeholders = set()
    for key in ("original_text", "replacement_text", "comment_text", "insertion_text", "append_text"):
        text = action.get(key, "")
        if text:
            placeholders.update(re.findall(r"\{([^}]+)\}", text))
    return sorted(placeholders)


def main():
    parser = argparse.ArgumentParser(
        description="基于 engine_output.json 生成 write_plan_template.json"
    )
    parser.add_argument("engine_output", help="analyze_revisions.py 输出的 JSON 文件路径")
    parser.add_argument("output", nargs="?", help="输出文件路径（默认 stdout）")
    parser.add_argument("--playbook", help="Playbook ID（如 nda）")
    args = parser.parse_args()

    if not Path(args.engine_output).exists():
        print(f"Error: engine_output 文件不存在: {args.engine_output}", file=sys.stderr)
        sys.exit(1)

    engine_output = load_json(args.engine_output)
    write_actions = load_write_actions(playbook=args.playbook)

    write_plan = generate_write_plan(
        engine_output=engine_output,
        write_actions=write_actions,
        playbook=args.playbook,
    )

    json_output = json.dumps(write_plan, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"Write plan template written to: {args.output}")
        print(f"Stats: {write_plan['stats']}")
    else:
        print(json_output)


if __name__ == "__main__":
    main()
