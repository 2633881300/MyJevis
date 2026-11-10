"""F. 详细模式：真实 intermediate_steps 展示。"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from helpers import ApiMock, ask, goto_app

pytestmark = pytest.mark.e2e


def _ready(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    goto_app(page, mock_base_url, token="t")
    page.wait_for_selector('[data-testid="chat"]')
    return api


def _enable_detail(page):
    page.locator('[data-testid="detail-switch"]').click()
    page.wait_for_timeout(200)


def test_default_mode_shows_empty_trace(page, mock_base_url):
    _ready(page, mock_base_url)

    assert page.locator('[data-testid="detail-switch"]').get_attribute("class").find("on") == -1
    expect(page.get_by_text("执行轨迹暂未开放")).to_be_visible()


def test_toggle_detail_persists(page, mock_base_url):
    _ready(page, mock_base_url)

    _enable_detail(page)
    assert page.evaluate("localStorage.getItem('mj_detail_mode')") == "1"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector('[data-testid="detail-switch"]')
    assert "on" in page.locator('[data-testid="detail-switch"]').get_attribute("class")


def test_detail_uses_sync_endpoint(page, mock_base_url):
    api = _ready(page, mock_base_url)
    _enable_detail(page)

    ask(page, "详细模式提问")

    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("详细模式回答")
    assert api.called("POST", "/chat")
    assert not api.called("POST", "/chat/stream")


def test_steps_render_tool_name_args_result(page, mock_base_url):
    api = _ready(page, mock_base_url)
    api.detail_body = {
        "answer": "已查询。",
        "intermediate_steps": [
            {"tool": "list_documents", "args": {"knowledge_base_id": 7}, "result": "共 4 份文档"},
            {"tool": "ask_kb_7", "args": {"question": "急救流程"}, "result": "子 Agent 的回答"},
        ],
    }
    _enable_detail(page)

    ask(page, "列出文档")
    page.wait_for_selector('[data-testid="step"]')

    steps = page.locator('[data-testid="step"]')
    expect(steps).to_have_count(2)

    first = steps.nth(0).inner_text()
    assert "列出文档" in first
    assert "knowledge_base_id" in first
    assert "共 4 份文档" in first

    second = steps.nth(1).inner_text()
    assert "知识库子 Agent" in second
    assert "急救流程" in second
    # 子 Agent 的结果就是最终答案本身，面板不再重复展示
    assert "子 Agent 的回答" not in second


def test_empty_steps_shows_reasonable_state(page, mock_base_url):
    api = _ready(page, mock_base_url)
    api.detail_body = {"answer": "无需工具，直接回答。", "intermediate_steps": []}
    _enable_detail(page)

    ask(page, "你好")

    expect(page.get_by_text("本次会话暂无工具调用")).to_be_visible()
    assert page.locator('[data-testid="step"]').count() == 0


def test_detail_failure_shows_error(page, mock_base_url):
    api = _ready(page, mock_base_url)
    api.detail_status = 500
    _enable_detail(page)

    ask(page, "会失败的请求")

    expect(page.locator(".msg-col p")).to_contain_text("服务暂时不可用", timeout=8000)
    assert page.locator('[data-testid="step"]').count() == 0


def test_no_fabricated_timestamps_in_trace(page, mock_base_url):
    api = _ready(page, mock_base_url)
    api.detail_body = {
        "answer": "完成。",
        "intermediate_steps": [
            {"tool": "list_knowledge_bases", "args": {}, "result": "你的知识库：- [ID 1] A"},
        ],
    }
    _enable_detail(page)

    ask(page, "查询")
    page.wait_for_selector('[data-testid="step"]')

    text = page.locator('[data-testid="panel"]').inner_text()
    # 面板只允许出现「当前会话信息」里的统计，不允许出现执行耗时/时间戳
    assert not re.search(r"\d{2}:\d{2}:\d{2}", text)
    assert "ms" not in text
