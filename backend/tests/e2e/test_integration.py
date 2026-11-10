"""真实后端集成验收（指向隔离库 my_jevis_test）。

默认执行：注册/登录、知识库 CRUD、文档列表、权限隔离。
标记 external：上传（需要 embedding）与问答（需要 LLM），默认跳过。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


class Client:
    def __init__(self, base: str, token: str | None = None):
        self.base = base.rstrip("/")
        self.token = token

    def _request(self, method: str, path: str, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return resp.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            try:
                parsed = json.loads(body) if body else None
            except json.JSONDecodeError:
                parsed = None
            return exc.code, parsed

    def get(self, path):
        return self._request("GET", path)

    def post(self, path, payload=None):
        return self._request("POST", path, payload)

    def patch(self, path, payload=None):
        return self._request("PATCH", path, payload)

    def delete(self, path):
        return self._request("DELETE", path)


def _new_user(live_base_url):
    username = "e2e_" + uuid.uuid4().hex[:10]
    password = uuid.uuid4().hex[:12]
    client = Client(live_base_url)
    status, data = client.post("/auth/register", {"username": username, "password": password})
    assert status == 200, data
    return username, password, data["access_token"], Client(live_base_url, data["access_token"])


def test_health(live_base_url):
    status, data = Client(live_base_url).get("/health")
    assert status == 200 and data["status"] == "healthy"


def test_register_login_and_me(live_base_url):
    username, password, token, client = _new_user(live_base_url)

    status, data = client.get("/auth/me")
    assert status == 200 and data["username"] == username

    anon = Client(live_base_url)
    status, _ = anon.post("/auth/login", {"username": username, "password": password})
    assert status == 200

    status, _ = anon.post("/auth/login", {"username": username, "password": "wrong-password"})
    assert status == 401


def test_duplicate_username_rejected(live_base_url):
    username, password, _, _ = _new_user(live_base_url)
    status, data = Client(live_base_url).post("/auth/register", {"username": username, "password": password})
    assert status == 400


def test_unauthenticated_requests_rejected(live_base_url):
    anon = Client(live_base_url)
    assert anon.get("/auth/me")[0] == 401
    assert anon.get("/knowledge-bases")[0] == 401
    assert anon.post("/chat", {"question": "hi"})[0] == 401


def test_kb_crud_flow(live_base_url):
    _, _, _, client = _new_user(live_base_url)

    status, kb = client.post("/knowledge-bases", {"name": "集成测试库", "description": "临时"})
    assert status == 200 and kb["is_public"] is False

    status, items = client.get("/knowledge-bases")
    assert status == 200 and any(k["id"] == kb["id"] for k in items)

    status, updated = client.patch(f"/knowledge-bases/{kb['id']}", {"name": "改名后", "is_public": True})
    assert status == 200 and updated["name"] == "改名后" and updated["is_public"] is True

    status, docs = client.get(f"/documents/list?knowledge_base_id={kb['id']}")
    assert status == 200 and docs == []

    status, _ = client.delete(f"/knowledge-bases/{kb['id']}")
    assert status == 200

    status, items = client.get("/knowledge-bases")
    assert all(k["id"] != kb["id"] for k in items)


def test_cannot_touch_other_users_kb(live_base_url):
    _, _, _, alice = _new_user(live_base_url)
    _, _, _, bob = _new_user(live_base_url)

    _, kb = alice.post("/knowledge-bases", {"name": "alice 的库"})

    # Bob 看不到、改不了、删不掉
    _, bob_list = bob.get("/knowledge-bases")
    assert all(k["id"] != kb["id"] for k in bob_list)
    assert bob.patch(f"/knowledge-bases/{kb['id']}", {"name": "劫持"})[0] == 404
    assert bob.delete(f"/knowledge-bases/{kb['id']}")[0] == 404
    assert bob.get(f"/documents/list?knowledge_base_id={kb['id']}")[0] == 404


@pytest.mark.external
def test_upload_and_chat(live_base_url):
    """会调用 embedding 与 LLM，默认跳过。"""
    _, _, _, client = _new_user(live_base_url)
    _, kb = client.post("/knowledge-bases", {"name": "外部调用库", "description": "临时"})

    boundary = "----e2e" + uuid.uuid4().hex
    content = "这是端到端测试文档。\n\n深海作业需要减压。"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"knowledge_base_id\"\r\n\r\n{kb['id']}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"e2e.txt\"\r\n"
        f"Content-Type: text/plain\r\n\r\n{content}\r\n--{boundary}--\r\n"
    ).encode("utf-8")

    req = urllib.request.Request(live_base_url + "/documents/upload", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", "Bearer " + client.token)
    with urllib.request.urlopen(req, timeout=120) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    assert doc["filename"] == "e2e.txt" and doc["chunk_count"] >= 1

    status, answer = client.post("/chat", {"question": "这份文档讲了什么？"})
    assert status == 200 and answer["answer"]
    assert isinstance(answer.get("intermediate_steps"), list)


def test_runs_against_isolated_database():
    """确认测试进程使用的是隔离库，而不是开发库 my_jevis。"""
    from app.harness.config import settings

    assert settings.mysql_database == "my_jevis_test", (
        f"测试数据库应为 my_jevis_test，实际为 {settings.mysql_database!r}"
    )
