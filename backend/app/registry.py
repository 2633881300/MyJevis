"""装配层：按用户构建工具注册表。

关键改动（安全）：
  build_default_registry 现在必须传 user_id —— 所有涉及用户资源的工具
  都在构建时用闭包绑定当前用户，不依赖运行时上下文，也不接受模型传入的身份。

  这解决了两个问题：
    1. 跨用户越权：工具不知道用户的身份，就无法校验；现在身份是构建时常量。
    2. 流式线程风险：上下文变量在线程池里会丢，闭包不会。
"""
from __future__ import annotations

from app.agents.public_search import PublicSearchInput, make_search_public_knowledge
from app.harness.tools import ToolRegistry
from app.knowledge.memory_tools import (
    GetProfileInput,
    ListDocsInput,
    ListKBsInput,
    UpdateProfileInput,
    make_get_user_profile,
    make_list_documents,
    make_list_knowledge_bases,
    make_update_user_profile,
)
from app.knowledge.tools import SearchInput, make_search_knowledge

DEFAULT_SYSTEM_PROMPT = """你是一个个人知识库助手。
规则：
1. 用户询问知识库、文档、资料里的内容时，必须先调用 search_knowledge 检索，基于检索结果回答，并标注来源。
2. 严格依据检索到的内容回答，不要用你自己的知识补充或编造。
3. 检索结果为空或明显不相关时，明确告诉用户"知识库中没有相关内容"。
4. 用户询问"我有几个知识库""某个库里有什么文档""我刚上传了什么""我的偏好"这类问题，
   分别使用 list_knowledge_bases、list_documents、get_user_profile 工具回答，不要凭猜。
5. 用户明确要求你记住某个偏好或习惯时，调用 update_user_profile 保存。
6. 如果自己的知识库找不到答案，可以调用 search_public_knowledge 在他人公开的库中检索。
7. 纯计算、纯常识类问题（如算术），可以直接回答，不必检索。
"""


def build_default_registry(user_id: int) -> ToolRegistry:
    """按用户构建工具注册表（所有工具都绑定该用户身份）。"""
    registry = ToolRegistry()

    # --- 知识库检索（只读，允许本人 + 他人公开库）---
    registry.register_function(
        func=make_search_knowledge(user_id),
        name="search_knowledge",
        description="在指定知识库中检索与问题相关的原文片段，返回带来源标注的内容。当用户询问知识库、文档、笔记里的具体内容时使用。",
        args_schema=SearchInput,
    )

    # --- 全局记忆 ---
    registry.register_function(
        func=make_list_knowledge_bases(user_id),
        name="list_knowledge_bases",
        description="列出当前用户的所有知识库（含 ID、名称、公开或私有）。当用户问「我有几个知识库」「有哪些库」时使用。",
        args_schema=ListKBsInput,
    )
    registry.register_function(
        func=make_list_documents(user_id),
        name="list_documents",
        description="列出某个知识库下的所有文档、文本块数量和上传时间。当用户问「某个库里有哪些文档」「我刚上传了什么」时使用。",
        args_schema=ListDocsInput,
    )
    registry.register_function(
        func=make_get_user_profile(user_id),
        name="get_user_profile",
        description="读取用户画像（长期偏好、习惯、重要事实）。当需要了解用户背景、或用户问「你记得我什么」时使用。",
        args_schema=GetProfileInput,
    )
    registry.register_function(
        func=make_update_user_profile(user_id),
        name="update_user_profile",
        description="更新用户画像，保存用户的长期偏好、习惯或重要事实。当用户明确说「记住…」「以后都…」这类长期要求时使用。",
        args_schema=UpdateProfileInput,
    )

    # --- 公开库检索 ---
    registry.register_function(
        func=make_search_public_knowledge(user_id),
        name="search_public_knowledge",
        description="在他人公开的知识库中检索内容。当用户问的内容自己的知识库里没有，或明确想查公开资料时使用。",
        args_schema=PublicSearchInput,
    )

    return registry
