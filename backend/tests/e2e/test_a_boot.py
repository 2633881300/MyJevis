"""A. 静态资源与页面初始化。"""
from __future__ import annotations

import logging

import pytest

from helpers import ApiMock, goto_app

pytestmark = pytest.mark.e2e


def test_index_loads_and_vue_mounts(page, mock_base_url, console_errors, failed_requests):
    ApiMock(page).add_kb("知识库 A")
    goto_app(page, mock_base_url, token="t")

    page.wait_for_selector('[data-testid="chat"]', timeout=5000)
    assert "MyJevis" in page.title()
    assert page.locator("#app").count() == 1
    assert console_errors == []


def test_static_assets_have_no_404(page, mock_base_url, failed_requests):
    ApiMock(page).add_kb("知识库 A")
    goto_app(page, mock_base_url, token="t")
    page.wait_for_selector('[data-testid="chat"]')

    asset_failures = [x for x in failed_requests if "/css/" in x[0] or "/js/" in x[0]]
    assert asset_failures == [], f"静态资源加载失败: {asset_failures}"


def test_unauthenticated_shows_auth_only(page, mock_base_url, console_errors):
    ApiMock(page)
    goto_app(page, mock_base_url)

    assert page.locator('[data-testid="auth-card"]').is_visible()
    assert page.locator('[data-testid="chat"]').count() == 0
    assert console_errors == []


def test_authenticated_shows_workspace(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    goto_app(page, mock_base_url, token="t", username="alice")

    assert page.locator('[data-testid="chat"]').is_visible()
    assert page.locator('[data-testid="auth-card"]').count() == 0
    assert page.locator('[data-testid="user-chip"]').inner_text().strip().endswith("alice")


def test_no_uncaught_exception_on_navigation(page, mock_base_url, console_errors):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    api.add_doc(1, "a.md")
    goto_app(page, mock_base_url, token="t")

    for nav in ("nav-kbs", "nav-docs", "nav-chat"):
        page.locator(f'[data-testid="{nav}"]').click()
        page.wait_for_timeout(250)

    assert console_errors == []


class _FlakyPage:
    """模拟「首屏没渲染出来」的页面，用来验证重试行为与日志。"""

    def __init__(self):
        self.url = "about:blank"
        self.goto_count = 0
        self.reload_count = 0
        self.wait_count = 0

    def goto(self, url, **kwargs):
        self.goto_count += 1
        self.url = url

    def wait_for_selector(self, selector, timeout=None):
        self.wait_count += 1
        if self.wait_count == 1:
            raise TimeoutError("selector not found")

    def reload(self, **kwargs):
        self.reload_count += 1

    def wait_for_timeout(self, ms):
        pass


@pytest.mark.no_browser
def test_first_paint_retry_is_logged(caplog):
    """重试必须留日志，否则资源加载失败会被悄悄忽略。"""
    caplog.set_level(logging.WARNING, logger="myjevis.e2e")
    fake = _FlakyPage()

    goto_app(fake, "http://example.test")

    assert fake.goto_count == 1
    assert fake.reload_count == 1
    assert fake.wait_count == 2
    messages = [r.getMessage() for r in caplog.records if r.name == "myjevis.e2e"]
    assert any("重载一次" in m for m in messages), messages
