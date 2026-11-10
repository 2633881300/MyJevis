"""子 agent：每个知识库一个，只检索自己那个库。

设计要点：
  1. 子 agent 是一个完整的 Harness 实例（有自己的工具、prompt、agent 循环）。
  2. 它同时绑定 user_id 和 kb_id：user_id 保证权限，kb_id 保证只查本库。
  3. 它被包装成一个工具暴露给总管家，总管家调用它就像调用普通工具。
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from app.harness.harness import Harness
from app.harness.tools import ToolRegistry
from app.knowledge.tools import make_search_knowledge

# 子 agent 的系统提示词：限定职责范围
KB_SYSTEM_PROMPT = """你是知识库「{kb_name}」的专属助手。
规则：
1. 必须先调用检索工具在当前知识库中查找相关内容，再基于检索结果回答。
2. 只回答本知识库范围内的内容，不要用你自己的知识作答，也不要编造。
3. 检索不到相关内容时，明确说明「本知识库中没有找到相关内容」。
"""


class SubSearchInput(BaseModel):
    """子 agent 检索工具的输入：只有 query，kb_id 和 user_id 都已固定。"""

    query: str = Field(description="要检索的问题或关键词")


class AskKbInput(BaseModel):
    """总管家向子 agent 提问的输入。"""

    question: str = Field(description="要向该知识库提出的完整问题")


def _make_kb_search_tool(user_id: int, kb_id: int) -> Callable[[str], str]:
    """生成「只查这个库、只以这个用户身份查」的检索函数。

    两层绑定：
      - user_id：权限校验用，模型无法篡改
      - kb_id：范围锁定，模型连选择权都没有
    """
    base_search = make_search_knowledge(user_id)

    def search_this_kb(query: str) -> str:
        return base_search(kb_id, query)

    return search_this_kb


def build_sub_agent(user_id: int, kb_id: int, kb_name: str) -> Harness:
    """构建一个知识库子 agent。"""
    registry = ToolRegistry()
    registry.register_function(
        func=_make_kb_search_tool(user_id, kb_id),
        name=f"search_kb_{kb_id}",
        description=f"在知识库「{kb_name}」中检索与问题相关的原文片段。",
        args_schema=SubSearchInput,
    )
    return Harness(registry, KB_SYSTEM_PROMPT.format(kb_name=kb_name))


def build_sub_agent_as_tool(user_id: int, kb_id: int, kb_name: str) -> Callable[[str], str]:
    """把子 agent 包装成一个可供总管家调用的函数。

    总管家只拿到最终答案，看不到子 agent 的检索过程（上下文隔离）。
    """
    sub_harness = build_sub_agent(user_id, kb_id, kb_name)

    def ask_kb(question: str) -> str:
        try:
            result = sub_harness.run(question)
            return result["answer"]
        except Exception:  # noqa: BLE001
            # 不把内部异常抛给上层模型（避免泄露实现细节）
            return f"知识库「{kb_name}」暂时无法回答，请稍后重试。"

    return ask_kb
