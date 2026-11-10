"""失败路径测试：验证「向量删除失败时不能删 SQL 记录」等关键分支。

用故障注入（monkeypatch）模拟 Chroma 删除失败，断言：
  - 接口返回 5xx
  - 文档记录仍然存在（用户还能重试，不会出现「列表没了、内容还能检索」）

运行：
    conda run -n Langgraph pytest tests/test_failure_modes.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.knowledge.store import get_vector_store
from app.main import app


@pytest.fixture(scope="module")
def client_and_ctx():
    """注册用户 → 建库 → 上传一份文档，返回 (client, headers, kb_id, doc_id)。"""
    client = TestClient(app)
    # 测试夹具账号：只在隔离库 my_jevis_test 中创建，不是任何环境的真实凭据
    username = "failure_mode_tester"
    password = "test123456"

    r = client.post("/auth/register", json={"username": username, "password": password})
    if r.status_code != 200:
        r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    kb = client.post("/knowledge-bases", json={"name": "故障测试库"}, headers=headers)
    assert kb.status_code == 200, kb.text
    kb_id = kb.json()["id"]

    with open("tests/sample_docs/家庭急救常识.md", "rb") as f:
        up = client.post(
            "/documents/upload",
            data={"knowledge_base_id": kb_id},
            files={"file": ("急救.md", f, "text/markdown")},
            headers=headers,
        )
    assert up.status_code == 200, up.text
    doc_id = up.json()["id"]

    return client, headers, kb_id, doc_id


def test_delete_document_raises_when_nothing_deleted(client_and_ctx):
    """删一个不存在 doc_id：必须抛异常，而不是静默返回 0。"""
    store = get_vector_store()
    _, _, kb_id, _ = client_and_ctx
    with pytest.raises(RuntimeError):
        store.delete_document(kb_id, 99999999)


def test_api_delete_keeps_sql_when_vector_delete_fails(client_and_ctx, monkeypatch):
    """向量删除失败 → 接口 5xx，且文档记录不能丢。"""
    client, headers, kb_id, doc_id = client_and_ctx
    store = get_vector_store()

    def _boom(*args, **kwargs):
        raise RuntimeError("模拟 Chroma 故障")

    monkeypatch.setattr(store, "delete_document", _boom)

    resp = client.delete(f"/documents/{doc_id}", headers=headers)
    assert resp.status_code == 500, f"应返回 5xx，实际 {resp.status_code}"

    # 关键断言：SQL 记录还在（用户可以重试）
    listed = client.get(f"/documents/list?knowledge_base_id={kb_id}", headers=headers)
    assert listed.status_code == 200
    ids = [d["id"] for d in listed.json()]
    assert doc_id in ids, "向量删除失败时，文档记录不应被删除"


def test_api_delete_succeeds_when_vector_delete_works(client_and_ctx):
    """正常路径：向量删除成功后才删 SQL 记录。"""
    client, headers, kb_id, doc_id = client_and_ctx

    resp = client.delete(f"/documents/{doc_id}", headers=headers)
    assert resp.status_code == 200, resp.text

    listed = client.get(f"/documents/list?knowledge_base_id={kb_id}", headers=headers)
    ids = [d["id"] for d in listed.json()]
    assert doc_id not in ids


# ===== 解析失败时必须不留脏数据 =====


def _count_docs(client, headers, kb_id: int) -> int:
    r = client.get(f"/documents/list?knowledge_base_id={kb_id}", headers=headers)
    assert r.status_code == 200
    return len(r.json())


def test_upload_corrupted_pdf_leaves_no_record(client_and_ctx):
    """损坏的 PDF：返回 4xx，且不产生 Document 记录。"""
    client, headers, kb_id, _ = client_and_ctx
    before = _count_docs(client, headers, kb_id)

    resp = client.post(
        "/documents/upload",
        data={"knowledge_base_id": kb_id},
        files={"file": ("broken.pdf", b"not a pdf at all", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 400, f"应返回 400，实际 {resp.status_code}: {resp.text}"
    assert _count_docs(client, headers, kb_id) == before, "解析失败不应留下文档记录"


def test_upload_scanned_pdf_leaves_no_record(client_and_ctx):
    """无文本层的 PDF（模拟扫描版）：返回 400 并给出明确提示。"""
    from tests.test_parser import _make_pdf

    client, headers, kb_id, _ = client_and_ctx
    before = _count_docs(client, headers, kb_id)

    resp = client.post(
        "/documents/upload",
        data={"knowledge_base_id": kb_id},
        files={"file": ("scan.pdf", _make_pdf([""]), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert "文本" in resp.json()["detail"], f"提示应说明无法提取文本：{resp.json()}"
    assert _count_docs(client, headers, kb_id) == before


def test_upload_unsupported_suffix_rejected(client_and_ctx):
    """不在白名单里的类型直接拒绝。"""
    client, headers, kb_id, _ = client_and_ctx
    resp = client.post(
        "/documents/upload",
        data={"knowledge_base_id": kb_id},
        files={"file": ("old.doc", b"legacy", "application/msword")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]


# ===== 来源文件名必须是原始文件名，不能是 uuid 临时名 =====


def test_upload_keeps_original_filename_as_source(client_and_ctx):
    """上传用的临时文件被 uuid 重命名，但 chunk.source 必须是用户原始文件名。

    这是此前的一个真实 Bug：source 落成了 my_jevis_<uuid>.pdf。
    """
    from tests.test_parser import _make_pdf

    client, headers, kb_id, _ = client_and_ctx
    original = "急救要点.pdf"

    resp = client.post(
        "/documents/upload",
        data={"knowledge_base_id": kb_id},
        files={"file": (original, _make_pdf(["Source name check content"]), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["filename"] == original
    doc_id = resp.json()["id"]

    hits = get_vector_store().search_with_score(kb_id, "Source name check content", k=5)
    matched = [h for h in hits if h["doc_id"] == doc_id]
    assert matched, "应能检索到刚上传的文档"
    assert matched[0]["source"] == original, f"source 应为原始文件名，实际 {matched[0]['source']!r}"
    assert not matched[0]["source"].startswith("my_jevis_"), "source 不能是 uuid 临时文件名"


# ===== 删除知识库：向量删除失败必须中止 =====


def test_delete_kb_aborts_when_vector_delete_fails(client_and_ctx, monkeypatch):
    """向量集合删除失败时，知识库和文档记录都不能被删掉。"""
    client, headers, _, _ = client_and_ctx

    # 单独建一个库，避免影响其他用例
    created = client.post("/knowledge-bases", json={"name": "删除故障库"}, headers=headers)
    assert created.status_code == 200
    tmp_kb = created.json()["id"]

    store = get_vector_store()

    def _boom(_kb_id):
        raise RuntimeError("模拟 Chroma 删除故障")

    monkeypatch.setattr(store, "delete_collection", _boom)

    resp = client.delete(f"/knowledge-bases/{tmp_kb}", headers=headers)
    assert resp.status_code == 500, f"应返回 5xx，实际 {resp.status_code}"

    listed = client.get("/knowledge-bases", headers=headers)
    ids = [k["id"] for k in listed.json()]
    assert tmp_kb in ids, "向量删除失败时，知识库记录不应被删除"


def test_delete_kb_succeeds_when_collection_missing(client_and_ctx):
    """从未上传过文档的库（没有 collection）也应能正常删除。"""
    client, headers, _, _ = client_and_ctx

    created = client.post("/knowledge-bases", json={"name": "空库"}, headers=headers)
    tmp_kb = created.json()["id"]

    resp = client.delete(f"/knowledge-bases/{tmp_kb}", headers=headers)
    assert resp.status_code == 200, resp.text

    listed = client.get("/knowledge-bases", headers=headers)
    ids = [k["id"] for k in listed.json()]
    assert tmp_kb not in ids
