"""文档接口：上传入库、列表、删除。

一致性与安全设计：
  1. 上传顺序改为「先拿 doc_id，再写向量，最后提交」：
       parse → db.add(Document) + flush 拿 id → 写 Chroma → commit
     任一步失败：rollback MySQL，并按 doc_id 清理已写入的向量。
  2. 删除文档 / 删除知识库时，向量删除失败会中止 SQL 删除，
     避免「界面上没了、agent 还能检索到」。
  3. 支持 txt / md / markdown / docx / pdf；限 10MB（有界读取）；
     用 uuid 重命名临时文件（防路径穿越），原始文件名单独保存为 source。
"""
from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import schemas
from app.auth import get_current_user
from app.db import get_db
from app.knowledge.parser import ParseError, parse_document
from app.knowledge.store import get_vector_store
from app.models import Document, KnowledgeBase

router = APIRouter(prefix="/documents", tags=["documents"])

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".docx", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=schemas.DocumentResponse)
async def upload_document(
    knowledge_base_id: int = Form(..., description="目标知识库 ID"),
    file: UploadFile = File(..., description="要上传的文档（.md / .txt）"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传文档并入库（带失败回滚）。"""
    uid = int(user["sub"])

    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == uid)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {suffix}，仅支持 {', '.join(sorted(ALLOWED_SUFFIXES))}",
        )

    # 只取文件名部分，丢掉用户可能带的路径（防 "../../x.pdf" 这类）
    safe_name = Path(file.filename or f"upload{suffix}").name

    # 有界读取：最多多读 1 字节用于判断超限，避免一次性把任意大文件读进内存
    content = await file.read(MAX_FILE_SIZE + 1)
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过 10MB 限制")

    # 先解析，解析失败不留任何脏数据
    tmp_path = Path(tempfile.gettempdir()) / f"my_jevis_{uuid.uuid4().hex}{suffix}"
    try:
        tmp_path.write_bytes(content)
        try:
            # 传原始文件名：避免 chunk.source 变成 uuid 临时名
            chunks = parse_document(tmp_path, source_name=safe_name)
        except ParseError as e:
            # 解析器给出的具体原因（不支持 / 损坏 / 扫描版 / 加密 …）
            raise HTTPException(status_code=400, detail=str(e))
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="文档解析失败，请检查文件内容")
    finally:
        tmp_path.unlink(missing_ok=True)

    if not chunks:
        raise HTTPException(status_code=400, detail="文档解析后没有可入库的内容")

    # 关键顺序：先拿到 doc_id（flush 不提交），再用它构造向量 id
    doc = Document(
        knowledge_base_id=knowledge_base_id,
        filename=safe_name,
        chunk_count=len(chunks),
    )
    db.add(doc)
    db.flush()          # 拿到 doc.id，但事务还没提交

    store = get_vector_store()
    try:
        store.add_chunks(knowledge_base_id, doc.id, chunks)
        db.commit()
    except Exception:  # noqa: BLE001
        # 向量可能已部分写入 → 按 doc_id 清理；MySQL 回滚
        db.rollback()
        try:
            store.delete_document(knowledge_base_id, doc.id)
        except Exception:  # noqa: BLE001
            # 清理也失败：这些 chunk 不会出现在文档列表里，但仍可能被检索到。
            # 服务端记日志便于排查，不向用户暴露细节。
            logger.warning(
                "入库失败后清理向量同样失败，可能存在残留 chunk：kb=%s doc=%s",
                knowledge_base_id, doc.id, exc_info=True,
            )
        raise HTTPException(status_code=500, detail="文档入库失败，请稍后重试")

    db.refresh(doc)

    from app.routers.chat import invalidate_master

    invalidate_master()

    return schemas.DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
    )


@router.get("/list", response_model=list[schemas.DocumentResponse])
def list_documents(
    knowledge_base_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出某个知识库下的所有文档。"""
    uid = int(user["sub"])
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == uid)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    docs = (
        db.query(Document)
        .filter(Document.knowledge_base_id == knowledge_base_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        schemas.DocumentResponse(
            id=d.id, filename=d.filename, chunk_count=d.chunk_count, created_at=d.created_at
        )
        for d in docs
    ]


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除文档：同时清理向量，避免残留可被检索。"""
    uid = int(user["sub"])
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == doc.knowledge_base_id, KnowledgeBase.user_id == uid)
        .first()
    )
    if not kb:
        raise HTTPException(status_code=404, detail="文档不存在")

    kb_id = doc.knowledge_base_id
    # 必须先删向量成功，才删 SQL 记录；否则会出现「库里没了、内容还能检索到」
    try:
        get_vector_store().delete_document(kb_id, doc_id)
    except Exception:  # noqa: BLE001
        # 不自动降级删除，让用户可以重试
        raise HTTPException(status_code=500, detail="删除失败，请稍后重试")
    db.delete(doc)
    db.commit()

    from app.routers.chat import invalidate_master

    invalidate_master()
    return {"message": "已删除"}
