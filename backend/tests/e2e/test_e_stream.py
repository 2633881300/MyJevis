"""E. 普通模式：SSE 流式问答。"""
from __future__ import annotations

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


def test_send_shows_user_and_assistant_messages(page, mock_base_url):
    api = _ready(page, mock_base_url)

    ask(page, "这个库讲了什么？")

    expect(page.locator('[data-testid="msg"][data-role="user"]')).to_have_count(1)
    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("流式回答")
    assert api.called("POST", "/chat/stream")


def test_enter_key_sends(page, mock_base_url):
    api = _ready(page, mock_base_url)

    box = page.locator('[data-testid="chat-input"]')
    box.fill("回车发送")
    box.press("Enter")

    expect(page.locator('[data-testid="msg"][data-role="user"]')).to_have_count(1)
    assert api.called("POST", "/chat/stream")


def test_shift_enter_inserts_newline_without_sending(page, mock_base_url):
    api = _ready(page, mock_base_url)

    box = page.locator('[data-testid="chat-input"]')
    box.fill("第一行")
    box.press("Shift+Enter")

    assert box.input_value().endswith("\n")
    assert page.locator('[data-testid="msg"][data-role="user"]').count() == 0
    assert not api.called("POST", "/chat/stream")


def test_stream_tokens_are_concatenated(page, mock_base_url):
    api = _ready(page, mock_base_url)
    api.stream_frames = [
        {"type": "token", "data": "第一段"},
        {"type": "token", "data": " + 第二段"},
        {"type": "done", "data": ""},
    ]

    ask(page, "分段输出")

    expect(page.locator('[data-testid="msg-text"]').last).to_have_text("第一段 + 第二段")


def test_pending_state_then_recover(page, mock_base_url):
    api = _ready(page, mock_base_url)

    # 在页面内接管 /chat/stream，延迟 800ms 再返回，这样「等待中」状态可稳定观察
    page.evaluate(
        """() => {
            const original = window.fetch;
            window.fetch = async (url, opts) => {
                if (String(url).indexOf('/chat/stream') >= 0) {
                    await new Promise((r) => setTimeout(r, 800));
                    const body = 'data: {"type":"token","data":"慢速回答"}\\n\\n'
                               + 'data: {"type":"done","data":""}\\n\\n';
                    return new Response(body, {status: 200, headers: {'content-type': 'text/event-stream'}});
                }
                return original(url, opts);
            };
        }"""
    )

    ask(page, "慢一点")

    expect(page.locator('[data-testid="typing"]')).to_be_visible(timeout=3000)
    expect(page.locator('[data-testid="chat-send"]')).to_be_disabled()

    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("慢速回答", timeout=10000)
    expect(page.locator('[data-testid="typing"]')).to_have_count(0)
    # 输入框已被清空，按钮应保持禁用；重新输入后必须恢复可发送
    expect(page.locator('[data-testid="chat-send"]')).to_be_disabled()
    page.locator('[data-testid="chat-input"]').fill("下一个问题")
    expect(page.locator('[data-testid="chat-send"]')).to_be_enabled()


def test_sse_error_event_surfaces_message(page, mock_base_url):
    api = _ready(page, mock_base_url)
    api.stream_frames = [
        {"type": "token", "data": "部分内容"},
        {"type": "error", "data": "服务暂时不可用，请稍后重试"},
        {"type": "done", "data": ""},
    ]

    ask(page, "触发错误")

    expect(page.locator(".msg-col p")).to_contain_text("服务暂时不可用", timeout=8000)


def test_empty_input_cannot_send(page, mock_base_url):
    api = _ready(page, mock_base_url)

    expect(page.locator('[data-testid="chat-send"]')).to_be_disabled()

    page.locator('[data-testid="chat-input"]').fill("   ")
    expect(page.locator('[data-testid="chat-send"]')).to_be_disabled()

    assert not api.called("POST", "/chat/stream")


def test_consecutive_questions_do_not_overwrite(page, mock_base_url):
    api = _ready(page, mock_base_url)

    ask(page, "第一个问题")
    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("流式回答")

    ask(page, "第二个问题")
    expect(page.locator('[data-testid="msg"][data-role="user"]')).to_have_count(2)
    # 欢迎语 + 两条回答，共 3 条 assistant 文本，说明第二次没有覆盖第一次
    expect(page.locator('[data-testid="msg-text"]')).to_have_count(3)


def test_network_failure_shows_error_and_recovers(page, mock_base_url):
    api = _ready(page, mock_base_url)
    page.route("**/chat/stream", lambda route: route.abort())

    ask(page, "断网测试")

    expect(page.locator(".msg-col p")).to_contain_text("网络异常", timeout=8000)
    # 失败后必须能继续操作：重新输入即可再次发送
    page.locator('[data-testid="chat-input"]').fill("再试一次")
    expect(page.locator('[data-testid="chat-send"]')).to_be_enabled()
