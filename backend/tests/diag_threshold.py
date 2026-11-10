"""诊断：实测 bge-m3 下「问题 vs 库名+描述」的余弦相似度分布，用来定阈值。"""
from __future__ import annotations

from app.knowledge.embedding import get_embedding_client

KB_TEXTS = [
    "计算机知识 操作系统、数据库、计算机网络等计算机基础知识的速查手册",
    "急救常识 家庭急救处理",
    "烹饪菜谱 家常菜做法",
]

QUERIES = [
    "死锁产生的四个必要条件是什么？",
    "烫伤之后应该怎么处理？",
    "法国大革命是什么时候？",
    "红烧肉怎么做？",
]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def main() -> None:
    embed = get_embedding_client()
    kb_vecs = embed.embed_texts(KB_TEXTS)

    for q in QUERIES:
        qv = embed.embed_texts([q])[0]
        scores = [(cosine(qv, kv), KB_TEXTS[i].split(" ")[0]) for i, kv in enumerate(kb_vecs)]
        scores.sort(reverse=True)
        print(f"\n问：{q}")
        for s, name in scores:
            print(f"   {s:.4f}  ← {name}")


if __name__ == "__main__":
    main()
