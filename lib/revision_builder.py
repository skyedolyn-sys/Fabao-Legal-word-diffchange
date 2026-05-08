"""
Open XML Track Changes 修订元素构建器。

支持创建 <w:ins>、<w:del> 及其内部的 <w:r>/<w:t> 结构。
处理命名空间、id 分配、作者和日期属性。

纯标准库实现：xml.etree, uuid, datetime
"""

import uuid
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _make_id() -> str:
    """生成唯一标识符（用于修订 id 和批注 id）。"""
    return str(uuid.uuid4().int % (2 ** 31))


def _now_iso() -> str:
    """生成当前时间的 ISO 8601 格式（带时区）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RevisionBuilder:
    """构建 Word track changes 所需的 XML 元素。"""

    def __init__(self, author: str = "Moonshot Legal"):
        self.author = author
        self._id_counter = 0

    def _next_id(self) -> int:
        """分配递增的修订 id（用于 w:id 属性）。"""
        self._id_counter += 1
        return self._id_counter

    def set_start_id(self, start: int) -> None:
        """手动设置起始 id（用于避免与文档中已有修订冲突）。"""
        self._id_counter = start

    def create_run(self, text: str, preserve_space: bool = True) -> ET.Element:
        """
        创建一个 <w:r> 元素，包含 <w:rPr>（可选）和 <w:t>。

        Args:
            text: 文本内容。
            preserve_space: 是否在 <w:t> 上设置 xml:space="preserve"。
        """
        r = ET.Element(f"{W}r")
        t = ET.SubElement(r, f"{W}t")
        t.text = text
        if preserve_space and (text.startswith(" ") or text.endswith(" ") or "  " in text):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return r

    def create_ins(self, text: str, ins_id: int | None = None) -> ET.Element:
        """
        创建一个 <w:ins> 元素，内部包含一个 <w:r><w:t>text</w:t></w:r>。

        Args:
            text: 要插入的文本。
            ins_id: 修订 id；None 则自动分配。

        Returns:
            <w:ins> Element
        """
        if ins_id is None:
            ins_id = self._next_id()

        ins = ET.Element(f"{W}ins")
        ins.set(f"{W}id", str(ins_id))
        ins.set(f"{W}author", self.author)
        ins.set(f"{W}date", _now_iso())

        r = self.create_run(text)
        ins.append(r)
        return ins

    def create_del(self, text: str, del_id: int | None = None) -> ET.Element:
        """
        创建一个 <w:del> 元素，内部包含一个 <w:r><w:delText>text</w:delText></w:r>。

        Args:
            text: 要删除的文本。
            del_id: 修订 id；None 则自动分配。

        Returns:
            <w:del> Element
        """
        if del_id is None:
            del_id = self._next_id()

        deletion = ET.Element(f"{W}del")
        deletion.set(f"{W}id", str(del_id))
        deletion.set(f"{W}author", self.author)
        deletion.set(f"{W}date", _now_iso())

        r = ET.SubElement(deletion, f"{W}r")
        del_text = ET.SubElement(r, f"{W}delText")
        del_text.text = text
        if text.startswith(" ") or text.endswith(" ") or "  " in text:
            del_text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return deletion

    def create_ins_with_multiple_runs(
        self, text_segments: list[str], ins_id: int | None = None
    ) -> ET.Element:
        """
        创建一个 <w:ins> 元素，内部包含多个 <w:r>（用于保留原始格式片段）。

        Args:
            text_segments: 文本片段列表，每个片段对应一个 <w:r><w:t>。
            ins_id: 修订 id；None 则自动分配。
        """
        if ins_id is None:
            ins_id = self._next_id()

        ins = ET.Element(f"{W}ins")
        ins.set(f"{W}id", str(ins_id))
        ins.set(f"{W}author", self.author)
        ins.set(f"{W}date", _now_iso())

        for seg in text_segments:
            r = self.create_run(seg)
            ins.append(r)
        return ins

    def create_del_with_multiple_runs(
        self, text_segments: list[str], del_id: int | None = None
    ) -> ET.Element:
        """
        创建一个 <w:del> 元素，内部包含多个 <w:r><w:delText>。

        Args:
            text_segments: 文本片段列表。
            del_id: 修订 id；None 则自动分配。
        """
        if del_id is None:
            del_id = self._next_id()

        deletion = ET.Element(f"{W}del")
        deletion.set(f"{W}id", str(del_id))
        deletion.set(f"{W}author", self.author)
        deletion.set(f"{W}date", _now_iso())

        for seg in text_segments:
            r = ET.SubElement(deletion, f"{W}r")
            del_text = ET.SubElement(r, f"{W}delText")
            del_text.text = seg
            if seg.startswith(" ") or seg.endswith(" ") or "  " in seg:
                del_text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            deletion.append(r)
        return deletion

    def create_paragraph_with_ins(self, text: str, para_id: int | None = None) -> ET.Element:
        """
        创建一个全新段落 <w:p>，内容为插入修订。

        Args:
            text: 段落文本。
            para_id: 段落属性中的 <w:pPr><w:pId> 值；None 则不设置。
        """
        p = ET.Element(f"{W}p")
        if para_id is not None:
            pPr = ET.SubElement(p, f"{W}pPr")
            pId = ET.SubElement(pPr, f"{W}pId")
            pId.set(f"{W}val", str(para_id))

        ins = self.create_ins(text)
        p.append(ins)
        return p

    def wrap_existing_text_with_ins(
        self, para: ET.Element, text_to_wrap: str, start_id: int | None = None
    ) -> bool:
        """
        在段落中找到匹配的文本，将其包装为 <w:ins>（保留周围的 runs）。

        这是**简单实现**：只查找第一个完全匹配的 <w:t> 文本节点，
        将其所在 <w:r> 替换为 <w:ins> 包裹的新结构。

        对于复杂场景（文本跨多个 runs），建议使用 replace_in_paragraph。

        Args:
            para: <w:p> 元素。
            text_to_wrap: 要包装为插入修订的文本。
            start_id: 起始修订 id。

        Returns:
            是否成功找到并包装。
        """
        if start_id is not None:
            self.set_start_id(start_id - 1)

        for r in para.iter(f"{W}r"):
            for t in r.iter(f"{W}t"):
                if t.text == text_to_wrap:
                    # 在段落中用 <w:ins> 替换这个 <w:r>
                    idx = list(para).index(r)
                    ins = self.create_ins(text_to_wrap)
                    para.remove(r)
                    para.insert(idx, ins)
                    return True
        return False

    def wrap_existing_text_with_del(
        self, para: ET.Element, text_to_wrap: str, start_id: int | None = None
    ) -> bool:
        """
        在段落中找到匹配的文本，将其包装为 <w:del>。

        Args:
            para: <w:p> 元素。
            text_to_wrap: 要包装为删除修订的文本。
            start_id: 起始修订 id。

        Returns:
            是否成功找到并包装。
        """
        if start_id is not None:
            self.set_start_id(start_id - 1)

        for r in para.iter(f"{W}r"):
            for t in r.iter(f"{W}t"):
                if t.text == text_to_wrap:
                    idx = list(para).index(r)
                    deletion = self.create_del(text_to_wrap)
                    para.remove(r)
                    para.insert(idx, deletion)
                    return True
        return False

    def replace_text_in_paragraph(
        self,
        para: ET.Element,
        old_text: str,
        new_text: str,
        start_id: int | None = None,
    ) -> bool:
        """
        在段落中将 old_text 替换为 new_text，通过 del + ins 实现。

        简单实现：查找第一个包含 old_text 的 <w:t>，
        将包含 old_text 的 <w:r> 替换为 <w:del>(old_text) + <w:ins>(new_text)。

        Args:
            para: <w:p> 元素。
            old_text: 要删除的文本。
            new_text: 要插入的文本。
            start_id: 起始修订 id。

        Returns:
            是否成功替换。
        """
        if start_id is not None:
            self.set_start_id(start_id - 1)

        for r in para.iter(f"{W}r"):
            for t in r.iter(f"{W}t"):
                if t.text and old_text in t.text:
                    idx = list(para).index(r)
                    # 创建 del + ins
                    deletion = self.create_del(old_text)
                    ins = self.create_ins(new_text)
                    para.remove(r)
                    para.insert(idx, deletion)
                    para.insert(idx + 1, ins)
                    return True
        return False

    @staticmethod
    def find_max_revision_id(doc_root: ET.Element) -> int:
        """
        扫描文档中已有的 <w:ins> 和 <w:del>，返回最大 w:id 值。
        用于确保新修订的 id 不会与已有修订冲突。
        """
        max_id = 0
        for tag in (f"{W}ins", f"{W}del"):
            for el in doc_root.iter(tag):
                rid = el.get(f"{W}id")
                if rid is not None:
                    try:
                        max_id = max(max_id, int(rid))
                    except ValueError:
                        pass
        return max_id
