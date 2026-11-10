"""权限回归测试：证明工具层不会越权。

这些测试直接调用工具函数（不经过 LLM），所以快且确定。
每个用例对应一个此前存在的真实漏洞。

运行：
    conda run -n Langgraph pytest tests/test_permissions.py -v
"""
from __future__ import annotations

import pytest

from app.db import SessionLocal, init_db
from app.knowledge.memory_tools import make_list_documents
from app.knowledge.permissions import (
    AccessDenied,
    require_owned_kb,
    require_readable_kb,
)
from app.knowledge.tools import make_search_knowledge
from app.models import KnowledgeBase, User

USER_A = "perm_test_a"
USER_B = "perm_test_b"


@pytest.fixture(scope="module")
def ids():
    """建两个用户：A 有一个私有库和一个公开库，B 什么都没有。"""
    init_db()
    db = SessionLocal()
    try:
        # 清理旧数据
        for name in (USER_A, USER_B):
            old = db.query(User).filter(User.username == name).first()
            if old:
                db.query(KnowledgeBase).filter(KnowledgeBase.user_id == old.id).delete()
                db.delete(old)
        db.commit()

        a = User(username=USER_A, password_hash="x")
        b = User(username=USER_B, password_hash="x")
        db.add_all([a, b])
        db.commit()
        db.refresh(a)
        db.refresh(b)

        kb_private = KnowledgeBase(user_id=a.id, name="A的私有库", is_public=False)
        kb_public = KnowledgeBase(user_id=a.id, name="A的公开库", is_public=True)
        db.add_all([kb_private, kb_public])
        db.commit()
        db.refresh(kb_private)
        db.refresh(kb_public)

        return {
            "a_id": a.id,
            "b_id": b.id,
            "kb_private": kb_private.id,
            "kb_public": kb_public.id,
        }
    finally:
        db.close()


# ===== 核心：工具层越权 =====


def test_b_cannot_read_private_kb(ids):
    """B 不能读 A 的私有库（require_readable_kb 必须拒绝）。"""
    with pytest.raises(AccessDenied):
        require_readable_kb(ids["kb_private"], ids["b_id"])


def test_b_can_read_public_kb(ids):
    """B 可以读 A 的公开库。"""
    info = require_readable_kb(ids["kb_public"], ids["b_id"])
    assert info["id"] == ids["kb_public"]


def test_b_cannot_own_a_kb(ids):
    """写操作必须要求所有权，公开也不行。"""
    with pytest.raises(AccessDenied):
        require_owned_kb(ids["kb_public"], ids["b_id"])


def test_search_tool_refuses_private_kb_of_other_user(ids):
    """越权的关键用例：工具的检索函数必须拒绝他人私有库。

    这正是修复前会泄露数据的路径 —— 模型猜测 kb_id 即可读取。
    """
    search_as_b = make_search_knowledge(ids["b_id"])
    out = search_as_b(ids["kb_private"], "任意问题")
    assert "检索失败" in out
    assert "无权" in out or "不存在" in out


def test_list_documents_refuses_private_kb_of_other_user(ids):
    """列出文档也要校验身份，否则会泄露文件名和上传时间。"""
    list_docs_as_b = make_list_documents(ids["b_id"])
    out = list_docs_as_b(ids["kb_private"])
    assert "查询失败" in out


def test_search_tool_handles_nonexistent_kb(ids):
    """不存在的库返回提示，不崩、不泄露内部异常。"""
    search_as_b = make_search_knowledge(ids["b_id"])
    out = search_as_b(999999, "任意问题")
    assert "检索失败" in out


def test_search_tool_handles_empty_query(ids):
    """空查询提前返回，不浪费 embedding 调用。"""
    search_as_b = make_search_knowledge(ids["b_id"])
    out = search_as_b(ids["kb_public"], "   ")
    assert "为空" in out


# ===== 用户身份不可伪造 =====


def test_user_id_is_bound_not_passed(ids):
    """工具的签名里没有 user_id —— 模型无法指定身份。"""
    search_as_b = make_search_knowledge(ids["b_id"])
    import inspect

    params = list(inspect.signature(search_as_b).parameters)
    assert "user_id" not in params
    assert params == ["knowledge_base_id", "query"]
