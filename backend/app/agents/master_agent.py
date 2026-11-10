"""总管家 agent：站在所有子 agent 之上的编排层。

设计要点：
  1. 总管家本身也是一个 Harness 实例，和子 agent 用同一套框架。
  2. 它的工具 = 按用户构建的全局工具 + 每个知识库子 agent 包装成的工具。
  3. 所有工具在构建时都绑定了 user_id，模型无法指定或篡改身份。
"""
from __future__ import annotations

from app.agents.sub_agent import AskKbInput, build_sub_agent_as_tool
from app.db import SessionLocal
from app.harness.harness import Harness
from app.models import KnowledgeBase
from app.registry import build_default_registry

MASTER_SYSTEM_PROMPT = """你是一个个人知识库总管家。
规则：
1. 判断用户问题涉及哪个知识库，调用对应的 ask_kb_* 工具，让该库的专属助手回答。
2. 用户问「我有几个知识库」「某个库有哪些文档」「我的偏好」时，
   用 list_knowledge_bases、list_documents、get_user_profile 等工具。
3. 用户要求记住偏好时，调用 update_user_profile。
4. 如果自己的知识库找不到答案，可以调用 search_public_knowledge 在他人公开的库中检索。
5. 综合各工具的结果回答，标注来源；不确定时如实说明，不要编造。
"""


def _list_user_kbs(user_id: int) -> list[dict]:
    """查当前用户自己的知识库（他人库通过 search_public_knowledge 访问）。"""
    db = SessionLocal()
    try:
        kbs = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.user_id == user_id)
            .order_by(KnowledgeBase.created_at)
            .all()
        )
        return [{"id": kb.id, "name": kb.name} for kb in kbs]
    finally:
        db.close()


def build_master_agent(user_id: int) -> Harness:
    """构建总管家 agent（工具全部绑定当前用户身份）。"""
    registry = build_default_registry(user_id)

    for kb in _list_user_kbs(user_id):
        registry.register_function(
            func=build_sub_agent_as_tool(user_id, kb["id"], kb["name"]),
            name=f"ask_kb_{kb['id']}",
            description=(
                f"向知识库「{kb['name']}」提问，由该库的专属助手检索后回答。"
                f"当用户问题涉及这个知识库的内容时使用。"
            ),
            args_schema=AskKbInput,
        )

    return Harness(registry, MASTER_SYSTEM_PROMPT)
