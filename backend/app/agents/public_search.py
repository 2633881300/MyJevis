"""公开库动态发现 + 检索工具。

不静态挂载所有公开库子 agent（公开库多时会工具爆炸），
而是提供一个「按需发现」工具：根据问题找到语义最相关的公开库，再检索。

权限：只查 is_public=True 且不属于当前用户的库；user_id 由闭包绑定。
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from app.db import SessionLocal
from app.knowledge.embedding import get_embedding_client
from app.knowledge.store import get_vector_store
from app.models import KnowledgeBase

# 库发现的粗筛阈值。
# 实测（bge-m3）：短问题 vs「库名+描述」的余弦相似度普遍偏低且区分度差——
#   相关问题 0.26~0.53，不相关问题 0.21~0.25，两者会重叠。
# 所以这一层只能做「粗筛」，宁可选得宽松一点（不漏掉可能的库），
# 真正的相关性判定交给下面的 chunk 距离阈值。
KB_RELEVANCE_THRESHOLD = 0.20

# 检索结果的最大距离（ChromaDB L2）：实测相关约 0.6，不相关约 1.4+，区分度明显
CHUNK_DISTANCE_THRESHOLD = 1.0


class PublicSearchInput(BaseModel):
    """公开库检索工具的输入。"""

    query: str = Field(description="要检索的问题或关键词")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _find_related_public_kbs(query: str, exclude_user_id: int, top_n: int = 3) -> list[dict]:
    """根据 query 找语义最相关的公开库（排除本人的库，且相似度须过阈值）。"""
    db = SessionLocal()
    try:
        public_kbs = (
            db.query(KnowledgeBase)
            .filter(
                KnowledgeBase.is_public == True,  # noqa: E712
                KnowledgeBase.user_id != exclude_user_id,
            )
            .all()
        )
        if not public_kbs:
            return []

        # 一次批量算：第 0 个是 query，后面是各库的「名称 + 描述」
        texts = [query] + [f"{kb.name} {kb.description}".strip() for kb in public_kbs]
        embed = get_embedding_client()
        vectors = embed.embed_texts(texts)

        query_vec, kb_vecs = vectors[0], vectors[1:]

        scored = []
        for kb, vec in zip(public_kbs, kb_vecs):
            score = _cosine_similarity(query_vec, vec)
            if score >= KB_RELEVANCE_THRESHOLD:
                scored.append({"id": kb.id, "name": kb.name, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]
    finally:
        db.close()


def make_search_public_knowledge(user_id: int) -> Callable[[str], str]:
    """生成「检索公开库」工具，user_id 闭包固定（用于排除自己的库）。"""

    def search_public_knowledge(query: str) -> str:
        if not query or not query.strip():
            return "查询内容为空。"

        related = _find_related_public_kbs(query, user_id, top_n=3)
        if not related:
            return "没有找到相关的公开知识库。"

        store = get_vector_store()
        blocks: list[str] = []
        for kb in related:
            try:
                results = store.search_with_score(kb["id"], query, k=4)
            except Exception:  # noqa: BLE001
                continue
            relevant = [r for r in results if r["score"] < CHUNK_DISTANCE_THRESHOLD]
            if not relevant:
                continue
            lines = [f"【公开库：{kb['name']}】"]
            for i, r in enumerate(relevant, 1):
                lines.append(f"  [{i}] 来源《{r['source']}》：{r['text']}")
            blocks.append("\n".join(lines))

        if not blocks:
            return "相关公开库中未检索到匹配内容。"
        return "\n\n".join(blocks)

    return search_public_knowledge
