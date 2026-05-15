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

# 额外注册 Word XML 中实际使用的命名空间前缀
# 注意：不注册 Content_Types 和 Relationships 的 URI，
# 因为这些文件要求使用默认（无前缀）命名空间，
# 而 ET.register_namespace 是全局的，会导致序列化时添加前缀。
EXTRA_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "o": "urn:schemas-microsoft-com:office:office",
    "v": "urn:schemas-microsoft-com:vml",
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "cx1": "http://schemas.microsoft.com/office/drawing/2015/9/8/chartex",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
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
        self._modified: set[str] = set()   # 仅被修改的 XML 才需要重新序列化
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

    def get_comments_extended(self) -> ET.Element | None:
        """返回 commentsExtended.xml 的根元素；如不存在则返回 None。"""
        tree = self._tree.get("word/commentsExtended.xml")
        return tree.getroot() if tree else None

    def get_styles(self) -> ET.Element | None:
        """返回 styles.xml 的根元素；如不存在则返回 None。"""
        tree = self._tree.get("word/styles.xml")
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
        self._modified.add("word/document.xml")

    def set_comments(self, root: ET.Element) -> None:
        """替换或新增 comments.xml 的内容。"""
        self._tree["word/comments.xml"] = ET.ElementTree(root)
        self._modified.add("word/comments.xml")
        if "word/comments.xml" not in self._namelist:
            self._namelist.append("word/comments.xml")

    def set_settings(self, root: ET.Element) -> None:
        """替换 settings.xml 的内容。"""
        self._tree["word/settings.xml"] = ET.ElementTree(root)
        self._modified.add("word/settings.xml")

    def set_comments_extended(self, root: ET.Element) -> None:
        """替换或新增 commentsExtended.xml 的内容。"""
        self._tree["word/commentsExtended.xml"] = ET.ElementTree(root)
        self._modified.add("word/commentsExtended.xml")
        if "word/commentsExtended.xml" not in self._namelist:
            self._namelist.append("word/commentsExtended.xml")

    # ------------------------------------------------------------------
    # 辅助功能
    # ------------------------------------------------------------------

    def mark_modified(self, part_name: str) -> None:
        """手动标记某个 part 已修改，使 save() 重新序列化它。
        用于通过 get_document() 获取根元素后就地修改的情况。
        """
        self._modified.add(part_name)

    def _ensure_rels_entry(self, rel_type: str, target: str) -> None:
        """确保 word/_rels/document.xml.rels 中存在指定类型的关系。"""
        rels_path = "word/_rels/document.xml.rels"
        rels_tree = self._tree.get(rels_path)
        ns = "http://schemas.openxmlformats.org/package/2006/relationships"

        if rels_tree is None:
            root = ET.Element(f"{{{ns}}}Relationships")
            rels_tree = ET.ElementTree(root)
            self._tree[rels_path] = rels_tree
            if rels_path not in self._namelist:
                self._namelist.append(rels_path)
        else:
            root = rels_tree.getroot()

        # 检查是否已存在
        for rel in root.iter(f"{{{ns}}}Relationship"):
            if rel.get("Type") == rel_type:
                return  # 已存在，无需修改

        # 计算新 rId
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
        rel.set("Type", rel_type)
        rel.set("Target", target)
        self._modified.add(rels_path)  # 标记已修改

    def ensure_comments_part(self) -> None:
        """确保文档包含 comments.xml 关系。"""
        self._ensure_rels_entry(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
            "comments.xml"
        )

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
                self._modified.add("word/settings.xml")
                return

        tr = ET.SubElement(root, f"{W}trackRevisions")
        tr.set(f"{W}val", "true")
        self._modified.add("word/settings.xml")

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

        仅对 _modified 中的 XML part 重新序列化，其余保留原始字节。
        对修改的 XML 保留原始 XML 声明和根元素开始标签（含所有命名空间声明），
        避免 ElementTree 丢弃命名空间导致 Word 报错。

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

        # 确保 comments / commentsExtended 关系存在
        if "word/comments.xml" in self._modified:
            self.ensure_comments_part()
        if "word/commentsExtended.xml" in self._modified:
            self._ensure_rels_entry(
                "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
                "commentsExtended.xml"
            )

        # 确保新 part 在 [Content_Types].xml 中有 override 声明
        self._ensure_content_type_overrides()

        import io

        # 构建写入顺序：[Content_Types].xml 必须在 ZIP 中排第一位
        # 某些 Word 版本要求 [Content_Types].xml 是 ZIP 中的第一个条目
        ordered_namelist = list(self._namelist)
        if "[Content_Types].xml" in ordered_namelist:
            ordered_namelist.remove("[Content_Types].xml")
            ordered_namelist.insert(0, "[Content_Types].xml")

        # 确保 _modified 中的文件都在 namelist 中（防止新创建的文件遗漏）
        for name in self._modified:
            if name not in ordered_namelist:
                ordered_namelist.append(name)

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ordered_namelist:
                if name in self._modified and name in self._tree:
                    xml_bytes = self._serialize_preserving_header(name)
                    zf.writestr(name, xml_bytes)
                elif name in self._raw:
                    zf.writestr(name, self._raw[name])
                else:
                    # 兜底：_modified 中有但 _raw 中没有的全新文件
                    if name in self._tree:
                        xml_bytes = self._serialize_preserving_header(name)
                        zf.writestr(name, xml_bytes)

        return str(target)

    def _serialize_preserving_header(self, name: str) -> bytes:
        """
        序列化已修改的 XML，但保留原始 XML 声明和根元素开始标签。

        ElementTree 序列化时会丢弃"未使用"的命名空间声明，
        但 Word 要求根元素上的所有原始 xmlns 必须保留。
        方法：用原始文件的 header（XML 声明 + 根开始标签）替换 ET 生成的。
        对 .rels 文件额外处理 ET 自动添加的 ns0: 前缀问题。
        """
        import io, re

        tree = self._tree[name]
        buf = io.BytesIO()
        tree.write(buf, encoding="UTF-8", xml_declaration=True)
        new_xml = buf.getvalue().decode("utf-8")

        # 对 package-level 文件（.rels 和 [Content_Types].xml）：
        # ElementTree 会将默认命名空间的元素序列化为 ns0: 前缀
        # 需要全局替换回无前缀形式
        if name.endswith(".rels"):
            new_xml = new_xml.replace("ns0:", "")
            new_xml = new_xml.replace('xmlns:ns0="http://schemas.openxmlformats.org/package/2006/relationships"',
                                      'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"')
            return new_xml.encode("utf-8")
        if name == "[Content_Types].xml":
            new_xml = new_xml.replace("ns0:", "")
            new_xml = new_xml.replace('xmlns:ns0="http://schemas.openxmlformats.org/package/2006/content-types"',
                                      'xmlns="http://schemas.openxmlformats.org/package/2006/content-types"')
            return new_xml.encode("utf-8")

        # 如果有原始字节，提取原始 header 替换 ET 生成的
        if name in self._raw:
            orig_xml = self._raw[name].decode("utf-8")

            # 正则提取: XML 声明 + 根元素开始标签
            # 匹配 <?xml ...?> 然后 <tagname attr1="..." attr2="..." ...>
            header_re = re.compile(r'(<\?xml[^?]*\?>\s*<[^>]+>)', re.DOTALL)

            orig_match = header_re.search(orig_xml)
            new_match = header_re.search(new_xml)

            if orig_match and new_match:
                # 原始 header + ET 生成的 body（根开始标签之后的内容）
                orig_header = orig_match.group(1)
                # 修复自闭合根元素：将 /> 转为 >，否则追加子元素后 XML 非法
                if orig_header.rstrip().endswith('/>'):
                    orig_header = orig_header.rstrip()[:-2].rstrip() + '>'

                # 关键修复：原始文件可能在子元素上声明了命名空间，
                # 导致根元素 header 中缺少这些声明。
                # ElementTree 序列化时会将其提升到根元素上，
                # 因此从 ET 生成的 header 中提取原始 header 缺失的命名空间声明并补充。
                new_header = new_match.group(1)
                orig_ns_set = set(re.findall(r'xmlns:[a-zA-Z0-9_]+="[^"]*"', orig_header))
                new_ns_list = re.findall(r'xmlns:[a-zA-Z0-9_]+="[^"]*"', new_header)
                additions = [ns for ns in new_ns_list if ns not in orig_ns_set]
                if additions:
                    # 在 orig_header 最后一个引号后插入缺失的命名空间声明
                    insert_pos = orig_header.rfind('"')
                    if insert_pos > 0:
                        orig_header = (
                            orig_header[:insert_pos + 1]
                            + " "
                            + " ".join(additions)
                            + orig_header[insert_pos + 1:]
                        )

                return (orig_header + new_xml[new_match.end():]).encode("utf-8")

        # 回退：直接返回 ET 输出
        return new_xml.encode("utf-8")

    def _ensure_content_type_overrides(self) -> None:
        """确保 [Content_Types].xml 中包含所有新增 part 的 Override 声明。"""
        ct_path = "[Content_Types].xml"
        ct_tree = self._tree.get(ct_path)
        if ct_tree is None:
            return

        root = ct_tree.getroot()
        ns = "http://schemas.openxmlformats.org/package/2006/content-types"

        # 需要注册的 part
        required_overrides = {
            "/word/comments.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
            "/word/commentsExtended.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml",
            "/word/settings.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml",
        }

        # 收集已存在的 PartName
        existing = set()
        for override in root.iter(f"{{{ns}}}Override"):
            existing.add(override.get("PartName"))

        added = False
        for part_name, content_type in required_overrides.items():
            if part_name not in existing and part_name[1:] in self._namelist:
                override = ET.SubElement(root, f"{{{ns}}}Override")
                override.set("PartName", part_name)
                override.set("ContentType", content_type)
                added = True

        if added:
            self._modified.add(ct_path)

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
