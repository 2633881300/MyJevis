"""Agent 循环：状态定义 + LangGraph 图（ReAct 循环）。

基于 LangGraph 构建一个经典的 ReAct 循环
    用户输入 -> 模型思考 -> (决定调工具) -> 执行工具 -> 结果回传 -> 再思考 -> ...
    直到模型认为可以给出最终答案, 循环结束.
"""

from __future__ import annotations
import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from typing import Literal

from langgraph.graph import StateGraph

from app.harness.llm import get_llm
from app.harness.state import AgentState
from app.harness.tools import ToolRegistry

logger = logging.getLogger(__name__)

# 同一个工具,同一组参数,最多允许重复调用次数
MAX_SAME_TOOL_CALLS = 2

def _call_key(tool_call: dict) -> tuple[str,str]:
    """把一次工具调用归一化为可比较的键"""

    args = json.dumps(tool_call.get("args",{}),sort_keys=True,ensure_ascii=False)
    return tool_call.get("name",""), args



def build_agent_graph(registry: ToolRegistry,system_prompt: str | None = None):
    """"根据工具注册表构建 agent 图

    - agent 节点: 调用模型,模型决定是调用工具还是直接回答
    - tools 节点: 执行模型选择调用的工具, 生成 ToolMessage 回传
    - 条件边: 模型要调用工具 -> 走 tools 节点;否则 -> END
    """
    llm = get_llm()
    tools = registry.get_all()
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        """agent 节点: 让模型基于当前消息决定下一步"""
        messages = state.get("messages",[])
        if system_prompt:
            messages = [SystemMessage(content=system_prompt)] + list(messages)
        response: AIMessage = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def tool_node(state: AgentState) -> dict:
        """自写工具执行节点"""
        messages = state.get("messages",[])
        last = messages[-1]
        if not (isinstance(last,AIMessage) and last.tool_calls):
            return {"messages": []}

        # 先统计历史上每个(工具名,参数)出现过几次
        history: dict[tuple[str,str],int] = {}
        for msg in messages:
            if isinstance(msg,AIMessage) and msg.tool_calls:
                for c in msg.tool_calls:
                    key = _call_key(c)
                    history[key] = history.get(key,0) + 1

        tool_messages: list[ToolMessage] = []
        for tc in last.tool_calls:
            key = _call_key(tc)
            if history.get(key,0) > MAX_SAME_TOOL_CALLS:
                content = (
                    f"已阻止重复调用：工具 {tc['name']} 用完全相同的参数已经调用过 "
                    f"{history[key] - 1} 次，结果不会改变。"
                    "请停止重复调用，基于已有信息直接回答用户，或如实说明信息不足。"
                )
            else:
                tool = tools_by_name.get(tc["name"])
                if tool is None:
                    content = f"错误,未知工具{tc['name']}"
                else:
                    try:
                        result = tool.invoke(tc["args"])
                        content = result if isinstance(result,str) else str(result)
                    except Exception:
                        # 原始异常只写服务端日志，不进入模型上下文 / 用户视野
                        logger.exception("工具 %s 执行失败", tc["name"])
                        content = f"工具 {tc['name']} 执行失败，请稍后重试或换一种方式。"
            tool_messages.append(
                ToolMessage(
                    content=content,
                    tool_call_id=tc["id"],
                    name=tc["name"],
                )
            )
        return {"messages": tool_messages}

    def route_after_agent(state: AgentState) -> Literal["tools","__end__"]:
        messages = state["messages"]
        last = messages[-1]
        if isinstance(last,AIMessage) and last.tool_calls:
            return "tools"
        return "__end__"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_edge("tools", "agent")

    return graph.compile()

def collect_intermediate_steps(messages: list) -> list[dict]:
    """从消息列表中提取 agent 的中间步骤"""
    steps: list[dict] = []
    for msg in messages:
        if isinstance(msg,AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                steps.append(
                    {
                        "tool": tc["name"],
                        "args": tc.get("args",{}),
                        "result": None,
                    }
                )
        elif isinstance(msg,ToolMessage):
            for step in reversed(steps):
                if step["result"] is None:
                    step["result"] = str(msg.content)
                    break
    return steps

