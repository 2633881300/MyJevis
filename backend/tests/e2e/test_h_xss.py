"""H. Markdown 渲染与 XSS 安全。

注意：这里验证的是「不执行脚本、不产生危险节点」，
并不能替代完整的渗透测试。
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from helpers import ApiMock, ask, goto_app

pytestmark = pytest.mark.e2e

PAYLOADS = [
    "<img src=x onerror=alert(1)>",
    "<script>alert(1)</script>",
    '<a href="javascript:alert(1)">click</a>',
    '<iframe src="javascript:alert(1)"></iframe>',
    '"><svg onload=alert(1)>',
]


@pytest.fixture
def dialogs(page):
    seen: list[str] = []
    page.on("dialog", lambda d: (seen.append(d.message), d.dismiss()))
    return seen


def _ready(page, mock_base_url, answer: str):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    api.detail_body = {"answer": answer, "intermediate_steps": []}
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="detail-switch"]').click()
    page.wait_for_selector('[data-testid="chat"]')
    return api


@pytest.mark.parametrize("payload", PAYLOADS)
def test_html_payload_is_escaped_not_executed(page, mock_base_url, dialogs, payload):
    _ready(page, mock_base_url, answer="结果：" + payload)

    ask(page, "注入测试")
    expect(page.locator('[data-testid="msg-text"]').last).to_contain_text("结果：", timeout=8000)
    page.wait_for_timeout(300)

    assert dialogs == [], f"脚本被触发了: {dialogs}"
    text_block = page.locator('[data-testid="msg-text"]').last
    assert text_block.locator("script, iframe, img, svg").count() == 0
    assert text_block.locator('[href^="javascript"]').count() == 0
    # 原始内容以文本形式保留，说明是转义而不是被吞掉
    assert payload in text_block.inner_text()


def test_markdown_table_renders(page, mock_base_url):
    answer = "\n".join([
        "文档清单：",
        "",
        "| 文档 | 块数 |",
        "|---|---|",
        "| a.md | 2 |",
        "| b.pdf | 3 |",
    ])
    _ready(page, mock_base_url, answer=answer)

    ask(page, "列出表格")
    page.wait_for_selector(".md-table", timeout=8000)

    table = page.locator(".md-table")
    assert table.locator("tbody tr").count() == 2
    assert "a.md" in table.inner_text()


def test_bold_and_code_render(page, mock_base_url):
    _ready(page, mock_base_url, answer="**重点** 与 `code` 混排")

    ask(page, "格式测试")
    page.wait_for_selector(".msg-text strong", timeout=8000)

    block = page.locator('[data-testid="msg-text"]').last
    assert block.locator("strong").inner_text() == "重点"
    assert block.locator("code").inner_text() == "code"


def test_tool_args_payload_is_not_executed(page, mock_base_url):
    api = ApiMock(page)
    api.add_kb("知识库 A")
    api.detail_body = {
        "answer": "完成",
        "intermediate_steps": [
            {"tool": "list_documents", "args": {"knowledge_base_id": "<img src=x onerror=alert(1)>"},
             "result": "<script>alert(1)</script>"},
        ],
    }
    goto_app(page, mock_base_url, token="t")
    page.locator('[data-testid="detail-switch"]').click()

    ask(page, "参数注入")
    page.wait_for_selector('[data-testid="step"]', timeout=8000)

    step = page.locator('[data-testid="step"]').first
    assert step.locator("img, script").count() == 0
    assert "<img" in step.inner_text()
