"""D. 文档管理：列表、切换、上传、删除。"""
from __future__ import annotations

import pytest

from helpers import ApiMock, goto_app

pytestmark = pytest.mark.e2e

TXT_FILE = {"name": "笔记.txt", "mimeType": "text/plain", "buffer": b"hello world"}
MD_FILE = {"name": "说明.md", "mimeType": "text/markdown", "buffer": b"# title\nbody"}


def _goto_docs(page, mock_base_url, api):
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="nav-docs"]').click()
    page.wait_for_timeout(400)


def test_docs_table_lists_files(page, mock_base_url):
    api = ApiMock(page)
    kb = api.add_kb("库一")
    api.add_doc(kb["id"], "急救.pdf", 4)
    _goto_docs(page, mock_base_url, api)

    page.wait_for_selector('[data-testid="doc-row"]')
    assert page.locator('[data-testid="doc-row"]').count() == 1
    assert "急救.pdf" in page.locator('[data-testid="doc-row"]').inner_text()


def test_switch_kb_changes_table(page, mock_base_url):
    api = ApiMock(page)
    kb1 = api.add_kb("库一")
    kb2 = api.add_kb("库二")
    api.add_doc(kb1["id"], "一号.md")
    api.add_doc(kb2["id"], "二号.md", 5)
    _goto_docs(page, mock_base_url, api)

    page.select_option('[data-testid="kb-select"]', str(kb2["id"]))
    page.wait_for_timeout(500)

    text = page.locator('[data-testid="doc-row"]').inner_text()
    assert "二号.md" in text
    assert "一号.md" not in text


def test_upload_txt(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("库一")
    _goto_docs(page, mock_base_url, api)

    page.set_input_files('input[type="file"]', TXT_FILE)
    page.wait_for_timeout(600)

    assert api.called("POST", "/documents/upload")
    assert "笔记.txt" in page.locator('[data-testid="doc-row"]').inner_text()


def test_upload_markdown(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("库一")
    _goto_docs(page, mock_base_url, api)

    page.set_input_files('input[type="file"]', MD_FILE)
    page.wait_for_timeout(600)

    assert "说明.md" in page.locator('[data-testid="doc-row"]').inner_text()


def test_chunk_count_rendered_from_api(page, mock_base_url):
    api = ApiMock(page)
    kb = api.add_kb("库一")
    api.add_doc(kb["id"], "多块.md", 7)
    _goto_docs(page, mock_base_url, api)

    page.wait_for_selector('[data-testid="doc-row"]')
    cells = page.locator('[data-testid="doc-row"] td').all_inner_texts()
    assert "7" in cells


def test_upload_refreshes_table_and_subtitle(page, mock_base_url):
    api = ApiMock(page)
    kb = api.add_kb("库一")
    api.add_doc(kb["id"], "已存在.md", 2)
    _goto_docs(page, mock_base_url, api)
    page.wait_for_selector('[data-testid="doc-row"]')
    before = page.locator('[data-testid="doc-row"]').count()

    page.set_input_files('input[type="file"]', TXT_FILE)
    page.wait_for_timeout(700)

    after = page.locator('[data-testid="doc-row"]').count()
    assert after == before + 1
    # 上传返回 chunk_count=3，加上原有 2 块，副标题应立即刷新为 2 篇 / 5 块
    subtitle = page.locator(".page-sub").inner_text()
    assert "2 个文档" in subtitle
    assert "5 个文本块" in subtitle


def test_delete_cancel_keeps_row(page, mock_base_url):
    api = ApiMock(page)
    kb = api.add_kb("库一")
    api.add_doc(kb["id"], "别删.md", 1)
    _goto_docs(page, mock_base_url, api)
    page.wait_for_selector('[data-testid="doc-row"]')

    page.locator('[data-testid="doc-delete"]').first.click()
    page.wait_for_selector('[data-testid="confirm"]')
    page.locator('[data-testid="confirm-cancel"]').click()
    page.wait_for_timeout(300)

    assert not api.called("DELETE", "/documents/")
    assert page.locator('[data-testid="doc-row"]').count() == 1


def test_delete_confirm_removes_row(page, mock_base_url):
    api = ApiMock(page)
    kb = api.add_kb("库一")
    api.add_doc(kb["id"], "删我.md", 1)
    _goto_docs(page, mock_base_url, api)
    page.wait_for_selector('[data-testid="doc-row"]')

    page.locator('[data-testid="doc-delete"]').first.click()
    page.wait_for_selector('[data-testid="confirm"]')
    page.locator('[data-testid="confirm-ok"]').click()
    page.wait_for_timeout(600)

    assert api.called("DELETE", "/documents/")
    assert page.locator('[data-testid="doc-row"]').count() == 0


def test_upload_failure_shows_error_toast(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("库一")
    api.upload_error = (400, "文档解析失败，请检查文件内容")
    _goto_docs(page, mock_base_url, api)

    page.set_input_files('input[type="file"]', TXT_FILE)
    page.wait_for_selector('[data-testid="toast"]', timeout=5000)

    toast = page.locator('[data-testid="toast"][data-type="err"]').first
    assert "文档解析失败" in toast.inner_text()
    assert page.locator('[data-testid="doc-row"]').count() == 0
