"""J. 时间显示与异常状态。"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from helpers import ApiMock, ask, goto_app

pytestmark = pytest.mark.e2e


def test_utc_timestamp_converted_to_local(page, mock_base_url):
    """后端存的是 naive UTC，页面应显示为本地时间（Asia/Shanghai +8）。"""
    api = ApiMock(page)
    kb = api.add_kb("库一")
    api.add_doc(kb["id"], "时间.md", 1, created_at="2026-11-08T11:27:00")
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="nav-docs"]').click()
    page.wait_for_selector('[data-testid="doc-row"]')

    assert "2026-11-08 19:27" in page.locator('[data-testid="doc-row"]').inner_text()


def test_message_clock_is_local_hhmm(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("库一")
    goto_app(page, mock_base_url, token="t")

    ask(page, "时间测试")
    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("流式回答")

    meta = page.locator('[data-testid="msg"][data-role="assistant"] .msg-meta').last.inner_text()
    assert re.search(r"\d{2}:\d{2}", meta)


def test_empty_document_list_state(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("空库")
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="nav-docs"]').click()
    page.wait_for_timeout(500)

    assert page.locator('[data-testid="doc-row"]').count() == 0
    assert "还没有文档" in page.locator(".page-scroll").inner_text()


def test_kb_list_404_shows_error(page, mock_base_url):
    api = ApiMock(page)
    api.kb_list_error = (404, "资源不存在")
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="nav-kbs"]').click()
    page.wait_for_timeout(600)

    assert "资源不存在" in page.locator(".page-scroll").inner_text()


def test_document_list_500_shows_error(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("库一")
    api.doc_list_error = (500, "服务暂时不可用")
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="nav-docs"]').click()
    page.wait_for_timeout(600)

    body = page.locator(".page-scroll").inner_text()
    assert "服务暂时不可用" in body or "暂时不可用" in body


def test_upload_403_message(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("库一")
    api.upload_error = (403, "没有权限执行该操作")
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="nav-docs"]').click()
    page.wait_for_timeout(400)

    page.set_input_files('input[type="file"]', {"name": "x.txt", "mimeType": "text/plain", "buffer": b"x"})
    page.wait_for_selector('[data-testid="toast"]', timeout=5000)
    assert "没有权限" in page.locator('[data-testid="toast"]').first.inner_text()
