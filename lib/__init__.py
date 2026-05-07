# Kimi法宝 — 写入能力库模块
"""
通用 DOCX 操作封装，支持 Word track changes 和 comments 的读取与写入。

纯标准库实现（zipfile, xml.etree, shutil, json, os, re, pathlib, datetime, uuid）。
"""

from .docx_operator import DocxOperator
from .revision_builder import RevisionBuilder
from .comment_injector import CommentInjector

__all__ = ["DocxOperator", "RevisionBuilder", "CommentInjector"]
