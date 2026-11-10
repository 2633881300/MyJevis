"""知识库接口：创建、列出、更新、删除。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.knowledge.store import get_vector_store
from app.models import Document, KnowledgeBase
from app.routers.chat import invalidate_master

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _to_response(kb: KnowledgeBase) -> schemas.KBResponse:
    return schemas.KBResponse(
        id=kb.id, name=kb.name, description=kb.description, is_public=kb.is_public
    )


@router.post("", response_model=schemas.KBResponse)
def create_kb(
    body: schemas.KBCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建知识库（默认私有）。"""
    uid = int(user["sub"])
    kb = KnowledgeBase(user_id=uid, name=body.name, description=body.description, is_public=False)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    invalidate_master()
    return _to_response(kb)


@router.get("", response_model=list[schemas.KBResponse])
def list_kbs(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """列出当前用户自己的知识库。"""
    uid = int(user["sub"])
    kbs = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.user_id == uid)
        .order_by(KnowledgeBase.created_at)
        .all()
    )
    return [_to_response(kb) for kb in kbs]


@router.get("/public", response_model=list[schemas.KBResponse])
def list_public_kbs(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """列出所有公开知识库（不含自己的）。"""
    uid = int(user["sub"])
    kbs = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.is_public == True, KnowledgeBase.user_id != uid)  # noqa: E712
        .all()
    )
    return [_to_response(kb) for kb in kbs]


@router.patch("/{kb_id}", response_model=schemas.KBResponse)
def update_kb(
    kb_id: int,
    body: schemas.KBUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新知识库（改名 / 改描述 / 切公开私有）。仅本人可操作。"""
    uid = int(user["sub"])
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == uid)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    if body.name is not None:
        kb.name = body.name
    if body.description is not None:
        kb.description = body.description
    if body.is_public is not None:
        kb.is_public = body.is_public

    db.commit()
    db.refresh(kb)
    invalidate_master()
    return _to_response(kb)


@router.delete("/{kb_id}")
def delete_kb(
    kb_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除知识库及其文档记录。仅本人可操作。"""
    uid = int(user["sub"])
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == uid)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    # 先删向量集合：真失败就中止，避免 MySQL 删了、向量还残留可被检索
    try:
        get_vector_store().delete_collection(kb_id)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="删除失败，请稍后重试")
    db.query(Document).filter(Document.knowledge_base_id == kb_id).delete()
    db.delete(kb)
    db.commit()
    invalidate_master()
    return {"message": "已删除"}
