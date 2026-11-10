"""知识库业务工具：把「知识检索」包装成 harness 可调用的工具。

权限设计（关键）：
  user_id 由闭包在「构建工具时」绑定，不通过参数传、也不依赖运行时上下文。
  这样无论 agent 怎么调度、线程怎么切换，工具永远只以当前用户的身份访问数据。
  模型没有任何接口能指定或篡改 user_id。

  注意：原来的 ingest_document 已移除 —— 它接受模型提供的服务器本地路径，
  属于任意文件读取风险。文档上传统一走 POST /documents/upload。
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from app.knowledge.permissions import AccessDenied, require_readable_kb
from app.knowledge.store import get_vector_store

# 检索结果的最大距离（ChromaDB L2，越小越相关）：实测相关约 0.6，不相关约 1.4+
RELEVANCE_THRESHOLD = 1.0


class SearchInput(BaseModel):
    """检索工具的输入参数。"""

    knowledge_base_id: int = Field(description="要检索的知识库 ID")
    query: str = Field(description="要检索的问题或关键词")


def make_search_knowledge(user_id: int) -> Callable[[int, str], str]:
    """生成一个「以指定用户身份检索」的工具函数。

    user_id 被闭包固定，模型无法指定或篡改。
    """

    def search_knowledge(knowledge_base_id: int, query: str) -> str:
        if not query or not query.strip():
            return "查询内容为空，请提供具体的问题或关键词。"

        # 权限校验：读操作允许「本人」或「他人公开」的库
        try:
            require_readable_kb(knowledge_base_id, user_id)
        except AccessDenied as e:
            # 返回文本而不是抛异常，让模型能理解并纠正自己的调用
            return f"检索失败：{e}"

        store = get_vector_store()
        try:
            results = store.search_with_score(knowledge_base_id, query, k=4)
        except Exception:  # noqa: BLE001
            return "检索服务暂时不可用，请稍后重试。"

        relevant = [r for r in results if r["score"] < RELEVANCE_THRESHOLD]
        if not relevant:
            return f"知识库 {knowledge_base_id} 中没有找到相关内容。"

        lines = [
            f"[{i}] 来源《{r['source']}》：{r['text']}"
            for i, r in enumerate(relevant, 1)
        ]
        return "\n\n".join(lines)

    return search_knowledge
