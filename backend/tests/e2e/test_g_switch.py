"""G. 知识库切换与状态隔离。

当前实现是「单一会话」：切换知识库不会清空对话，消息与轨迹都是全局的。
这些用例锁定的是实际行为，而不是尚未实现的「按库分会话」。
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from helpers import ApiMock, ask, goto_app

pytestmark = pytest.mark.e2e


def _mock(page):
    api = ApiMock(page)
    kb1 = api.add_kb("库一")
    kb2 = api.add_kb("库二")
    api.add_doc(kb1["id"], "a.md", 4)
    api.add_doc(kb1["id"], "b.md", 3)
    api.add_doc(kb2["id"], "c.pdf", 1)
    return api, kb1, kb2


def _slow_stream(page, text="库一的回答"):
    page.evaluate(
        """(text) => {
            const original = window.fetch;
            window.fetch = async (url, opts) => {
                if (String(url).indexOf('/chat/stream') >= 0) {
                    await new Promise((r) => setTimeout(r, 700));
                    const body = 'data: ' + JSON.stringify({type: 'token', data: text}) + '\\n\\n'
                               + 'data: {"type":"done","data":""}\\n\\n';
                    return new Response(body, {status: 200, headers: {'content-type': 'text/event-stream'}});
                }
                return original(url, opts);
            };
        }""",
        text,
    )


def test_switch_midflight_keeps_answer_and_updates_header(page, mock_base_url):
    api, kb1, kb2 = _mock(page)
    goto_app(page, mock_base_url, token="t")
    page.wait_for_selector('[data-testid="chat"]')
    _slow_stream(page)

    ask(page, "库一的问题")
    # 请求还没回来就切到库二
    page.locator(f'[data-testid="kb-item"][data-kb-id="{kb2["id"]}"]').click()
    expect(page.locator('[data-testid="kb-switch"]')).to_contain_text("库二")

    # 回答仍然落在当前这段会话里（单会话设计），且不会丢失
    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("库一的回答", timeout=8000)
    assert page.locator('[data-testid="msg"][data-role="user"]').count() == 1


def test_session_info_follows_active_kb(page, mock_base_url):
    api, kb1, kb2 = _mock(page)
    goto_app(page, mock_base_url, token="t")
    page.wait_for_selector('[data-testid="panel"]')
    page.wait_for_timeout(600)

    panel = page.locator('[data-testid="panel"]')
    expect(panel).to_contain_text("2 篇 / 7 块")

    page.locator(f'[data-testid="kb-item"][data-kb-id="{kb2["id"]}"]').click()
    expect(panel).to_contain_text("1 篇 / 1 块")


def test_trace_does_not_grow_when_switching_kb(page, mock_base_url):
    api, kb1, kb2 = _mock(page)
    api.detail_body = {
        "answer": "回答",
        "intermediate_steps": [
            {"tool": "ask_kb_1", "args": {"question": "q"}, "result": "r"},
        ],
    }
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="detail-switch"]').click()

    ask(page, "问库一")
    page.wait_for_selector('[data-testid="step"]')
    before = page.locator('[data-testid="step"]').count()

    page.locator(f'[data-testid="kb-item"][data-kb-id="{kb2["id"]}"]').click()
    page.wait_for_timeout(400)

    # 切换知识库不会凭空产生新的执行步骤
    assert page.locator('[data-testid="step"]').count() == before


def test_switching_kb_does_not_clear_conversation(page, mock_base_url):
    api, kb1, kb2 = _mock(page)
    goto_app(page, mock_base_url, token="t")
    page.wait_for_selector('[data-testid="chat"]')

    ask(page, "先问一个问题")
    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("流式回答")

    page.locator(f'[data-testid="kb-item"][data-kb-id="{kb2["id"]}"]').click()
    page.wait_for_timeout(300)

    assert page.locator('[data-testid="msg"][data-role="user"]').count() == 1
    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("流式回答")
