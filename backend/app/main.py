"""my_jevis 后端入口：FastAPI 应用。

启动（在 backend 目录下）：
    conda run -n Langgraph uvicorn app.main:app --reload --port 8000
或直接运行本文件。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.routers import auth, chat, documents, knowledge_bases

app = FastAPI(title="my_jevis API", version="0.1.0")

# 开发阶段放开跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(knowledge_bases.router)


@app.on_event("startup")
def on_startup() -> None:
    """启动时建库建表。"""
    init_db()


@app.get("/health")
def health():
    return {"status": "healthy"}


# 如果前端已经构建到 static/ 目录，就一起托管（单端口部署）
_static_dir = Path(__file__).resolve().parents[1] / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
