#!/usr/bin/env python3
"""
Kimi法宝 — 修订执行器（Post-Processing Step 7）

读取 write_plan.json，在原始 DOCX 中执行 track changes 写入和批注注入。

执行流程：
  1. 加载 write_plan.json + 原始 docx
  2. 前置校验（文本存在性、作者约束）
  3. 同步 revision_id / comment_id 起始值
  4. 逐项执行 action
  5. 保存文档（自动备份）
  6. 后置验证（重新分析输出文档）

Usage:
    python execute_revisions.py <write_plan.json> <input.docx> [output.docx] [--author "Moonshot Legal"]
"""

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

# 将 lib/ 加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from docx_operator import DocxOperator, NAMESPACES
from revision_builder import RevisionBuilder
from comment_injector import CommentInjector
from validators import DocumentValidator

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class RevisionExecutor:
    """执行 write_plan 中的写入操作。"""

    def __init__(self, docx_path: str, author: str = "Moonshot Legal"):
        self.op = DocxOperator(docx_path)
        self.builder = RevisionBuilder(author=author)

        # 动态查找批注样式 ID
        comment_text_style, comment_ref_style = self._find_comment_styles()
        self.injector = CommentInjector(
            author=author,
            comment_text_style=comment_text_style,
            comment_ref_style=comment_ref_style,
        )
        self.validator = DocumentValidator(self.op)
        self.author = author
        self.results = []

        # 同步起始 id，避免与文档中已有修订/批注冲突
        self._sync_ids()

    def _find_comment_styles(self) -> tuple[str, str]:
        """从 styles.xml 查找 annotation text 和 annotation reference 的 styleId。"""
        styles_root = self.op.get_styles()
        text_style = "7"  # 默认值
        ref_style = "17"  # 默认值

        if styles_root is not None:
            for s in styles_root.iter(f"{W}style"):
                name_el = s.find(f"{W}name")
                if name_el is None:
                    continue
                name_val = name_el.get(f"{W}val", "").lower()
                sid = s.get(f"{W}styleId", "")
                if name_val == "annotation text" and sid:
                    text_style = sid
                elif name_val == "annotation reference" and sid:
                    ref_style = sid

        return text_style, ref_style

    def _sync_ids(self) -> None:
        """
        扫描文档中已有的所有注释类型，设置全局唯一的起始 id。
        OOXML 规范要求 w:id 在 ins/del/bookmark/commentRange 中全局唯一。
        """
        doc_root = self.op.get_document()
        max_annotation_id = self.builder.find_max_annotation_id(doc_root)

        # 也检查 comments.xml 中的 id
        comments_root = self.op.get_comments()
        max_comment_id = self.injector.find_max_comment_id(comments_root)

        # 统一起始点：取所有来源的最大值
        # builder 语义: set_start_id(X) 后 _next_id() 返回 X+1
        # injector 语义: set_start_id(X) 后 _alloc_id() 返回 X
        global_max = max(max_annotation_id, max_comment_id)
        self.builder.set_start_id(global_max)
        self.injector.set_start_id(global_max + 1)

    def _cross_sync_ids(self) -> None:
        """
        在 builder 和 injector 之间同步 ID 计数器，确保全局唯一。

        语义差异：
        - builder._id_counter = 最后分配的 ID（_next_id 返回 counter+1）
        - injector._next_comment_id = 下一个待分配 ID（_alloc_id 返回当前值）
        """
        builder_last_used = self.builder._id_counter
        injector_last_used = self.injector._next_comment_id - 1
        last_used = max(builder_last_used, injector_last_used)
        self.builder.set_start_id(last_used)
        self.injector.set_start_id(last_used + 1)

    def execute(self, write_plan: dict, dry_run: bool = False) -> dict:
        """
        执行完整的 write_plan。

        Args:
            write_plan: write_plan.json 内容。
            dry_run: 如为 True，只校验不实际写入。

        Returns:
            执行结果报告 dict。
        """
        items = write_plan.get("items", [])
        executed = 0
        skipped = 0
        failed = 0

        for item in items:
            item_id = item.get("id", "unknown")
            action = item.get("action", {})
            engine_ref = item.get("engine_ref", {})
            disposition = item.get("disposition", "negotiable")

            result = {
                "item_id": item_id,
                "status": "pending",
                "error": None,
            }

            # 跳过状态为 skipped 的项
            if item.get("status") == "skipped":
                result["status"] = "skipped"
                self.results.append(result)
                skipped += 1
                continue

            # 前置校验
            location_hint = engine_ref.get("location", "")
            feasible, error_msg = self.validator.check_action_feasibility(action, location_hint)
            if not feasible:
                result["status"] = "failed"
                result["error"] = f"前置校验失败: {error_msg}"
                self.results.append(result)
                failed += 1
                continue

            if dry_run:
                result["status"] = "dry_run_ok"
                self.results.append(result)
                executed += 1
                continue

            # 执行写入
            try:
                ok, exec_msg = self._execute_action(action, location_hint)
                if ok:
                    result["status"] = "executed"
                    executed += 1
                else:
                    result["status"] = "failed"
                    result["error"] = exec_msg
                    failed += 1
            except Exception as e:
                result["status"] = "failed"
                result["error"] = f"执行异常: {str(e)}"
                failed += 1

            # 同步两个计数器，确保全局唯一
            self._cross_sync_ids()

            self.results.append(result)

        return {
            "total": len(items),
            "executed": executed,
            "skipped": skipped,
            "failed": failed,
            "items": self.results,
        }

    def _execute_action(self, action: dict, location_hint: str) -> tuple[bool, str]:
        """执行单个 action。"""
        action_type = action.get("type")

        if action_type == "replace_in_text":
            return self._do_replace_in_text(action, location_hint)
        elif action_type == "replace_in_revision":
            return self._do_replace_in_revision(action, location_hint)
        elif action_type == "delete_text":
            return self._do_delete_text(action, location_hint)
        elif action_type == "add_comment":
            return self._do_add_comment(action, location_hint)
        elif action_type == "insert_after_paragraph":
            return self._do_insert_after_paragraph(action, location_hint)
        elif action_type == "append_to_paragraph":
            return self._do_append_to_paragraph(action, location_hint)
        else:
            return False, f"未知的 action 类型: {action_type}"

    # ------------------------------------------------------------------
    # 具体 Action 实现
    # ------------------------------------------------------------------

    def _find_target_paragraph(self, text: str, location_hint: str = "") -> tuple[ET.Element | None, int]:
        """
        查找包含目标文本的段落。

        策略：
        1. 先精确匹配
        2. 再规范化匹配（去除多余空白）
        3. 如果有多个匹配，优先选择与 location_hint 相关的段落

        Returns:
            (段落元素, 段落索引) 或 (None, -1)
        """
        paragraphs = self.op.get_paragraphs()
        candidates = []

        for idx, para in enumerate(paragraphs):
            para_text = self.op.get_paragraph_text(para)
            if text in para_text:
                candidates.append((para, idx, para_text, 2))  # 精确匹配优先级2
            elif _normalize(text) in _normalize(para_text):
                candidates.append((para, idx, para_text, 1))  # 规范化匹配优先级1

        if not candidates:
            return None, -1

        if len(candidates) == 1:
            return candidates[0][0], candidates[0][1]

        # 多个匹配：优先选择与 location_hint 相关的
        if location_hint:
            norm_hint = _normalize(location_hint)
            for para, idx, para_text, priority in candidates:
                if norm_hint in _normalize(para_text):
                    return para, idx

        # 仍有多匹配，选第一个
        return candidates[0][0], candidates[0][1]

    # ------------------------------------------------------------------
    # 辅助方法：在单个 run 中执行替换（保留 prefix / suffix）
    # ------------------------------------------------------------------

    def _replace_single_run(
        self, para, container, container_idx: int, run, old_text: str, new_text: str
    ) -> tuple[bool, str]:
        """
        在单个 run 中将 old_text 替换为 del + ins。

        如果 run 的文本比 old_text 更长（如包含前缀/后缀标点），
        会保留 prefix 和 suffix 为独立的 run。

        Args:
            para: 段落元素。
            container: run 的直接父元素（para 本身或 <w:ins>/<w:del> 元素）。
            container_idx: container 在 para.children 中的索引。
            run: 包含 old_text 的 <w:r> 元素。
            old_text: 要删除的文本。
            new_text: 要插入的文本。

        Returns:
            (success, message)
        """
        t = run.find(f"{W}t")
        run_text = t.text if t is not None else ""
        original_rPr = run.find(f"{W}rPr")

        pos = run_text.index(old_text)
        prefix = run_text[:pos]
        suffix = run_text[pos + len(old_text):]

        # 构建替换元素序列
        new_elements = []
        if prefix:
            new_elements.append(self.builder.create_run(prefix, rPr=original_rPr))
        new_elements.append(self.builder.create_del(old_text, rPr=original_rPr))
        new_elements.append(self.builder.create_ins(new_text, rPr=original_rPr))
        if suffix:
            new_elements.append(self.builder.create_run(suffix, rPr=original_rPr))

        if container is para:
            # run 是段落的直接子元素
            para.remove(run)
            for j, el in enumerate(new_elements):
                para.insert(container_idx + j, el)
        else:
            # run 在 <w:ins>/<w:del> 内部，需要在段落层级操作
            # 移除整个 container，在其位置插入新元素
            para.remove(container)
            for j, el in enumerate(new_elements):
                para.insert(container_idx + j, el)

        return True, ""

    # ------------------------------------------------------------------
    # 辅助方法：跨 run 替换（文本分散在多个连续元素中）
    # ------------------------------------------------------------------

    def _replace_cross_run(
        self, para, old_text: str, new_text: str, para_idx: int
    ) -> tuple[bool, str]:
        """
        处理 old_text 分散在多个连续元素中的情况。

        策略：找到包含 old_text 的连续元素范围，将该范围替换为
        prefix_run + del(old_text) + ins(new_text) + suffix_run。
        """
        # 收集所有直接子元素的文本信息
        children = list(para)
        child_texts = []  # [(index, element, text, rPr)]
        for i, child in enumerate(children):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "r":
                t = child.find(f"{W}t")
                txt = t.text if t is not None and t.text else ""
                rPr = child.find(f"{W}rPr")
                child_texts.append((i, child, txt, rPr))
            elif tag in ("ins", "del"):
                # 收集该元素内所有 run 的文本
                parts = []
                first_rPr = None
                for r in child.iter(f"{W}r"):
                    t_el = r.find(f"{W}t")
                    dt_el = r.find(f"{W}delText")
                    txt = ""
                    if t_el is not None and t_el.text:
                        txt = t_el.text
                    elif dt_el is not None and dt_el.text:
                        txt = dt_el.text
                    if txt:
                        parts.append(txt)
                    if first_rPr is None:
                        first_rPr = r.find(f"{W}rPr")
                combined = "".join(parts)
                child_texts.append((i, child, combined, first_rPr))
            # 跳过 pPr、commentRangeStart/End 等

        if not child_texts:
            return False, "段落中无可用的文本元素"

        # 拼接连续文本，寻找包含 old_text 的窗口
        concat = "".join(ct[2] for ct in child_texts)
        if old_text not in concat:
            return False, f"在段落中未找到可替换的文本: '{old_text[:60]}...'"

        # 定位 old_text 在 concat 中的位置
        match_start = concat.index(old_text)
        match_end = match_start + len(old_text)

        # 确定涉及的元素范围
        cursor = 0
        first_idx = last_idx = None
        prefix = suffix = ""
        ref_rPr = None

        for ct_i, (idx, el, txt, rPr) in enumerate(child_texts):
            el_start = cursor
            el_end = cursor + len(txt)

            if el_start <= match_start < el_end and first_idx is None:
                first_idx = ct_i
                prefix = txt[:match_start - el_start]
                if ref_rPr is None:
                    ref_rPr = rPr

            if el_start < match_end <= el_end:
                last_idx = ct_i
                suffix = txt[match_end - el_start:]
                if ref_rPr is None:
                    ref_rPr = rPr
                break

            cursor = el_end

        if first_idx is None or last_idx is None:
            return False, "无法定位元素范围"

        # 构建替换序列
        new_elements = []
        if prefix:
            new_elements.append(self.builder.create_run(prefix, rPr=ref_rPr))
        new_elements.append(self.builder.create_del(old_text, rPr=ref_rPr))
        new_elements.append(self.builder.create_ins(new_text, rPr=ref_rPr))
        if suffix:
            new_elements.append(self.builder.create_run(suffix, rPr=ref_rPr))

        # 移除范围内的元素，插入新元素
        first_para_idx = child_texts[first_idx][0]
        elements_to_remove = [child_texts[ci][1] for ci in range(first_idx, last_idx + 1)]
        for el in elements_to_remove:
            para.remove(el)

        for j, el in enumerate(new_elements):
            para.insert(first_para_idx + j, el)

        return True, f"跨 run 替换成功（段落 {para_idx}，涉及 {last_idx - first_idx + 1} 个元素）"

    def _do_replace_in_text(self, action: dict, location_hint: str) -> tuple[bool, str]:
        """
        将 old_text 替换为 new_text（通过 del + ins）。

        搜索顺序：
        1. 直接 <w:r> 子元素（单 run 匹配）
        2. <w:ins> 内部的 <w:r>（单 run 匹配）
        3. 跨元素匹配（文本分散在多个连续 run / ins / del 中）

        所有路径均保留 prefix / suffix 和 rPr 格式。
        """
        old_text = action.get("original_text", "")
        new_text = action.get("replacement_text", "")

        para, idx = self._find_target_paragraph(old_text, location_hint)
        if para is None:
            return False, f"未找到包含原文的段落: '{old_text[:60]}...'"

        # Pass 1: 直接 <w:r> 子元素
        children = list(para)
        for i, child in enumerate(children):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "r":
                t = child.find(f"{W}t")
                if t is not None and t.text and old_text in t.text:
                    return self._replace_single_run(para, para, i, child, old_text, new_text)

        # Pass 2: <w:ins> 内部的单个 run
        for i, child in enumerate(children):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "ins":
                for r in child.iter(f"{W}r"):
                    t = r.find(f"{W}t")
                    if t is not None and t.text and old_text in t.text:
                        return self._replace_single_run(para, child, i, r, old_text, new_text)

        # Pass 3: 跨元素匹配（文本分散在多个 run / ins 中）
        para_text = self.op.get_paragraph_text(para)
        if old_text in para_text:
            return self._replace_cross_run(para, old_text, new_text, idx)

        return False, f"在段落中未找到可替换的文本: '{old_text[:60]}...'"

    def _do_replace_in_revision(self, action: dict, location_hint: str) -> tuple[bool, str]:
        """修改已有修订中的文本（较复杂，先实现简化版）。"""
        # 简化版：等同于 replace_in_text
        return self._do_replace_in_text(action, location_hint)

    def _do_delete_text(self, action: dict, location_hint: str) -> tuple[bool, str]:
        """将文本包装为删除修订。"""
        old_text = action.get("original_text", "")

        para, idx = self._find_target_paragraph(old_text, location_hint)
        if para is None:
            return False, f"未找到包含原文的段落: '{old_text[:60]}...'"

        children = list(para)
        for i, child in enumerate(children):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "r":
                t = child.find(f"{W}t")
                if t is not None and t.text == old_text:
                    original_rPr = child.find(f"{W}rPr")
                    # 完全匹配，替换为 del（继承原始格式）
                    del_el = self.builder.create_del(old_text, rPr=original_rPr)
                    para.remove(child)
                    para.insert(i, del_el)
                    return True, ""

        return False, f"在段落中未找到精确匹配的文本: '{old_text[:60]}...'"

    def _do_add_comment(self, action: dict, location_hint: str) -> tuple[bool, str]:
        """添加段落级批注。"""
        comment_text = action.get("comment_text") or action.get("comment", "")
        target_text = action.get("target_text", "")

        # 确定目标段落
        if target_text:
            para, idx = self._find_target_paragraph(target_text, location_hint)
        elif location_hint:
            para, idx = self._find_target_paragraph(location_hint, location_hint)
        else:
            # 无目标，添加到第一个非空段落
            for p in self.op.get_paragraphs():
                if self.op.get_paragraph_text(p).strip():
                    para = p
                    break
            else:
                return False, "文档中无可用段落"
            idx = -1

        if para is None:
            return False, "未找到目标段落"

        comment_id = self.injector.add_paragraph_comment(
            self.op, para, comment_text, target_text=target_text or None
        )
        return True, f"批注 id={comment_id}"

    @staticmethod
    def _extract_para_properties(para) -> tuple:
        """
        从段落中提取段落属性（pPr）和最后一个 run 的字符属性（rPr）。

        返回 (pPr_element_or_None, rPr_element_or_None)。
        不做 deepcopy，调用方负责 copy。
        """
        pPr = para.find(f"{W}pPr")
        # 从段落的最后一个 run 提取 rPr
        last_rPr = None
        for child in reversed(list(para)):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "r":
                last_rPr = child.find(f"{W}rPr")
                break
        return pPr, last_rPr

    def _do_insert_after_paragraph(self, action: dict, location_hint: str) -> tuple[bool, str]:
        """在目标段落后插入新段落（带插入修订）。继承目标段落的样式。"""
        target_text = action.get("target_text", "")
        insertion_text = action.get("insertion_text", "")

        if not target_text:
            # 无目标段落，在文档末尾插入
            body = self.op.get_body()
            new_para = self.builder.create_paragraph_with_ins(insertion_text)
            body.append(new_para)
            return True, "已插入到文档末尾"

        para, idx = self._find_target_paragraph(target_text, location_hint)
        if para is None:
            return False, f"未找到目标段落: '{target_text[:60]}...'"

        # 提取目标段落的样式和字符格式
        source_pPr, source_rPr = self._extract_para_properties(para)

        body = self.op.get_body()
        all_children = list(body)
        try:
            target_idx = all_children.index(para)
        except ValueError:
            return False, "无法在文档结构中找到目标段落"

        new_para = self.builder.create_paragraph_with_ins(
            insertion_text, pPr=source_pPr, rPr=source_rPr
        )
        # 在 body 中 target_para 之后插入
        body.insert(target_idx + 1, new_para)
        return True, f"已插入到段落 {idx} 之后（继承段落样式）"

    def _do_append_to_paragraph(self, action: dict, location_hint: str) -> tuple[bool, str]:
        """在段落末尾追加文本（带插入修订）。"""
        target_text = action.get("target_text", "")
        append_text = action.get("append_text", "")

        if target_text:
            para, idx = self._find_target_paragraph(target_text, location_hint)
        elif location_hint:
            para, idx = self._find_target_paragraph(location_hint, location_hint)
        else:
            return False, "缺少 target_text 或 location_hint"

        if para is None:
            return False, "未找到目标段落"

        # 从段落末尾的 run 提取格式
        last_rPr = None
        for child in reversed(list(para)):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "r":
                last_rPr = child.find(f"{W}rPr")
                break
        ins_el = self.builder.create_ins(append_text, rPr=last_rPr)
        para.append(ins_el)
        return True, f"已追加到段落 {idx}"

    def save(self, output_path: str | None = None) -> str:
        """保存修改后的文档。"""
        # 标记就地修改的 XML part 为已修改
        self.op.mark_modified("word/document.xml")
        self.op.mark_modified("word/comments.xml")
        # 同步 commentsExtended.xml（set_comments_extended 内部会标记 modified）
        self.injector.sync_comments_extended(self.op)
        return self.op.save(output_path=output_path, backup=True)

    def post_validate(self, expected_items: int) -> list[str]:
        """后置验证。"""
        return self.validator.validate_result(expected_items, self.author)


def run_analyze_revisions(docx_path: str, playbook: str | None = None) -> dict:
    """调用 analyze_revisions.py 分析文档。"""
    script_dir = Path(__file__).resolve().parent.parent
    script = script_dir / "analyze_revisions.py"

    cmd = [sys.executable, str(script), docx_path]
    if playbook:
        cmd.extend(["--playbook", playbook])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"analyze_revisions.py 失败: {result.stderr}")

    return json.loads(result.stdout)


def _normalize(text: str) -> str:
    import re
    return re.sub(r"\s+", " ", text.strip().lower())


def main():
    parser = argparse.ArgumentParser(description="执行 write_plan 到 DOCX")
    parser.add_argument("write_plan", help="write_plan.json 路径")
    parser.add_argument("input_docx", help="原始 DOCX 路径")
    parser.add_argument("output_docx", nargs="?", help="输出 DOCX 路径（默认覆盖原文件）")
    parser.add_argument("--author", default="Moonshot Legal", help="修订作者名")
    parser.add_argument("--dry-run", action="store_true", help="只校验不写入")
    parser.add_argument("--post-validate", action="store_true", help="执行后置验证")
    args = parser.parse_args()

    if not Path(args.write_plan).exists():
        print(f"Error: write_plan 不存在: {args.write_plan}", file=sys.stderr)
        sys.exit(1)
    if not Path(args.input_docx).exists():
        print(f"Error: input_docx 不存在: {args.input_docx}", file=sys.stderr)
        sys.exit(1)

    write_plan = load_json(args.write_plan)

    executor = RevisionExecutor(args.input_docx, author=args.author)

    print(f"开始执行 write_plan: {len(write_plan.get('items', []))} 项...")
    result = executor.execute(write_plan, dry_run=args.dry_run)

    print(f"\n执行结果:")
    print(f"  总计: {result['total']}")
    print(f"  成功: {result['executed']}")
    print(f"  跳过: {result['skipped']}")
    print(f"  失败: {result['failed']}")

    if result['failed'] > 0:
        print("\n失败项:")
        for item in result['items']:
            if item['status'] == 'failed':
                print(f"  [{item['item_id']}] {item['error']}")

    if not args.dry_run and result['executed'] > 0:
        output = executor.save(output_path=args.output_docx)
        print(f"\n文档已保存: {output}")

        if args.post_validate:
            print("\n后置验证...")
            expected = result['executed']
            errors = executor.post_validate(expected)
            if errors:
                for e in errors:
                    print(f"  ⚠ {e}")
            else:
                print("  ✓ 后置验证通过")


if __name__ == "__main__":
    main()
