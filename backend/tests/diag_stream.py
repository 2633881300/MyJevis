"""诊断脚本（非自动化测试）：打印 LangGraph stream_mode="messages" 的真实
事件结构，用于设计「只输出最终答案」的流式过滤规则。

用法（在 backend 目录下）：
    python -m tests.diag_stream [用户名]

不传用户名时取环境变量 DIAG_USER，再没有就用 "api_tester"。
会真实调用 LLM 与数据库，仅用于人工观察，不参与 pytest。
"""
from __future__ import annotations

import os
import sys

from app.agents.master_agent import build_master_agent
from app.db import SessionLocal
from app.models import KnowledgeBase, User

DEFAULT_USER = os.environ.get("DIAG_USER", "api_tester")


def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USER

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        if not u:
            print(f"找不到用户 {username!r}。请先在 Web 界面注册，或修改 DIAG_USER 环境变量。")
            return
        uid = u.id
        kbs = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == uid).all()
        print(f"user={username} user_id={uid}, 知识库: {[(k.id, k.name) for k in kbs]}")
    finally:
        db.close()

    master = build_master_agent(uid)
    from langchain_core.messages import HumanMessage

    state = {"messages": [HumanMessage(content="烫伤怎么处理？")]}

    print("\n=== stream_mode=messages 的 chunk 结构 ===")
    for i, (msg, meta) in enumerate(
        master._graph.stream(state, config={"recursion_limit": 20}, stream_mode="messages")
    ):
        content = getattr(msg, "content", "")
        if not isinstance(content, str) or not content:
            continue
        print(
            f"[{i}] node={meta.get('langgraph_node')!r} type={type(msg).__name__} "
            f"tool_calls={bool(getattr(msg, 'tool_calls', None))} "
            f"tags={meta.get('tags')} text={content[:25]!r}"
        )
        if i > 40:
            print("...")
            break


if __name__ == "__main__":
    main()
