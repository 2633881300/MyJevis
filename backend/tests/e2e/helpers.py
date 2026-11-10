"""Mock 后端与页面操作封装。

所有 API 都由 Playwright 路由拦截，返回结构严格对齐真实 FastAPI 响应：
  GET    /knowledge-bases                -> [{id, name, description, is_public}]
  POST   /knowledge-bases                -> 单个对象
  PATCH  /knowledge-bases/{id}           -> 单个对象
  DELETE /knowledge-bases/{id}           -> {"message": "已删除"}
  GET    /documents/list?knowledge_base_id= -> [{id, filename, chunk_count, created_at}]
  POST   /documents/upload               -> 单个对象
  DELETE /documents/{id}                 -> {"message": ...}
  POST   /chat/stream                     -> text/event-stream，事件 {type, data}
  POST   /chat                            -> {answer, intermediate_steps:[{tool,args,result}]}
"""
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("myjevis.e2e")

API_PATTERNS = ("**/auth/**", "**/knowledge-bases**", "**/documents/**", "**/chat**")


class ApiMock:
    def __init__(self, page):
        self.page = page
        self.kbs: list[dict] = []
        self.docs: dict[int, list[dict]] = {}
        self.calls: list[tuple[str, str]] = []
        self._kb_seq = 1
        self._doc_seq = 1

        # 可调节的响应行为
        self.login_error: tuple[int, str] | None = None
        self.register_error: tuple[int, str] | None = None
        self.kb_list_error: tuple[int, str] | None = None
        self.doc_list_error: tuple[int, str] | None = None
        self.upload_error: tuple[int, str] | None = None
        self.stream_status = 200
        self.stream_frames: list[dict] | None = None
        self.stream_delay_ms = 0
        self.detail_status = 200
        self.detail_body: dict | None = None
        self.chat_delay_ms = 0

        for pattern in API_PATTERNS:
            page.route(pattern, self._dispatch)

    # ---------------- 数据构造 ----------------
    def add_kb(self, name: str, description: str = "", is_public: bool = False) -> dict:
        kb = {"id": self._kb_seq, "name": name, "description": description, "is_public": is_public}
        self._kb_seq += 1
        self.kbs.append(kb)
        self.docs[kb["id"]] = []
        return kb

    def add_doc(self, kb_id: int, filename: str, chunk_count: int = 2,
                created_at: str = "2026-11-08T11:27:00") -> dict:
        doc = {
            "id": self._doc_seq,
            "filename": filename,
            "chunk_count": chunk_count,
            "created_at": created_at,
        }
        self._doc_seq += 1
        self.docs.setdefault(kb_id, []).append(doc)
        return doc

    # ---------------- 请求断言辅助 ----------------
    def called(self, method: str, path_prefix: str) -> bool:
        return any(m == method and p.startswith(path_prefix) for m, p in self.calls)

    def count(self, method: str, path_prefix: str) -> int:
        return sum(1 for m, p in self.calls if m == method and p.startswith(path_prefix))

    # ---------------- 路由分发 ----------------
    def _json(self, route, status: int, payload) -> None:
        route.fulfill(
            status=status,
            headers={"content-type": "application/json; charset=utf-8"},
            body=json.dumps(payload, ensure_ascii=False),
        )

    def _sse(self, route, frames: list[dict], status: int = 200) -> None:
        body = "".join(
            f"data: {json.dumps(f, ensure_ascii=False)}\n\n" for f in frames
        )
        route.fulfill(
            status=status,
            headers={
                "content-type": "text/event-stream; charset=utf-8",
                "cache-control": "no-cache",
            },
            body=body,
        )

    def _default_frames(self) -> list[dict]:
        return [
            {"type": "token", "data": "这是"},
            {"type": "token", "data": "流式回答。"},
            {"type": "done", "data": ""},
        ]

    def _dispatch(self, route) -> None:
        req = route.request
        parsed = urlparse(req.url)
        path = parsed.path
        method = req.method

        # 只拦截真正的 API。静态资源（如 /js/views/chat.js）必须放行，
        # 否则会被通配模式误伤，导致组件注册失败。
        if not path.startswith(("/auth/", "/knowledge-bases", "/documents", "/chat")):
            return route.fallback()

        self.calls.append((method, path))

        if path == "/auth/login":
            if self.login_error:
                return self._json(route, self.login_error[0], {"detail": self.login_error[1]})
            body = req.post_data_json or {}
            return self._json(route, 200, {
                "access_token": "mock-token",
                "token_type": "bearer",
                "username": body.get("username") or "mock_user",
            })

        if path == "/auth/register":
            if self.register_error:
                return self._json(route, self.register_error[0], {"detail": self.register_error[1]})
            body = req.post_data_json or {}
            return self._json(route, 200, {
                "access_token": "mock-token",
                "token_type": "bearer",
                "username": body.get("username") or "mock_user",
            })

        if path == "/knowledge-bases/public":
            return self._json(route, 200, [k for k in self.kbs if k["is_public"]])

        if path == "/knowledge-bases":
            if method == "GET":
                if self.kb_list_error:
                    return self._json(route, self.kb_list_error[0], {"detail": self.kb_list_error[1]})
                return self._json(route, 200, self.kbs)
            if method == "POST":
                body = req.post_data_json or {}
                kb = self.add_kb(body.get("name", ""), body.get("description", ""), False)
                return self._json(route, 200, kb)

        if path.startswith("/knowledge-bases/"):
            try:
                kb_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                return self._json(route, 404, {"detail": "知识库不存在"})

            kb = next((k for k in self.kbs if k["id"] == kb_id), None)
            if kb is None:
                return self._json(route, 404, {"detail": "知识库不存在"})

            if method == "PATCH":
                body = req.post_data_json or {}
                for field in ("name", "description", "is_public"):
                    if field in body and body[field] is not None:
                        kb[field] = body[field]
                return self._json(route, 200, kb)

            if method == "DELETE":
                self.kbs = [k for k in self.kbs if k["id"] != kb_id]
                self.docs.pop(kb_id, None)
                return self._json(route, 200, {"message": "已删除"})

        if path == "/documents/list":
            if self.doc_list_error:
                return self._json(route, self.doc_list_error[0], {"detail": self.doc_list_error[1]})
            kb_id = int(parse_qs(parsed.query).get("knowledge_base_id", ["0"])[0])
            return self._json(route, 200, self.docs.get(kb_id, []))

        if path == "/documents/upload":
            if self.upload_error:
                return self._json(route, self.upload_error[0], {"detail": self.upload_error[1]})
            kb_id = 1
            raw = req.post_data_buffer or b""
            matched = re.search(rb'name="knowledge_base_id"\r\n\r\n(\d+)', raw)
            if matched:
                kb_id = int(matched.group(1))
            name = "上传文档.txt"
            name_matched = re.search(rb'filename="([^"]+)"', raw)
            if name_matched:
                name = name_matched.group(1).decode("utf-8", "ignore")
            doc = self.add_doc(kb_id, name, 3)
            return self._json(route, 200, doc)

        if path.startswith("/documents/"):
            if method == "DELETE":
                try:
                    doc_id = int(path.rsplit("/", 1)[-1])
                except ValueError:
                    return self._json(route, 404, {"detail": "文档不存在"})
                for kb_id, items in self.docs.items():
                    self.docs[kb_id] = [d for d in items if d["id"] != doc_id]
                return self._json(route, 200, {"message": "已删除"})

        if path == "/chat/stream":
            if self.stream_delay_ms:
                time.sleep(self.stream_delay_ms / 1000)
            frames = self.stream_frames if self.stream_frames is not None else self._default_frames()
            return self._sse(route, frames, status=self.stream_status)

        if path == "/chat":
            if self.chat_delay_ms:
                time.sleep(self.chat_delay_ms / 1000)
            if self.detail_status != 200:
                return self._json(route, self.detail_status, {"detail": "服务暂时不可用"})
            body = self.detail_body or {
                "answer": "详细模式回答。",
                "intermediate_steps": [
                    {"tool": "ask_kb_1", "args": {"question": "测试问题"}, "result": "子 Agent 回答内容"},
                ],
            }
            return self._json(route, 200, body)

        return self._json(route, 404, {"detail": "未拦截的接口: " + path})


# ---------------- 页面操作 ----------------
def goto_app(page, base_url: str, token: str | None = None, username: str = "e2e_user"):
    """打开首页；token 非空时先写入 localStorage 再加载。

    连续跑整套用例时，偶发首屏尚未渲染完成就进入断言。这里显式等待
    「登录卡片或工作台」出现，失败后重载一次（只重试加载，不放宽断言）。
    """
    if token:
        page.add_init_script(
            f"""try {{
                localStorage.setItem('mj_token', {json.dumps(token)});
                localStorage.setItem('mj_user', {json.dumps(username)});
            }} catch (e) {{}}"""
        )
    page.goto(base_url + "/", wait_until="domcontentloaded")
    try:
        page.wait_for_selector('[data-testid="auth-card"], [data-testid="chat"]', timeout=8000)
    except Exception as exc:  # noqa: BLE001
        # 不静默掩盖：重试必须留下日志，否则资源加载失败会被当成偶发波动忽略
        logger.warning(
            "首屏未在 8s 内完成渲染，重载一次。url=%s base=%s 原因=%s: %s",
            page.url if hasattr(page, "url") else "?",
            base_url,
            type(exc).__name__,
            exc,
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector('[data-testid="auth-card"], [data-testid="chat"]', timeout=15000)
    page.wait_for_timeout(200)


def login_ui(page, username: str, password: str):
    page.locator('[data-testid="auth-username"]').fill(username)
    page.locator('[data-testid="auth-password"]').fill(password)
    page.locator('[data-testid="auth-submit"]').click()


def ask(page, question: str):
    box = page.locator('[data-testid="chat-input"]')
    box.fill(question)
    page.locator('[data-testid="chat-send"]').click()


def assistant_texts(page) -> list[str]:
    return page.locator('[data-testid="msg"][data-role="assistant"] [data-testid="msg-text"]').all_inner_texts()


def last_assistant_text(page) -> str:
    texts = assistant_texts(page)
    return texts[-1] if texts else ""
