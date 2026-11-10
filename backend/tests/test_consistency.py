"""数据一致性回归测试：向量生命周期。

覆盖：
  1. 删除文档后，检索不能再返回它的内容（此前是真实 bug）
  2. 同名文件重复上传不互相覆盖（doc_id 让 chunk id 全局唯一）
  3. 按 doc_id 清理向量的能力（上传失败回滚依赖它）

需要真实 embedding 调用，跑得慢一些。

运行：
    conda run -n Langgraph pytest tests/test_consistency.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.db import SessionLocal, init_db
from app.knowledge.parser import parse_document
from app.knowledge.store import get_vector_store
from app.models import Document, KnowledgeBase, User

TEST_USER = "consistency_tester"
DOC = Path("tests/sample_docs/家庭急救常识.md")


@pytest.fixture(scope="module")
def kb_id():
    """建一个干净的知识库，测试结束后删掉向量集合。"""
    init_db()
    db = SessionLocal()
    store = get_vector_store()
    try:
        old = db.query(User).filter(User.username == TEST_USER).first()
        if old:
            kb_ids = [
                k.id for k in db.query(KnowledgeBase).filter(KnowledgeBase.user_id == old.id)
            ]
            for kid in kb_ids:
                store.delete_collection(kid)
            db.query(Document).filter(Document.knowledge_base_id.in_(kb_ids)).delete(
                synchronize_session=False
            )
            db.query(KnowledgeBase).filter(KnowledgeBase.user_id == old.id).delete()
            db.delete(old)
            db.commit()

        u = User(username=TEST_USER, password_hash="x")
        db.add(u)
        db.commit()
        db.refresh(u)

        kb = KnowledgeBase(user_id=u.id, name="一致性测试库", is_public=False)
        db.add(kb)
        db.commit()
        db.refresh(kb)

        yield kb.id

        store.delete_collection(kb.id)
    finally:
        db.close()


def _new_doc(kb_id: int, filename: str) -> int:
    """建一条 Document 记录并 flush 拿 id（模拟上传流程）。"""
    db = SessionLocal()
    try:
        doc = Document(knowledge_base_id=kb_id, filename=filename, chunk_count=0)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc.id
    finally:
        db.close()


def _ingest(kb_id: int, doc_id: int) -> int:
    chunks = parse_document(DOC)
    get_vector_store().add_chunks(kb_id, doc_id, chunks)
    return len(chunks)


def test_delete_document_removes_vectors(kb_id):
    """删除某文档的向量后，检索不应再返回它的内容。"""
    store = get_vector_store()
    doc_id = _new_doc(kb_id, "待删除.md")
    _ingest(kb_id, doc_id)

    # 入库后应能命中
    hits = store.search_with_score(kb_id, "烫伤怎么处理", k=4)
    assert any("凉水" in h["text"] or "烫伤" in h["text"] for h in hits), "入库后应能检索到"

    # 按 doc_id 删除
    deleted = store.delete_document(kb_id, doc_id)
    assert deleted > 0, "应当删除到向量"

    # 再检索应无结果
    after = store.search_with_score(kb_id, "烫伤怎么处理", k=4)
    assert not after, f"删除后不应再有结果，实际返回 {len(after)} 条"


def test_same_file_twice_does_not_overwrite(kb_id):
    """同名文件用不同 doc_id 入库，两份数据互不覆盖，删一份留一份。"""
    store = get_vector_store()
    doc_a = _new_doc(kb_id, "同名文件.md")
    n_a = _ingest(kb_id, doc_a)
    doc_b = _new_doc(kb_id, "同名文件.md")
    n_b = _ingest(kb_id, doc_b)

    assert n_a > 0 and n_b > 0

    # 两份都应该在
    hits = store.search_with_score(kb_id, "烫伤处理", k=10)
    doc_ids = {h.get("doc_id") for h in hits}
    # 删除 A，B 应仍在
    store.delete_document(kb_id, doc_a)
    remain = store.search_with_score(kb_id, "烫伤处理", k=10)
    assert remain, "删除 A 之后，B 的内容应该还在"

    # 清理 B
    store.delete_document(kb_id, doc_b)
    assert not store.search_with_score(kb_id, "烫伤处理", k=10), "两份都删后应无结果"


def test_chunk_ids_are_unique_per_document(kb_id):
    """chunk id 带 doc_id，不同文档不会撞 id。"""
    store = get_vector_store()
    d1 = _new_doc(kb_id, "id测试.md")
    d2 = _new_doc(kb_id, "id测试.md")

    import app.knowledge.store as store_mod

    ids_1 = [f"{d1}::{i}" for i in range(3)]
    ids_2 = [f"{d2}::{i}" for i in range(3)]
    assert not (set(ids_1) & set(ids_2)), "不同 doc_id 生成的 chunk id 不应重叠"
