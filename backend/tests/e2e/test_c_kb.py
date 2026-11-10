"""C. 知识库管理：创建、选择、改名、公开切换、删除。"""
from __future__ import annotations

import pytest

from helpers import ApiMock, goto_app

pytestmark = pytest.mark.e2e


def _open_create(page):
    page.locator('[data-testid="kb-add"]').click()
    page.wait_for_selector('[data-testid="kb-form"]')


def _submit_form(page):
    page.locator('[data-testid="kb-form-submit"]').click()


def test_create_private_kb(page, mock_base_url):
    api = ApiMock(page)
    goto_app(page, mock_base_url, token="t")

    _open_create(page)
    page.locator('[data-testid="kb-form-name"]').fill("私有笔记")
    page.locator('[data-testid="kb-form-desc"]').fill("操作系统复习")
    _submit_form(page)

    page.wait_for_selector('[data-testid="kb-item"]')
    assert api.called("POST", "/knowledge-bases")
    assert "私有笔记" in page.locator('[data-testid="kb-item"]').inner_text()
    assert "私有" in page.locator('[data-testid="kb-item"]').inner_text()


def test_create_name_required(page, mock_base_url):
    api = ApiMock(page)
    goto_app(page, mock_base_url, token="t")

    _open_create(page)
    _submit_form(page)

    assert "请填写知识库名称" in page.locator('[data-testid="kb-form-error"]').inner_text()
    assert not api.called("POST", "/knowledge-bases")


def test_sidebar_and_card_stay_in_sync(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("已有库")
    goto_app(page, mock_base_url, token="t")

    _open_create(page)
    page.locator('[data-testid="kb-form-name"]').fill("新库")
    _submit_form(page)
    page.wait_for_timeout(300)

    assert page.locator('[data-testid="kb-item"]').count() == 2

    page.locator('[data-testid="nav-kbs"]').click()
    page.wait_for_timeout(400)
    assert page.locator('[data-testid="kb-card"]').count() == 2


def test_select_kb_updates_header(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("库一")
    api.add_kb("库二")
    goto_app(page, mock_base_url, token="t")

    page.locator('[data-testid="kb-item"][data-kb-id="2"]').click()
    page.wait_for_timeout(200)

    assert "库二" in page.locator('[data-testid="kb-switch"]').inner_text()


def test_rename_kb_updates_sidebar(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("旧名字")
    goto_app(page, mock_base_url, token="t")

    page.locator('[data-testid="kb-more"]').first.click()
    page.locator('[data-testid="kb-menu-edit"]').click()
    page.wait_for_selector('[data-testid="kb-form"]')

    page.locator('[data-testid="kb-form-name"]').fill("新名字")
    page.locator('[data-testid="kb-form-desc"]').fill("补充描述")
    _submit_form(page)
    page.wait_for_timeout(400)

    assert api.called("PATCH", "/knowledge-bases/1")
    assert "新名字" in page.locator('[data-testid="kb-item"]').inner_text()


def test_toggle_public_from_card(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("待公开", description="测试用")
    goto_app(page, mock_base_url, token="t")

    page.locator('[data-testid="nav-kbs"]').click()
    page.wait_for_selector('[data-testid="kb-card"]')

    page.get_by_role("button", name="转公开").click()
    page.wait_for_timeout(400)

    assert api.called("PATCH", "/knowledge-bases/1")
    assert "公开" in page.locator('[data-testid="kb-card"]').inner_text()


def test_delete_cancel_keeps_kb(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("别删我")
    goto_app(page, mock_base_url, token="t")

    page.locator('[data-testid="kb-more"]').first.click()
    page.locator('[data-testid="kb-menu-delete"]').click()
    page.wait_for_selector('[data-testid="confirm"]')

    assert "不可恢复" in page.locator('[data-testid="confirm-message"]').inner_text()
    page.locator('[data-testid="confirm-cancel"]').click()
    page.wait_for_timeout(300)

    assert not api.called("DELETE", "/knowledge-bases")
    assert page.locator('[data-testid="kb-item"]').count() == 1
    assert "别删我" in page.locator('[data-testid="kb-item"]').inner_text()


def test_delete_confirm_removes_kb(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("要删的")
    api.add_kb("留下的")
    goto_app(page, mock_base_url, token="t")

    page.locator('[data-testid="kb-more"]').first.click()
    page.locator('[data-testid="kb-menu-delete"]').click()
    page.wait_for_selector('[data-testid="confirm"]')
    page.locator('[data-testid="confirm-ok"]').click()
    page.wait_for_timeout(500)

    assert api.called("DELETE", "/knowledge-bases/1")
    assert page.locator('[data-testid="kb-item"]').count() == 1
    assert "留下的" in page.locator('[data-testid="kb-item"]').inner_text()


def test_card_stats_come_from_documents_api(page, mock_base_url):
    api = ApiMock(page)
    kb = api.add_kb("有文档的库")
    api.add_doc(kb["id"], "a.md", 2)
    api.add_doc(kb["id"], "b.pdf", 3)
    goto_app(page, mock_base_url, token="t")

    page.locator('[data-testid="nav-kbs"]').click()
    page.wait_for_selector('[data-testid="kb-stats"]')
    page.wait_for_timeout(500)

    text = page.locator('[data-testid="kb-stats"]').inner_text()
    assert "2 个文档" in text and "5 个文本块" in text
