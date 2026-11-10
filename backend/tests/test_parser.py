"""文档解析测试：只验证解析，不涉及 LLM / MySQL / Chroma。

样本文件由测试代码现场生成（不依赖仓库里的二进制样本），
PDF 用一个最小 PDF 构造器生成，避免引入 reportlab 之类的新依赖。

运行：
    conda run -n Langgraph pytest tests/test_parser.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge.parser import Chunk, ParseError, parse_document


# ===== 样本生成 =====


def _make_pdf(pages: list[str]) -> bytes:
    """构造一个最小可用的多页 PDF（Helvetica，仅 ASCII 文本）。

    只用于测试 pypdf 的文本提取和页码，不追求排版能力。
    """
    n = len(pages)
    page_ids = [4 + i * 2 for i in range(n)]
    content_ids = [5 + i * 2 for i in range(n)]

    objects: list[tuple[int, str]] = [
        (1, "<< /Type /Catalog /Pages 2 0 R >>"),
        (2, f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {n} >>"),
        (3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    for i, text in enumerate(pages):
        esc = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        stream = f"BT /F1 14 Tf 72 720 Td ({esc}) Tj ET"
        objects.append(
            (
                page_ids[i],
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_ids[i]} 0 R >>",
            )
        )
        objects.append(
            (content_ids[i], f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num, body in objects:
        offsets[num] = len(out)
        out += f"{num} 0 obj\n{body}\nendobj\n".encode("latin-1")

    xref_pos = len(out)
    max_num = max(num for num, _ in objects)
    out += f"xref\n0 {max_num + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, max_num + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {max_num + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _make_docx(path: Path, paragraphs: list[str], table: list[list[str]] | None = None) -> None:
    from docx import Document as DocxDocument

    doc = DocxDocument()
    for i, text in enumerate(paragraphs):
        if i == 0:
            doc.add_heading(text, level=1)
        else:
            doc.add_paragraph(text)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, val in enumerate(row):
                t.cell(r, c).text = val
    doc.save(str(path))


# ===== TXT / Markdown =====


def test_parse_txt(tmp_path: Path):
    f = tmp_path / "note.txt"
    f.write_text("这是第一段。\n\n这是第二段。", encoding="utf-8")

    chunks = parse_document(f)
    assert chunks, "应至少产生一个 chunk"
    assert all(isinstance(c, Chunk) for c in chunks)
    assert chunks[0].file_type == "txt"
    assert chunks[0].source == "note.txt"
    assert chunks[0].page_number is None
    assert "第一段" in "".join(c.text for c in chunks)


def test_parse_markdown(tmp_path: Path):
    f = tmp_path / "doc.md"
    f.write_text("# 标题\n\n正文内容。\n\n## 小节\n\n小节内容。", encoding="utf-8")

    chunks = parse_document(f)
    assert chunks
    assert chunks[0].file_type == "md"
    assert chunks[0].page_number is None
    joined = "".join(c.text for c in chunks)
    assert "标题" in joined and "小节内容" in joined


# ===== DOCX =====


def test_parse_docx_paragraphs(tmp_path: Path):
    f = tmp_path / "word.docx"
    _make_docx(f, ["文档标题", "这是正文第一段。", "这是正文第二段。"])

    chunks = parse_document(f)
    joined = "".join(c.text for c in chunks)
    assert chunks[0].file_type == "docx"
    assert "文档标题" in joined
    assert "正文第二段" in joined
    assert chunks[0].page_number is None


def test_parse_docx_table(tmp_path: Path):
    """表格内容必须被提取（不能只读 paragraphs）。"""
    f = tmp_path / "table.docx"
    _make_docx(f, ["含表格的文档"], table=[["姓名", "年龄"], ["张三", "30"]])

    chunks = parse_document(f)
    joined = "".join(c.text for c in chunks)
    assert "姓名" in joined
    assert "张三" in joined
    assert "30" in joined


def test_parse_docx_keeps_block_order(tmp_path: Path):
    """段落与表格按原始顺序出现，表格不能被统一挪到文末。"""
    f = tmp_path / "order.docx"
    _make_docx(f, ["开头段落"], table=[["表头A", "表头B"]])
    # 再追加一段，使它位于表格之后
    from docx import Document as DocxDocument

    doc = DocxDocument(str(f))
    doc.add_paragraph("结尾段落")
    doc.save(str(f))

    text = "\n".join(c.text for c in parse_document(f))
    assert text.index("开头段落") < text.index("表头A") < text.index("结尾段落")


def test_empty_docx_rejected(tmp_path: Path):
    """空文档必须报错，不能当成解析成功。"""
    f = tmp_path / "empty.docx"
    _make_docx(f, [], table=None)

    with pytest.raises(ParseError):
        parse_document(f)


# ===== PDF =====


def test_parse_pdf_multi_page(tmp_path: Path):
    f = tmp_path / "multi.pdf"
    f.write_bytes(_make_pdf(["Page one content", "Page two content"]))

    chunks = parse_document(f)
    joined = "".join(c.text for c in chunks)
    assert "Page one" in joined and "Page two" in joined
    assert chunks[0].file_type == "pdf"


def test_parse_pdf_page_numbers(tmp_path: Path):
    """每页的 chunk 必须带正确的页码（从 1 开始）。"""
    f = tmp_path / "pages.pdf"
    f.write_bytes(_make_pdf(["Alpha content", "Beta content", "Gamma content"]))

    chunks = parse_document(f)
    by_text = {}
    for c in chunks:
        for key in ("Alpha", "Beta", "Gamma"):
            if key in c.text:
                by_text[key] = c.page_number

    assert by_text.get("Alpha") == 1
    assert by_text.get("Beta") == 2
    assert by_text.get("Gamma") == 3


def test_pdf_without_text_rejected(tmp_path: Path):
    """纯空白页（模拟扫描版）应被拒绝，而不是返回空 chunk。"""
    f = tmp_path / "blank.pdf"
    f.write_bytes(_make_pdf([""]))

    with pytest.raises(ParseError) as ei:
        parse_document(f)
    assert "可提取的文本" in str(ei.value)


def test_corrupted_pdf_rejected(tmp_path: Path):
    """损坏 / 伪造的 PDF 必须抛 ParseError，不能崩栈。"""
    f = tmp_path / "broken.pdf"
    f.write_bytes(b"this is definitely not a pdf file")

    with pytest.raises(ParseError):
        parse_document(f)


# ===== 其他 =====


def test_unsupported_suffix_rejected(tmp_path: Path):
    for name in ("old.doc", "weird.xyz", "noext"):
        f = tmp_path / name
        f.write_text("content", encoding="utf-8")
        with pytest.raises(ParseError):
            parse_document(f)


def test_chunk_index_is_continuous(tmp_path: Path):
    """chunk_index 在整个文档内连续递增（保证 doc_id::chunk_index 不冲突）。"""
    f = tmp_path / "long.txt"
    f.write_text("段落内容。" * 400, encoding="utf-8")

    chunks = parse_document(f)
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
