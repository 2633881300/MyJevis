"""会话状态定义: LangGraph 图内流传的状态结构
"""

from __future__ import annotations

from typing import TypedDict, Annotated,Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict,total=False):
    """Agent 工具循环的状态

    - messages: 对话消息列表
    - final_answer: 最终答案
    - intermediate_state: 记录每一步调用了哪个工具,传了什么参数,返回什么
    """
    messages: Annotated[list[BaseMessage],add_messages]