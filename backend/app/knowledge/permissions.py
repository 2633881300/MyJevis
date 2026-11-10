"""知识库 / 文档访问权限校验。

核心原则：
  任何访问用户或知识库资源的工具，都必须在**真正读取数据之前**完成服务端校验。
  不能把鉴权交给 prompt —— 模型可以无视任何提示词。

本模块的函数都在数据访问路径上，被工具直接调用，而不是靠上层自觉。
"""
from __future__ import annotations

from app.db import SessionLocal
from app.models import Document, KnowledgeBase


class AccessDenied(Exception):
    """无权访问指定资源。"""


def require_readable_kb(kb_id: int, user_id: int) -> dict:
    """校验「可读」权限：本人的库，或他人公开的库。

    返回 {"id", "name", "owner_id"}，供调用方使用。
    """
    db = SessionLocal()
    try:
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if kb is None:
            # 不区分「不存在」和「无权」，避免探测他人库里有什么
            raise AccessDenied(f"知识库 {kb_id} 不存在或无权访问")
        if kb.user_id != user_id and not kb.is_public:
            raise AccessDenied(f"知识库 {kb_id} 不存在或无权访问")
        return {"id": kb.id, "name": kb.name, "owner_id": kb.user_id}
    finally:
        db.close()


def require_owned_kb(kb_id: int, user_id: int) -> dict:
    """校验「所有权」：只有本人的库才行（写操作必须用这个）。"""
    db = SessionLocal()
    try:
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if kb is None or kb.user_id != user_id:
            raise AccessDenied(f"知识库 {kb_id} 不存在或无权访问")
        return {"id": kb.id, "name": kb.name, "owner_id": kb.user_id}
    finally:
        db.close()


def require_owned_document(doc_id: int, user_id: int) -> Document:
    """校验文档归属：文档所在知识库必须属于当前用户。"""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc is None:
            raise AccessDenied(f"文档 {doc_id} 不存在")
        kb = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.id == doc.knowledge_base_id)
            .first()
        )
        if kb is None or kb.user_id != user_id:
            raise AccessDenied(f"文档 {doc_id} 不存在或无权访问")
        return doc
    finally:
        db.close()
