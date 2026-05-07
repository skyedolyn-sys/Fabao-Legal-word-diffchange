"""
DOCX 文件操作封装 — 支持 ZIP 解压/打包、XML 读写、备份。

纯标准库实现：zipfile, xml.etree, shutil, os, pathlib, datetime
"""

import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


# WordprocessingML 命名空间
NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}

# 注册命名空间以保持序列化时前缀一致
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)

# 额外注册常见命名空间
EXTRA_NS = {
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "ve": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "o": "urn:schemas-microsoft-com:office:office",
    "v": "urn:schemas-microsoft-com:vml",
}
for prefix, uri in EXTRA_NS.items():
    ET.register_namespace(prefix, uri)


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def get_text(element: ET.Element) -> str:
    """提取元素及其子元素中的所有文本。"""
    parts = []
    for t in element.iter(f"{W}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def set_text(element: ET.Element, text: str) -> None:
    """设置元素中第一个 <w:t> 的文本（如没有则创建）。"""
    t_el = element.find(f"{W}t")
    if t_el is None:
        t_el = ET.SubElement(element, f"{W}t")
    t_el.text = text


class DocxOperator:
    """封装 DOCX 的读取、解压、修改、重新打包操作。"""

    def __init__(self, docx_path: str):
        self.docx_path = Path(docx_path)
        if not self.docx_path.exists():
            raise FileNotFoundError(f"DOCX not found: {docx_path}")
        self._tree: dict[str, ET.ElementTree] = {}
        self._raw: dict[str, bytes] = {}
        self._namelist: list[str] = []
        self._load()

    def _load(self) -> None:
        """将 DOCX 解压到内存，解析所有 XML 文件。"""
        with zipfile.ZipFile(self.docx_path, "r") as zf:
            self._namelist = zf.namelist()
            for name in self._namelist:
                data = zf.read(name)
                self._raw[name] = data
                if name.endswith(".xml") or name.endswith(".rels"):
                    try:
                        self._tree[name] = ET.parse(zf.open(name))
                    except ET.ParseError:
                        pass  # 保持原始字节

    # ------------------------------------------------------------------
    # 读取接口
    # ------------------------------------------------------------------

    def get_document(self) -> ET.Element:
        """返回 document.xml 的根元素。"""
        tree = self._tree.get("word/document.xml")
        if tree is None:
            raise ValueError("word/document.xml not found")
        return tree.getroot()

    def get_comments(self) -> ET.Element | None:
        """返回 comments.xml 的根元素；如不存在则返回 None。"""
        tree = self._tree.get("word/comments.xml")
        return tree.getroot() if tree else None

    def get_settings(self) -> ET.Element | None:
        """返回 settings.xml 的根元素；如不存在则返回 None。"""
        tree = self._tree.get("word/settings.xml")
        return tree.getroot() if tree else None

    def get_body(self) -> ET.Element:
        """返回 document.xml 中的 <w:body>。"""
        root = self.get_document()
        body = root.find(f".//{W}body")
        if body is None:
            raise ValueError("<w:body> not found in document.xml")
        return body

    def get_paragraphs(self) -> list[ET.Element]:
        """返回 document.xml 中所有 <w:p> 段落元素。"""
        return list(self.get_body().iter(f"{W}p"))

    def get_paragraph_text(self, para: ET.Element) -> str:
        """返回段落的纯文本。"""
        return get_text(para)

    # ------------------------------------------------------------------
    # 写入接口
    # ------------------------------------------------------------------

    def set_document(self, root: ET.Element) -> None:
        """替换 document.xml 的内容。"""
        self._tree["word/document.xml"] = ET.ElementTree(root)

    def set_comments(self, root: ET.Element) -> None:
        """替换或新增 comments.xml 的内容。"""
        self._tree["word/comments.xml"] = ET.ElementTree(root)
        if "word/comments.xml" not in self._namelist:
            self._namelist.append("word/comments.xml")

    def set_settings(self, root: ET.Element) -> None:
        """替换 settings.xml 的内容。"""
        self._tree["word/settings.xml"] = ET.ElementTree(root)

    # ------------------------------------------------------------------
    # 辅助功能
    # ------------------------------------------------------------------

    def ensure_comments_part(self) -> None:
        """
        确保文档包含 comments.xml 关系。
        如果 word/_rels/document.xml.rels 中没有 comments 关系，则添加。
        """
        rels_path = "word/_rels/document.xml.rels"
        rels_tree = self._tree.get(rels_path)
        if rels_tree is None:
            # 创建新的 rels 文件
            root = ET.Element(
                "{http://schemas.openxmlformats.org/package/2006/relationships}Relationships"
            )
            rels_tree = ET.ElementTree(root)
            self._tree[rels_path] = rels_tree
            self._namelist.append(rels_path)
        else:
            root = rels_tree.getroot()

        ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        # 检查是否已有 comments 关系
        for rel in root.iter(f"{{{ns}}}Relationship"):
            if rel.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments":
                return

        # 计算新的 rId
        existing_ids = []
        for rel in root.iter(f"{{{ns}}}Relationship"):
            rid = rel.get("Id", "")
            if rid.startswith("rId"):
                try:
                    existing_ids.append(int(rid[3:]))
                except ValueError:
                    pass
        new_id = max(existing_ids) + 1 if existing_ids else 1

        rel = ET.SubElement(root, f"{{{ns}}}Relationship")
        rel.set("Id", f"rId{new_id}")
        rel.set(
            "Type",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
        )
        rel.set("Target", "comments.xml")

    def ensure_track_changes_enabled(self) -> None:
        """
        在 settings.xml 中启用 track changes（<w:trackRevisions w:val="true"/>）。
        如 settings.xml 不存在则创建。
        """
        settings_tree = self._tree.get("word/settings.xml")
        if settings_tree is None:
            root = ET.Element(f"{W}settings")
            settings_tree = ET.ElementTree(root)
            self._tree["word/settings.xml"] = settings_tree
            if "word/settings.xml" not in self._namelist:
                self._namelist.append("word/settings.xml")
        else:
            root = settings_tree.getroot()

        # 检查是否已有 trackRevisions
        for child in root:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "trackRevisions":
                child.set(f"{W}val", "true")
                return

        tr = ET.SubElement(root, f"{W}trackRevisions")
        tr.set(f"{W}val", "true")

    def ensure_comments_xml_structure(self) -> ET.Element:
        """
        确保 comments.xml 存在且有正确的根元素。
        返回 comments.xml 的根元素。
        """
        root = self.get_comments()
        if root is None:
            root = ET.Element(f"{W}comments")
            self.set_comments(root)
        return root

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------

    def save(self, output_path: str | None = None, backup: bool = True) -> str:
        """
        将修改后的内容重新打包为 DOCX。

        Args:
            output_path: 输出路径；None 则覆盖原文件。
            backup: 是否先备份原文件。

        Returns:
            最终保存的文件路径。
        """
        target = Path(output_path) if output_path else self.docx_path

        if backup and not output_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.docx_path.with_suffix(f".backup_{ts}.docx")
            shutil.copy2(self.docx_path, backup_path)

        # 确保 comments 关系存在
        if "word/comments.xml" in self._tree:
            self.ensure_comments_part()

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in self._namelist:
                if name in self._tree:
                    # XML 文件：序列化 ElementTree
                    tree = self._tree[name]
                    # 添加 XML 声明
                    import io
                    buf = io.BytesIO()
                    tree.write(buf, encoding="UTF-8", xml_declaration=True)
                    zf.writestr(name, buf.getvalue())
                else:
                    # 非 XML 文件：保持原始字节
                    zf.writestr(name, self._raw[name])

        return str(target)

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """基础校验：检查 document.xml 是否存在且可解析。"""
        errors = []
        if "word/document.xml" not in self._tree:
            errors.append("Missing word/document.xml")
        else:
            body = self.get_body()
            if body is None:
                errors.append("Missing <w:body> in document.xml")
        return errors
