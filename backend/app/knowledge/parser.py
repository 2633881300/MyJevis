"""文档解析与分段：支持 txt / md / docx / 文本型 pdf。

设计：
  - 对外接口保持不变：parse_document(path) -> list[Chunk]
  - 按扩展名分派到独立的提取函数，每个格式一个函数，互不干扰
  - 提取函数统一返回 [(文本, 页码或None)]，PDF 有页码，其余为 None
  - 分块仍用 RecursiveCharacterTextSplitter，按「片段」分别切分，
    这样 PDF 的每一页都能保留自己的页码

不支持：.doc（旧格式）、扫描版 PDF（需要 OCR）、图片/公式/复杂排版还原。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

CHUNK_SIZE = 300
CHUNK_OVERLAP = 50

SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".docx", ".pdf"}


class ParseError(ValueError):
    """文档无法解析：格式不支持、内容为空、文件损坏、需要密码等。"""


@dataclass
class Chunk:
    """一个文本块,知识库的最小单元"""

    text: str
    source: str
    chunk_index: int
    file_type: str = ""
    page_number: int | None = None   # PDF 页码，从 1 开始；其他格式为 None


# ===== 各格式的文本提取 =====


def _extract_plain(path: Path) -> list[tuple[str, int | None]]:
    """txt / md / markdown：整篇作为一个片段。"""
    try:
        return [(path.read_text(encoding="utf-8"), None)]
    except UnicodeDecodeError as e:
        raise ParseError("文本文件编码无法识别（请使用 UTF-8）") from e


def _iter_docx_blocks(doc):
    """按文档原始顺序产出段落和表格。

    python-docx 的 doc.paragraphs / doc.tables 是两个独立列表，会打乱原始顺序。
    所以遍历 body 的 XML 子元素，逐个判断是段落还是表格。
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def _extract_docx(path: Path) -> list[tuple[str, int | None]]:
    """Word：段落 + 表格，按原始顺序拼接。表格用制表符分隔单元格。"""
    from docx import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        doc = DocxDocument(str(path))
    except Exception as e:  # noqa: BLE001  损坏的 docx / 不是 zip
        raise ParseError(f"Word 文档解析失败（文件可能已损坏）") from e

    parts: list[str] = []
    for block in _iter_docx_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                parts.append(text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    parts.append("\t".join(cells))

    return [("\n".join(parts), None)]


def _extract_pdf(path: Path) -> list[tuple[str, int | None]]:
    """PDF：逐页提取，保留页码（从 1 开始）。只支持有文本层的 PDF。"""
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception as e:  # noqa: BLE001  损坏 / 不是 PDF
        raise ParseError("PDF 文件损坏或不是有效的 PDF") from e

    # 加密 PDF：尝试空密码，失败则拒绝
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                raise ParseError("PDF 已加密，需要密码才能解析")
        except ParseError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ParseError("PDF 已加密，需要密码才能解析") from e

    segments: list[tuple[str, int | None]] = []
    failed_pages: list[int] = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001  单页失败不影响其他页
            failed_pages.append(page_no)
            text = ""
        text = text.strip()
        if text:
            segments.append((text, page_no))

    # 不静默吞掉失败：记录页码，便于排查 PDF 质量问题
    if failed_pages:
        logger.warning(
            "PDF %s 有 %d 页文本提取失败，已跳过：%s",
            path.name, len(failed_pages), failed_pages,
        )
    return segments


_EXTRACTORS = {
    ".txt": _extract_plain,
    ".md": _extract_plain,
    ".markdown": _extract_plain,
    ".docx": _extract_docx,
    ".pdf": _extract_pdf,
}


# ===== 对外接口 =====


def _make_splitter() -> RecursiveCharacterTextSplitter:
    """分块器：优先在 Markdown 标题处断开，其次段落、句子、空格。"""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", "！", "？", " ", ""],
    )


def parse_document(
    path: str | Path,
    source_name: str | None = None,
) -> list[Chunk]:
    """读取一个文档并切分为文本块。

    Args:
        path: 服务器上的临时文件路径（上传时会用 uuid 重命名）。
        source_name: 写入 chunk.source 的展示名。
            上传场景应传用户原始文件名；不传则退化为临时文件名。

    失败时抛 ParseError（调用方据此返回 400，且不产生任何数据库/向量记录）。
    """
    p = Path(path)
    suffix = p.suffix.lower()

    extractor = _EXTRACTORS.get(suffix)
    if extractor is None:
        raise ParseError(f"暂不支持的文档类型：{suffix or '无扩展名'}")

    # 来源名优先用调用方给的真实文件名，避免落进 uuid 临时名
    source = source_name or p.name

    segments = extractor(p)          # [(文本, 页码|None)]
    splitter = _make_splitter()

    chunks: list[Chunk] = []
    for text, page_no in segments:
        for piece in splitter.split_text(text):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                Chunk(
                    text=piece,
                    source=source,
                    chunk_index=len(chunks),     # 全文档连续编号
                    file_type=suffix.lstrip("."),
                    page_number=page_no,
                )
            )

    if not chunks:
        raise ParseError(
            "文档中没有可提取的文本。如果是 PDF，可能是扫描版（纯图片），暂不支持 OCR。"
        )
    return chunks
