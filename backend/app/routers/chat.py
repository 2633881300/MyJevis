"""问答接口：同步问答 + SSE 流式问答。

身份传递：不再使用 contextvars。
  user_id 从 JWT 解析后，直接作为参数传给 build_master_agent，由它闭包绑定到每个工具。
  这样即使 StreamingResponse 把同步生成器丢进线程池，身份也不会丢或串。
"""
from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app import schemas
from app.agents.master_agent import build_master_agent
from app.auth import get_current_user
from app.harness.harness import Harness

router = APIRouter(prefix="/chat", tags=["chat"])


@lru_cache(maxsize=32)
def _get_master(user_id: int) -> Harness:
    """按用户缓存总管家。

    构建一次就要为每个知识库新建子 agent（含 LLM 客户端 + 编译图），代价高。
    注意：缓存的实例里所有工具已绑定该 user_id，不同用户互不共享。
    """
    return build_master_agent(user_id)


def invalidate_master() -> None:
    """清空总管家缓存（知识库变动后调用）。"""
    _get_master.cache_clear()


@router.post("", response_model=schemas.ChatResponse)
def chat(body: schemas.ChatRequest, user: dict = Depends(get_current_user)):
    """同步问答。"""
    uid = int(user["sub"])
    master = _get_master(uid)
    result = master.run(body.question)
    return schemas.ChatResponse(
        answer=result["answer"],
        intermediate_steps=result["intermediate_steps"],
    )


@router.post("/stream")
def chat_stream(body: schemas.ChatRequest, user: dict = Depends(get_current_user)):
    """流式问答：SSE 逐段推送最终答案的 token。

    只推送「允许展示的最终回答」：中间轮次（带工具调用）的文本被 Harness 过滤掉，
    前端不会看到"我先去查一下"这类内部草稿。
    """
    uid = int(user["sub"])
    master = _get_master(uid)

    def event_generator():
        try:
            for piece in master.stream(body.question):
                yield f"data: {json.dumps({'type': 'token', 'data': piece}, ensure_ascii=False)}\n\n"
        except Exception:  # noqa: BLE001
            # 不把内部异常细节推给前端
            yield f"data: {json.dumps({'type': 'error', 'data': '服务暂时不可用，请稍后重试'}, ensure_ascii=False)}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done', 'data': ''}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
