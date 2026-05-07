"""
写入层校验器 — 前置校验（plan 合法性）与 后置校验（写入结果）。

纯标准库实现：json, re, pathlib
"""

import json
import re
from pathlib import Path
from typing import Any


# 合法的 action 类型
VALID_ACTION_TYPES = {
    "insert_after_paragraph",
    "replace_in_text",
    "replace_in_revision",
    "append_to_paragraph",
    "delete_text",
    "add_comment",
}


class ValidationError(Exception):
    """校验失败异常，包含详细错误信息。"""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class WritePlanValidator:
    """对 write_plan.json 进行前置合法性校验。"""

    def __init__(self, engine_output_path: str | None = None):
        self.engine_output_path = engine_output_path
        self._engine_data: dict | None = None

    def _load_engine_output(self) -> dict:
        if self._engine_data is None and self.engine_output_path:
            with open(self.engine_output_path, "r", encoding="utf-8") as f:
                self._engine_data = json.load(f)
        return self._engine_data or {}

    def validate(self, write_plan: dict | str) -> list[str]:
        """
        校验 write_plan 的完整性和合法性。

        Args:
            write_plan: 已解析的 dict 或 JSON 文件路径。

        Returns:
            错误信息列表（空列表表示全部通过）。
        """
        errors: list[str] = []

        if isinstance(write_plan, str):
            path = Path(write_plan)
            if not path.exists():
                errors.append(f"write_plan 文件不存在: {write_plan}")
                return errors
            with open(path, "r", encoding="utf-8") as f:
                write_plan = json.load(f)

        # 1. 顶层字段校验
        required_top = {"source_engine", "source_document", "items"}
        missing = required_top - set(write_plan.keys())
        if missing:
            errors.append(f"write_plan 缺少必填字段: {missing}")

        items = write_plan.get("items", [])
        if not isinstance(items, list):
            errors.append("write_plan.items 必须是列表")
            return errors

        # 2. 逐项校验
        for idx, item in enumerate(items):
            prefix = f"items[{idx}]"
            item_errors = self._validate_item(item, prefix)
            errors.extend(item_errors)

        return errors

    def _validate_item(self, item: dict, prefix: str) -> list[str]:
        errors = []

        # 2.1 engine_ref 必填
        engine_ref = item.get("engine_ref")
        if not isinstance(engine_ref, dict):
            errors.append(f"{prefix}.engine_ref 必须是对象")
            return errors

        revision_id = engine_ref.get("revision_id")
        if not revision_id:
            errors.append(f"{prefix}.engine_ref.revision_id 必填")

        # 2.2 溯源校验：revision_id 是否存在于 engine_output
        if self.engine_output_path:
            engine_data = self._load_engine_output()
            analyzed = engine_data.get("analyzed_revisions", [])
            ids = {str(r.get("id")) for r in analyzed}
            if str(revision_id) not in ids:
                errors.append(
                    f"{prefix}.engine_ref.revision_id='{revision_id}' 在 engine_output 中不存在"
                )

        # 2.3 action 必填
        action = item.get("action")
        if not isinstance(action, dict):
            errors.append(f"{prefix}.action 必须是对象")
            return errors

        action_type = action.get("type")
        if not action_type:
            errors.append(f"{prefix}.action.type 必填")
        elif action_type not in VALID_ACTION_TYPES:
            errors.append(
                f"{prefix}.action.type='{action_type}' 不合法，必须是 {VALID_ACTION_TYPES}"
            )

        # 2.4 action 字段完整性校验
        type_required = {
            "insert_after_paragraph": {"insertion_text"},
            "replace_in_text": {"original_text", "replacement_text"},
            "replace_in_revision": {"original_text", "replacement_text"},
            "append_to_paragraph": {"append_text"},
            "delete_text": {"original_text"},
            "add_comment": {"comment_text"},
        }
        required_fields = type_required.get(action_type, set())
        action_keys = set(action.keys())
        missing_fields = required_fields - action_keys
        if missing_fields:
            errors.append(
                f"{prefix}.action 缺少 {action_type} 所需的字段: {missing_fields}"
            )

        # 2.5 mandatory / negotiable 标记校验
        disposition = item.get("disposition", "negotiable")
        if disposition not in {"mandatory", "negotiable"}:
            errors.append(
                f"{prefix}.disposition='{disposition}' 不合法，必须是 mandatory/negotiable"
            )

        return errors


class DocumentValidator:
    """对 DOCX 文档执行前置文本匹配校验和后置结果校验。"""

    def __init__(self, docx_operator):
        """
        Args:
            docx_operator: DocxOperator 实例。
        """
        self.op = docx_operator

    def check_text_exists(self, text: str, location_hint: str | None = None) -> tuple[bool, list[int]]:
        """
        检查文本是否存在于文档中。

        Args:
            text: 要查找的文本。
            location_hint: 位置提示（如条款标题），用于优先匹配。

        Returns:
            (是否存在, 匹配的段落索引列表)
        """
        paragraphs = self.op.get_paragraphs()
        matched_indices = []
        norm_text = self._normalize(text)

        for idx, para in enumerate(paragraphs):
            para_text = self.op.get_paragraph_text(para)
            if text in para_text:
                matched_indices.append(idx)
            elif norm_text in self._normalize(para_text):
                matched_indices.append(idx)

        return len(matched_indices) > 0, matched_indices

    def check_action_feasibility(self, action: dict, location_hint: str | None = None) -> tuple[bool, str]:
        """
        在执行前检查单个 action 是否可行。

        Returns:
            (是否可行, 错误信息)
        """
        action_type = action.get("type")

        if action_type in ("replace_in_text", "delete_text"):
            original = action.get("original_text", "")
            exists, indices = self.check_text_exists(original, location_hint)
            if not exists:
                return False, f"原文未找到: '{original[:80]}...'" if len(original) > 80 else f"原文未找到: '{original}'"
            if len(indices) > 1:
                return False, f"原文在文档中出现 {len(indices)} 次，无法精确定位"
            return True, ""

        elif action_type == "replace_in_revision":
            # 需要找到包含特定修订的段落
            original = action.get("original_text", "")
            exists, indices = self.check_text_exists(original, location_hint)
            if not exists:
                return False, f"修订目标文本未找到: '{original[:80]}...'" if len(original) > 80 else f"修订目标文本未找到: '{original}'"
            return True, ""

        elif action_type == "add_comment":
            # 批注总是可行的
            return True, ""

        elif action_type == "insert_after_paragraph":
            # 需要定位目标段落
            target = action.get("target_text", "")
            if target:
                exists, indices = self.check_text_exists(target, location_hint)
                if not exists:
                    return False, f"插入目标段落未找到: '{target[:80]}...'" if len(target) > 80 else f"插入目标段落未找到: '{target}'"
            return True, ""

        return True, ""

    def validate_result(self, expected_items: int, expected_author: str) -> list[str]:
        """
        后置校验：分析写入后的文档，确认新增修订/批注是否正确生成。

        Args:
            expected_items: 期望生成的新修订数。
            expected_author: 期望的作者名。

        Returns:
            错误信息列表。
        """
        errors = []
        body = self.op.get_body()
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

        # 只统计指定作者的新增修订
        author_ins = 0
        author_del = 0
        for el in body.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag in ("ins", "del"):
                author = el.get(f"{W}author", "")
                if author == expected_author:
                    if tag == "ins":
                        author_ins += 1
                    else:
                        author_del += 1

        author_total = author_ins + author_del
        if author_total < expected_items:
            errors.append(
                f"后置校验: 指定作者的新增修订数 ({author_total}) 少于期望值 ({expected_items})"
            )

        # 统计指定作者的新增批注
        comments_root = self.op.get_comments()
        author_comments = 0
        if comments_root is not None:
            for c in comments_root.iter(f"{W}comment"):
                author = c.get(f"{W}author", "")
                if author == expected_author:
                    author_comments += 1

        if author_comments == 0 and expected_items > 0:
            # 如果预期有写入但既没有修订也没有批注，才报错
            # 但如果 author_total > 0，说明有修订，只是没有批注，这是正常的
            pass

        return errors

    @staticmethod
    def _normalize(text: str) -> str:
        """规范化文本用于匹配（去除多余空白）。"""
        return re.sub(r"\s+", " ", text.strip().lower())


# ---------------------------------------------------------------------------
# CLI 入口（用于独立测试）
# ---------------------------------------------------------------------------

def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python validators.py <write_plan.json> [engine_output.json]")
        sys.exit(1)

    plan_path = sys.argv[1]
    engine_path = sys.argv[2] if len(sys.argv) > 2 else None

    validator = WritePlanValidator(engine_output_path=engine_path)
    errors = validator.validate(plan_path)

    if errors:
        print(f"校验失败 ({len(errors)} 项):")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("✓ write_plan 校验通过")


if __name__ == "__main__":
    main()
