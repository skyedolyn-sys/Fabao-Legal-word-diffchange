"""
Word 批注（Comments）注入器。

支持：
1. 读取/写入 comments.xml
2. 在 document.xml 中插入 commentRangeStart / commentRangeEnd / commentReference
3. 自动分配批注 id

纯标准库实现：xml.etree, datetime, re
"""

import re
import secrets
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
W15 = "{http://schemas.microsoft.com/office/word/2012/wordml}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_para_id() -> str:
    """生成 8 位十六进制 paraId（与 Word 原生格式一致）。"""
    return secrets.token_hex(4).upper()


class CommentInjector:
    """管理 Word 文档中的批注（comments）。"""

    def __init__(self, author: str = "Moonshot Legal",
                 comment_text_style: str = "7",
                 comment_ref_style: str = "17"):
        self.author = author
        self._next_comment_id = 0
        self.comment_text_style = comment_text_style  # 段落样式: annotation text
        self.comment_ref_style = comment_ref_style    # 字符样式: annotation reference
        self._new_comment_para_ids: list[tuple[int, str]] = []  # [(comment_id, para_id)]

    def set_start_id(self, start: int) -> None:
        """手动设置起始批注 id。"""
        self._next_comment_id = start

    def _alloc_id(self) -> int:
        """分配新的批注 id。"""
        cid = self._next_comment_id
        self._next_comment_id += 1
        return cid

    # ------------------------------------------------------------------
    # comments.xml 操作
    # ------------------------------------------------------------------

    def create_comments_root(self) -> ET.Element:
        """创建一个空的 <w:comments> 根元素。"""
        return ET.Element(f"{W}comments")

    def add_comment(
        self,
        comments_root: ET.Element,
        text: str,
        comment_id: int | None = None,
        author: str | None = None,
        date: str | None = None,
    ) -> int:
        """
        向 comments.xml 中添加一条批注。

        生成的 XML 与 Word 原生格式一致：
        - <w:p> 带 w14:paraId 和 <w:pStyle val="7"/>
        - <w:r> 带 <w:rPr><w:rStyle val="17"/></w:rPr>

        Args:
            comments_root: <w:comments> 根元素。
            text: 批注文本。
            comment_id: 批注 id；None 则自动分配。
            author: 作者；None 则使用 self.author。
            date: ISO 日期；None 则使用当前时间。

        Returns:
            分配的批注 id。
        """
        if comment_id is None:
            comment_id = self._alloc_id()
        if author is None:
            author = self.author
        if date is None:
            date = _now_iso()

        comment_el = ET.SubElement(comments_root, f"{W}comment")
        comment_el.set(f"{W}id", str(comment_id))
        comment_el.set(f"{W}author", author)
        comment_el.set(f"{W}date", date)
        comment_el.set(f"{W}initials", "".join(c for c in author if c.isupper())[:2])

        # 批注内容段落（带 paraId 和 pStyle）
        para_id = _gen_para_id()
        p = ET.SubElement(comment_el, f"{W}p")
        p.set(f"{W14}paraId", para_id)

        # 段落样式: annotation text
        pPr = ET.SubElement(p, f"{W}pPr")
        pStyle = ET.SubElement(pPr, f"{W}pStyle")
        pStyle.set(f"{W}val", self.comment_text_style)

        # 批注引用标记 run（Word 要求，否则批注内容不显示）
        ref_r = ET.SubElement(p, f"{W}r")
        ref_rPr = ET.SubElement(ref_r, f"{W}rPr")
        ref_rStyle = ET.SubElement(ref_rPr, f"{W}rStyle")
        ref_rStyle.set(f"{W}val", self.comment_ref_style)
        ET.SubElement(ref_r, f"{W}annotationRef")

        # 批注文本 run
        r = ET.SubElement(p, f"{W}r")
        t = ET.SubElement(r, f"{W}t")
        t.text = text
        if text.startswith(" ") or text.endswith(" "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

        # 记录 paraId 以便后续同步到 commentsExtended.xml
        self._new_comment_para_ids.append((comment_id, para_id))

        return comment_id

    def load_comments(self, comments_root: ET.Element) -> dict[int, dict]:
        """
        从 <w:comments> 中读取所有批注。

        Returns:
            {comment_id: {"author": ..., "text": ..., "date": ...}}
        """
        result = {}
        for comment in comments_root.iter(f"{W}comment"):
            cid_str = comment.get(f"{W}id")
            if cid_str is None:
                continue
            try:
                cid = int(cid_str)
            except ValueError:
                continue

            # 提取文本
            texts = []
            for t in comment.iter(f"{W}t"):
                if t.text:
                    texts.append(t.text)

            result[cid] = {
                "author": comment.get(f"{W}author", ""),
                "date": comment.get(f"{W}date", ""),
                "text": "".join(texts),
            }
        return result

    def find_max_comment_id(self, comments_root: ET.Element | None) -> int:
        """返回 comments.xml 中最大的批注 id。"""
        if comments_root is None:
            return -1
        max_id = -1
        for comment in comments_root.iter(f"{W}comment"):
            cid_str = comment.get(f"{W}id")
            if cid_str is not None:
                try:
                    max_id = max(max_id, int(cid_str))
                except ValueError:
                    pass
        return max_id

    # ------------------------------------------------------------------
    # document.xml 批注范围标记
    # ------------------------------------------------------------------

    def inject_comment_range(
        self,
        paragraph: ET.Element,
        comment_id: int,
        target_text: str | None = None,
    ) -> bool:
        """
        在段落的指定文本位置插入 commentRangeStart 和 commentRangeEnd。

        简单实现：在段落开头插入 commentRangeStart，在末尾插入 commentRangeEnd
        和 commentReference。这是**段落级批注**（适用于整个段落的批注）。

        Args:
            paragraph: <w:p> 元素。
            comment_id: 批注 id。
            target_text: 如果提供，尝试在该文本所在的 <w:r> 前后插入范围标记。
                        None 则标记整个段落。

        Returns:
            是否成功插入。
        """
        if target_text is None:
            return self._inject_paragraph_level(paragraph, comment_id)

        # 尝试在包含 target_text 的 <w:r> 前后插入
        children = list(paragraph)
        for i, child in enumerate(children):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "r":
                text_el = child.find(f"{W}t")
                if text_el is not None and text_el.text and target_text in text_el.text:
                    # 在该 run 前插入 start
                    start_el = ET.Element(f"{W}commentRangeStart")
                    start_el.set(f"{W}id", str(comment_id))
                    paragraph.insert(i, start_el)

                    # 在该 run 后插入 end + reference
                    end_el = ET.Element(f"{W}commentRangeEnd")
                    end_el.set(f"{W}id", str(comment_id))

                    ref_el = ET.Element(f"{W}r")
                    ref_rPr = ET.SubElement(ref_el, f"{W}rPr")
                    ref_style = ET.SubElement(ref_rPr, f"{W}rStyle")
                    ref_style.set(f"{W}val", self.comment_ref_style)
                    ref_comment = ET.SubElement(ref_el, f"{W}commentReference")
                    ref_comment.set(f"{W}id", str(comment_id))

                    paragraph.insert(i + 2, end_el)
                    paragraph.insert(i + 3, ref_el)
                    return True

        # 未找到目标文本，回退到段落级
        return self._inject_paragraph_level(paragraph, comment_id)

    def _inject_paragraph_level(self, paragraph: ET.Element, comment_id: int) -> bool:
        """在段落开头和末尾插入批注范围标记。"""
        start_el = ET.Element(f"{W}commentRangeStart")
        start_el.set(f"{W}id", str(comment_id))

        end_el = ET.Element(f"{W}commentRangeEnd")
        end_el.set(f"{W}id", str(comment_id))

        ref_el = ET.Element(f"{W}r")
        ref_rPr = ET.SubElement(ref_el, f"{W}rPr")
        ref_style = ET.SubElement(ref_rPr, f"{W}rStyle")
        ref_style.set(f"{W}val", self.comment_ref_style)
        ref_comment = ET.SubElement(ref_el, f"{W}commentReference")
        ref_comment.set(f"{W}id", str(comment_id))

        paragraph.insert(0, start_el)
        paragraph.append(end_el)
        paragraph.append(ref_el)
        return True

    # ------------------------------------------------------------------
    # commentsExtended.xml 同步
    # ------------------------------------------------------------------

    def sync_comments_extended(self, docx_op) -> int:
        """
        为新添加的批注在 commentsExtended.xml 中创建对应的 commentEx 条目。

        Args:
            docx_op: DocxOperator 实例。

        Returns:
            新增的 commentEx 条目数。
        """
        if not self._new_comment_para_ids:
            return 0

        ce_root = docx_op.get_comments_extended()
        if ce_root is None:
            # 创建新的 commentsExtended.xml
            ce_root = ET.Element(f"{W15}commentsEx")
            docx_op.set_comments_extended(ce_root)

        # 收集已有的 paraId
        existing = set()
        for ex in ce_root:
            pid = ex.get(f"{W15}paraId")
            if pid:
                existing.add(pid)

        count = 0
        for comment_id, para_id in self._new_comment_para_ids:
            if para_id not in existing:
                ex = ET.SubElement(ce_root, f"{W15}commentEx")
                ex.set(f"{W15}paraId", para_id)
                ex.set(f"{W15}done", "0")
                count += 1

        if count > 0:
            # 标记 commentsExtended.xml 已修改，确保 save() 重新序列化
            docx_op.mark_modified("word/commentsExtended.xml")

        return count

    # ------------------------------------------------------------------
    # 便捷方法：添加段落批注（含 comments.xml + document.xml 范围标记）
    # ------------------------------------------------------------------

    def add_paragraph_comment(
        self,
        docx_op,
        paragraph: ET.Element,
        comment_text: str,
        target_text: str | None = None,
    ) -> int:
        """
        为指定段落添加批注。

        Args:
            docx_op: DocxOperator 实例。
            paragraph: <w:p> 元素。
            comment_text: 批注内容。
            target_text: 批注针对的具体文本；None 则针对整个段落。

        Returns:
            分配的批注 id。
        """
        # 确保 comments.xml 存在
        comments_root = docx_op.ensure_comments_xml_structure()

        # 同步起始 id（基于 comments.xml 中的最大 id）
        max_existing = self.find_max_comment_id(comments_root)
        if max_existing >= self._next_comment_id:
            self.set_start_id(max_existing + 1)

        # 添加批注内容（带 paraId + pStyle）
        comment_id = self.add_comment(comments_root, comment_text)

        # 在 document.xml 中插入范围标记
        self.inject_comment_range(paragraph, comment_id, target_text=target_text)

        return comment_id
