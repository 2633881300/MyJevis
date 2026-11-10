"""MyJevis v0.2.0 前端 E2E 测试夹具。

两类被测目标：
  1. mock_base_url —— 只托管 static/ 的静态服务器，所有 API 由 Playwright 路由拦截。
     不依赖 MySQL / Chroma / 真实模型。
  2. live_base_url —— 起一个真实 uvicorn 进程，指向隔离库 my_jevis_test 与临时 Chroma 目录。
     外部模型调用（embedding / LLM）默认跳过，需 RUN_EXTERNAL=1。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytest.importorskip("playwright", reason="需要 playwright 才能运行 E2E 测试")

BACKEND_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BACKEND_DIR / "static"
TEST_DB = "my_jevis_test"


# --------------------------------------------------------------------------
# 标记注册（不引入 pytest.ini，避免影响既有测试的 rootdir 行为）
# --------------------------------------------------------------------------
def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: 浏览器端到端测试")
    config.addinivalue_line("markers", "integration: 需要真实后端的集成测试")
    config.addinivalue_line("markers", "external: 会调用真实模型接口，默认跳过")
    config.addinivalue_line("markers", "no_browser: 不启动浏览器的纯 Python 用例")


def pytest_collection_modifyitems(config, items):
    """未显式开启时跳过 external 用例，避免产生 API 费用。"""
    if os.getenv("RUN_EXTERNAL") == "1":
        return
    skip = pytest.mark.skip(reason="默认跳过：会调用真实 LLM / embedding（设 RUN_EXTERNAL=1 开启）")
    for item in items:
        if "external" in item.keywords:
            item.add_marker(skip)


# --------------------------------------------------------------------------
# 浏览器上下文默认参数
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
    }


# --------------------------------------------------------------------------
# 静态服务器（Mock E2E）
# --------------------------------------------------------------------------
class _QuietHandler(SimpleHTTPRequestHandler):
    # 浏览器一次并发请求 11 个静态文件。HTTP/1.1 + keep-alive 可以显著减少
    # 新建连接数，避免偶发的连接重置导致脚本没加载、整页空白。
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # noqa: D102  静默访问日志
        pass


@pytest.fixture(scope="session")
def mock_base_url():
    handler = partial(_QuietHandler, directory=str(STATIC_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


# --------------------------------------------------------------------------
# 真实后端（集成测试）
# --------------------------------------------------------------------------
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (URLError, OSError):
            time.sleep(0.4)
    return False


@pytest.fixture(scope="session")
def live_base_url(tmp_path_factory):
    """启动真实后端。数据库固定为 my_jevis_test，向量目录为本次会话的临时目录。"""
    port = _free_port()
    chroma_dir = tmp_path_factory.mktemp("chroma_e2e")

    env = os.environ.copy()
    env.update({
        "MYSQL_DATABASE": TEST_DB,
        "CHROMA_DIR": str(chroma_dir),
        # 覆盖成固定测试密钥，避免依赖本地 .env 的具体值
        "JWT_SECRET_KEY": "e2e-test-secret-" + "0" * 48,
    })

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base = f"http://127.0.0.1:{port}"
    if not _wait_http(base + "/health"):
        proc.terminate()
        out = b""
        try:
            out = proc.communicate(timeout=10)[0] or b""
        except subprocess.TimeoutExpired:
            proc.kill()
        pytest.skip("真实后端启动失败（可能缺少 MySQL）：\n" + out.decode("utf-8", "ignore")[-1500:])

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_e2e_data():
    """清理集成测试创建的 e2e_ 前缀账号及其关联数据。

    双重保险：库名不是 my_jevis_test 时直接放弃清理，
    避免误连开发库把真实用户数据带走。
    """
    yield

    try:
        from app.harness.config import settings
        from app.db import SessionLocal
        from app.models import Document, KnowledgeBase, User, UserProfile
    except Exception:  # 数据库不可用时直接跳过清理
        return

    if settings.mysql_database != TEST_DB:
        print(
            f"\n[SKIP CLEANUP] 当前数据库是 {settings.mysql_database!r}，"
            f"不是 {TEST_DB!r}，为避免影响开发数据，跳过清理。"
        )
        return

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.username.like("e2e_%")).all()
        for user in users:
            kb_ids = [k.id for k in db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).all()]
            if kb_ids:
                db.query(Document).filter(Document.knowledge_base_id.in_(kb_ids)).delete(synchronize_session=False)
                db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).delete(synchronize_session=False)
            db.query(UserProfile).filter(UserProfile.user_id == user.id).delete(synchronize_session=False)
            db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# --------------------------------------------------------------------------
# 浏览器辅助
# --------------------------------------------------------------------------
@pytest.fixture
def console_errors(page):
    """收集真正的 JS 异常与控制台 error；警告不计入。"""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on("console", lambda msg: errors.append(f"console.error: {msg.text}") if msg.type == "error" else None)
    return errors


@pytest.fixture
def failed_requests(page):
    """记录 4xx / 5xx 资源请求，用于检查静态资源 404。"""
    failed: list[tuple[str, int]] = []

    def _on_response(resp):
        if resp.status >= 400:
            failed.append((resp.url, resp.status))

    page.on("response", _on_response)
    return failed


def seed_auth(page, token="e2e-token", username="e2e_user"):
    """在页面加载前写入登录态（localStorage 与 store 初始化逻辑一致）。"""
    page.add_init_script(
        f"""try {{
            localStorage.setItem('mj_token', {json.dumps(token)});
            localStorage.setItem('mj_user', {json.dumps(username)});
        }} catch (e) {{}}"""
    )


# --------------------------------------------------------------------------
# 失败留证：截图 + DOM 快照
# --------------------------------------------------------------------------
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, "rep_" + report.when, report)


@pytest.fixture(autouse=True)
def _capture_failure_artifacts(request):
    """仅在浏览器用例失败时保存截图与 DOM；集成测试与纯 Python 用例不启动浏览器。"""
    keywords = request.node.keywords
    if "integration" in keywords or "no_browser" in keywords:
        yield
        return

    page = request.getfixturevalue("page")
    yield

    report = getattr(request.node, "rep_call", None)
    if not report or not report.failed:
        return

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    name = request.node.name.replace("/", "_").replace("::", "_")
    try:
        page.screenshot(path=str(ARTIFACT_DIR / f"{name}.png"), full_page=True)
    except Exception:
        pass
    try:
        (ARTIFACT_DIR / f"{name}.html").write_text(page.content(), encoding="utf-8")
        (ARTIFACT_DIR / f"{name}.txt").write_text(
            f"url: {page.url}\nviewport: {page.viewport_size}\n", encoding="utf-8"
        )
    except Exception:
        pass
