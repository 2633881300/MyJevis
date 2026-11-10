"""Harness 门面类：对外的统一入口。
"""

from __future__ import annotations

from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.errors import GraphRecursionError

from app.harness.graph import build_agent_graph, collect_intermediate_steps
from app.harness.state import AgentState
from app.harness.tools import ToolRegistry

# 最大循环步数上限
MAX_GRAPH_STEPS = 20

# 上限友好回复
LIVELOCK_MESSAGE = (
    "这个问题我反复尝试调用工具，但没能收敛到答案。"
    "可能是问题太复杂、知识库中没有相关内容，或工具暂时不可用。"
    "建议换个说法，或确认知识库里已上传相关资料。"
)


class Harness:
    """可复用的 Agent Harness
    """

    def __init__(self, registry: ToolRegistry, system_prompt: str | None = None) -> None:
        self.registry = registry
        self._graph = build_agent_graph(registry, system_prompt)

    def run(self, question: str) -> dict:
        """同步运行一次 agent 循环,返回最终答案 + 中间步骤"""
        initial_state: AgentState = {
            "messages": [HumanMessage(content=question)],
        }

        # 第一层防护：限制最大步数，防止模型反复调工具导致无限循环
        try:
            result: AgentState = self._graph.invoke(
                initial_state,
                config={"recursion_limit": MAX_GRAPH_STEPS},
            )
        except GraphRecursionError:
            return {
                "answer": LIVELOCK_MESSAGE,
                "intermediate_steps": [],
            }

        messages = result["messages"]
        final_answer = ""
        if messages:
            last = messages[-1]
            final_answer = last.content if hasattr(last, "content") else ""

        return {
            "answer": final_answer,
            "intermediate_steps": collect_intermediate_steps(messages),
        }

    def stream(self, question: str):
        """流式运行：只产出「可展示的最终答案」，过滤中间过程。

        过滤规则（实测 LangGraph stream_mode="messages" 的 metadata 得出）：
          1. 只处理 AIMessageChunk —— ToolMessage（工具检索原文）绝不能给用户看。
          2. 带 tool_calls 的 AI 消息属于「中间轮次」（模型说"我去查一下"然后调工具），
             它的文本也要丢弃。

        权衡：流式时 token 先到、tool_calls 后到，无法边流边判断。
        所以按「消息」为单位缓冲，一条消息结束后再决定是否输出。
        代价是最终答案整段出现而非逐 token，但保证内容正确。
        """
        initial_state: AgentState = {
            "messages": [HumanMessage(content=question)],
        }

        buf_id: str | None = None
        buf_text = ""
        buf_has_tool = False

        def _take_buffer() -> str | None:
            """取出缓冲区里可展示的文本（中间轮次返回 None）。"""
            nonlocal buf_id, buf_text, buf_has_tool
            text = buf_text if (buf_id and not buf_has_tool and buf_text.strip()) else None
            buf_id, buf_text, buf_has_tool = None, "", False
            return text

        try:
            for msg, meta in self._graph.stream(
                initial_state,
                config={"recursion_limit": MAX_GRAPH_STEPS},
                stream_mode="messages",
            ):
                # 规则 1：只认 AI 生成的消息，ToolMessage 一律丢弃
                if not isinstance(msg, AIMessageChunk):
                    continue

                # 规则 1.5：只接受本图 agent 节点产出的事件。
                # 防止未来开启嵌套子图流式传播时，把子 agent 的输出混进来。
                node = meta.get("langgraph_node")
                if node is not None and node != "agent":
                    continue

                # 消息切换：先把上一条结算掉
                if msg.id != buf_id:
                    piece = _take_buffer()
                    if piece:
                        yield piece
                    buf_id = msg.id

                # 规则 2：这条消息在调工具 → 标记，结算时丢弃。
                # 流式下有两条线索：tool_calls 是解析后的完整调用，
                # tool_call_chunks 是原始增量片段（不同版本/模型可能只给后者）。
                if getattr(msg, "tool_calls", None) or getattr(msg, "tool_call_chunks", None):
                    buf_has_tool = True

                if isinstance(msg.content, str):
                    buf_text += msg.content

            # 流结束，结算最后一条
            piece = _take_buffer()
            if piece:
                yield piece
        except GraphRecursionError:
            yield LIVELOCK_MESSAGE
