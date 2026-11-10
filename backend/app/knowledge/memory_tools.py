"""全局记忆工具：让 agent 能查询用户的知识库目录、文档清单、用户画像。

权限设计：
  user_id 由闭包在构建工具时绑定，不使用 contextvars。

  最初用 contextvars 隐式传递当前用户，但流式场景下 StreamingResponse 会把
  同步生成器丢到线程池迭代，ContextVar 可能跨线程丢失，导致工具拿到错误的
  用户（默认值 0）。改成闭包绑定后，user_id 是构建时的常量，与线程调度无关。
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from app.db import SessionLocal
from app.knowledge.permissions import AccessDenied, require_readable_kb
from app.models import Document, KnowledgeBase, UserProfile


# ===== 工具 1：列出我的知识库 =====


class ListKBsInput(BaseModel):
    """无参数。"""
    pass


def make_list_knowledge_bases(user_id: int) -> Callable[[], str]:
    """生成「列出我的知识库」工具。"""

    def list_knowledge_bases() -> str:
        db = SessionLocal()
        try:
            kbs = (
                db.query(KnowledgeBase)
                .filter(KnowledgeBase.user_id == user_id)
                .order_by(KnowledgeBase.created_at)
                .all()
            )
            if not kbs:
                return "当前用户还没有任何知识库。"
            lines = []
            for kb in kbs:
                flag = "公开" if kb.is_public else "私有"
                desc = f"，{kb.description}" if kb.description else ""
                lines.append(f"- [ID {kb.id}] {kb.name}（{flag}{desc}）")
            return "你的知识库：\n" + "\n".join(lines)
        finally:
            db.close()

    return list_knowledge_bases


# ===== 工具 2：列出某知识库的文档 =====


class ListDocsInput(BaseModel):
    knowledge_base_id: int = Field(description="要查询的知识库 ID")


def make_list_documents(user_id: int) -> Callable[[int], str]:
    """生成「列出某库文档」工具。"""

    def list_documents(knowledge_base_id: int) -> str:
        # 权限校验：只能看本人或公开的库
        try:
            kb_info = require_readable_kb(knowledge_base_id, user_id)
        except AccessDenied as e:
            return f"查询失败：{e}"

        db = SessionLocal()
        try:
            docs = (
                db.query(Document)
                .filter(Document.knowledge_base_id == knowledge_base_id)
                .order_by(Document.created_at.desc())
                .all()
            )
            if not docs:
                return f"知识库「{kb_info['name']}」下还没有文档。"
            lines = [
                f"- {d.filename}（{d.chunk_count} 个文本块，上传于 "
                f"{d.created_at.strftime('%Y-%m-%d %H:%M')}）"
                for d in docs
            ]
            return f"知识库「{kb_info['name']}」的文档：\n" + "\n".join(lines)
        finally:
            db.close()

    return list_documents


# ===== 工具 3：读用户画像 =====


class GetProfileInput(BaseModel):
    """无参数。"""
    pass


def make_get_user_profile(user_id: int) -> Callable[[], str]:
    """生成「读画像」工具。"""

    def get_user_profile() -> str:
        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if not profile or not profile.summary:
                return "暂无用户画像。"
            return profile.summary
        finally:
            db.close()

    return get_user_profile


# ===== 工具 4：更新用户画像 =====


class UpdateProfileInput(BaseModel):
    summary: str = Field(description="要保存的用户关键信息摘要（追加式更新）")


def make_update_user_profile(user_id: int) -> Callable[[str], str]:
    """生成「更新画像」工具。采用追加而非覆盖，避免新偏好冲掉旧画像。"""

    def update_user_profile(summary: str) -> str:
        text = (summary or "").strip()
        if not text:
            return "没有需要保存的内容。"

        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if profile:
                existing = (profile.summary or "").strip()
                if text in existing:
                    return "该信息已在画像中，无需重复保存。"
                profile.summary = f"{existing}\n- {text}" if existing else text
            else:
                db.add(UserProfile(user_id=user_id, summary=text))
            db.commit()
            return "用户画像已更新。"
        finally:
            db.close()

    return update_user_profile
