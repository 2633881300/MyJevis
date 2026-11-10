"""流式过滤测试：证明 SSE 只输出最终答案。

不需要真实 LLM —— 用一个假的图模拟 LangGraph 的事件序列：
    中间文本 + 工具调用  →  工具结果(ToolMessage)  →  最终回答
断言输出里只有最终回答。

运行：
    conda run -n Langgraph pytest tests/test_stream_filter.py -v
"""
from __future__ import annotations

from langchain_core.messages import AIMessageChunk, ToolMessage

from app.harness.harness import Harness
from app.harness.tools import ToolRegistry


class _FakeGraph:
    """模拟 LangGraph 的 stream(stream_mode="messages") 输出。"""

    def __init__(self, events):
        self._events = events

    def stream(self, *args, **kwargs):
        for item in self._events:
            yield item


def _mk_harness(events) -> Harness:
    h = Harness(ToolRegistry(), None)
    h._graph = _FakeGraph(events)      # 直接替换内部图，绕开真实 LLM
    return h


def test_middle_text_and_tool_result_are_filtered():
    """中间文本 + 工具调用 + 工具原文 都不能出现在输出里。"""
    events = [
        # 第一轮：模型说"我先查一下"，同时产生工具调用
        (AIMessageChunk(id="m1", content="我先"), {"langgraph_node": "agent"}),
        (AIMessageChunk(id="m1", content="查一下"), {"langgraph_node": "agent"}),
        (
            AIMessageChunk(
                id="m1",
                content="",
                tool_call_chunks=[
                    {"name": "search", "args": "{}", "id": "c1", "index": 0, "type": "tool_call_chunk"}
                ],
            ),
            {"langgraph_node": "agent"},
        ),
        # 工具执行结果
        (ToolMessage(content="工具检索到的原文内容", tool_call_id="c1"), {"langgraph_node": "tools"}),
        # 第二轮：最终回答
        (AIMessageChunk(id="m2", content="这是"), {"langgraph_node": "agent"}),
        (AIMessageChunk(id="m2", content="最终答案"), {"langgraph_node": "agent"}),
    ]

    out = "".join(_mk_harness(events).stream("问题"))

    assert out == "这是最终答案", f"实际输出：{out!r}"
    assert "我先" not in out, "中间文本泄漏"
    assert "工具检索到的原文" not in out, "工具原文泄漏"


def test_tool_call_detected_by_tool_calls_field():
    """只带 tool_calls（无 tool_call_chunks）时也要能识别为中间轮次。"""
    chunk = AIMessageChunk(
        id="m1",
        content="我要调用工具",
        tool_calls=[{"name": "search", "args": {}, "id": "c1", "type": "tool_call"}],
    )
    events = [
        (chunk, {"langgraph_node": "agent"}),
        (AIMessageChunk(id="m2", content="最终答案"), {"langgraph_node": "agent"}),
    ]
    out = "".join(_mk_harness(events).stream("问题"))
    assert out == "最终答案", f"实际输出：{out!r}"


def test_no_tool_call_passes_through():
    """没有工具调用时，答案应完整输出。"""
    events = [
        (AIMessageChunk(id="m1", content="直接"), {"langgraph_node": "agent"}),
        (AIMessageChunk(id="m1", content="回答"), {"langgraph_node": "agent"}),
    ]
    out = "".join(_mk_harness(events).stream("问题"))
    assert out == "直接回答"


def test_non_agent_node_events_ignored():
    """非 agent 节点产出的 AI 消息（未来嵌套子图）不应混入输出。"""
    events = [
        (AIMessageChunk(id="m1", content="子agent的话"), {"langgraph_node": "sub_agent"}),
        (AIMessageChunk(id="m2", content="最终答案"), {"langgraph_node": "agent"}),
    ]
    out = "".join(_mk_harness(events).stream("问题"))
    assert out == "最终答案", f"实际输出：{out!r}"
