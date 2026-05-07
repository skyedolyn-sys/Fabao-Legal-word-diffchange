"""
Word 批注（Comments）注入器。

支持：
1. 读取/写入 comments.xml
2. 在 document.xml 中插入 commentRangeStart / commentRangeEnd / commentReference
3. 自动分配批注 id

纯标准库实现：xml.etree, datetime, re
"""

import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CommentInjector:
    """管理 Word 文档中的批注（comments）。"""

    def __init__(self, author: str = "Moonshot Legal"):
        self.author = author
        self._next_comment_id = 0

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

        # 批注内容段落
        p = ET.SubElement(comment_el, f"{W}p")
        r = ET.SubElement(p, f"{W}r")
        t = ET.SubElement(r, f"{W}t")
        t.text = text
        if text.startswith(" ") or text.endswith(" "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

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
                    ref_style.set(f"{W}val", "CommentReference")
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
        ref_style.set(f"{W}val", "CommentReference")
        ref_comment = ET.SubElement(ref_el, f"{W}commentReference")
        ref_comment.set(f"{W}id", str(comment_id))

        paragraph.insert(0, start_el)
        paragraph.append(end_el)
        paragraph.append(ref_el)
        return True

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

        # 同步起始 id
        max_existing = self.find_max_comment_id(comments_root)
        if max_existing >= self._next_comment_id:
            self.set_start_id(max_existing + 1)

        # 添加批注内容
        comment_id = self.add_comment(comments_root, comment_text)

        # 在 document.xml 中插入范围标记
        self.inject_comment_range(paragraph, comment_id, target_text=target_text)

        return comment_id
