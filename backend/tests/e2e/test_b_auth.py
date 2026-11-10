"""B. 登录 / 注册 / 认证状态。"""
from __future__ import annotations

import pytest

from helpers import ApiMock, goto_app, login_ui

pytestmark = pytest.mark.e2e


def test_login_success(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    goto_app(page, mock_base_url)

    login_ui(page, "alice", "secret123")
    page.wait_for_selector('[data-testid="chat"]', timeout=5000)

    assert api.called("POST", "/auth/login")
    assert page.evaluate("localStorage.getItem('mj_token')") == "mock-token"
    assert page.evaluate("localStorage.getItem('mj_user')") == "alice"


def test_login_wrong_password_shows_backend_message(page, mock_base_url):
    api = ApiMock(page)
    api.login_error = (401, "用户名或密码错误")
    goto_app(page, mock_base_url)

    login_ui(page, "alice", "wrong-pass")
    page.wait_for_selector('[data-testid="auth-error"]')

    assert "用户名或密码错误" in page.locator('[data-testid="auth-error"]').inner_text()
    assert page.locator('[data-testid="chat"]').count() == 0


def test_empty_username_blocked_without_request(page, mock_base_url):
    api = ApiMock(page)
    goto_app(page, mock_base_url)

    page.locator('[data-testid="auth-password"]').fill("secret123")
    page.locator('[data-testid="auth-submit"]').click()

    assert "请输入用户名" in page.locator('[data-testid="auth-error"]').inner_text()
    assert not api.called("POST", "/auth/")


def test_empty_password_blocked_without_request(page, mock_base_url):
    api = ApiMock(page)
    goto_app(page, mock_base_url)

    page.locator('[data-testid="auth-username"]').fill("alice")
    page.locator('[data-testid="auth-submit"]').click()

    assert "请输入密码" in page.locator('[data-testid="auth-error"]').inner_text()
    assert not api.called("POST", "/auth/")


def test_switch_to_register_form(page, mock_base_url):
    ApiMock(page)
    goto_app(page, mock_base_url)

    page.locator('[data-testid="auth-tab-register"]').click()
    assert "创建账号" in page.locator('[data-testid="auth-card"]').inner_text()
    assert page.locator('[data-testid="auth-submit"]').inner_text().strip() == "注册并登录"


def test_register_password_rule_enforced(page, mock_base_url):
    api = ApiMock(page)
    goto_app(page, mock_base_url)

    page.locator('[data-testid="auth-tab-register"]').click()
    login_ui(page, "newbie", "123")

    assert "密码至少 6 位" in page.locator('[data-testid="auth-error"]').inner_text()
    assert not api.called("POST", "/auth/register")


def test_register_success_logs_in(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("新库")
    goto_app(page, mock_base_url)

    page.locator('[data-testid="auth-tab-register"]').click()
    login_ui(page, "newbie", "secret123")

    page.wait_for_selector('[data-testid="chat"]', timeout=5000)
    assert api.called("POST", "/auth/register")


def test_refresh_keeps_session(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    goto_app(page, mock_base_url, token="t", username="alice")
    page.wait_for_selector('[data-testid="chat"]')

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector('[data-testid="chat"]', timeout=5000)

    assert page.locator('[data-testid="auth-card"]').count() == 0


def test_401_on_load_clears_token_and_returns_to_login(page, mock_base_url):
    api = ApiMock(page)
    api.kb_list_error = (401, "未登录或登录已过期")
    goto_app(page, mock_base_url, token="expired-token")

    page.wait_for_selector('[data-testid="auth-card"]', timeout=5000)
    assert page.evaluate("localStorage.getItem('mj_token')") in (None, "")


def test_logout_clears_storage(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    goto_app(page, mock_base_url, token="t", username="alice")
    page.wait_for_selector('[data-testid="chat"]')

    page.locator('[data-testid="user-chip"]').click()
    page.locator('[data-testid="logout"]').click()
    page.wait_for_selector('[data-testid="auth-card"]')

    assert page.evaluate("localStorage.getItem('mj_token')") in (None, "")
    assert page.locator('[data-testid="chat"]').count() == 0
