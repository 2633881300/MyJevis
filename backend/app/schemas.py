"""接口的请求"""
from __future__ import annotations

from pydantic import BaseModel,Field

from datetime import datetime

# ==== 认证 ====
class RegisterRequest(BaseModel):
    username: str = Field(...,min_length=2,max_length=32)
    password: str = Field(...,min_length=6)

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


# ===== 知识库 =====
class KBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""


class KBUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


class KBResponse(BaseModel):
    id: int
    name: str
    description: str
    is_public: bool


# ===== 文档 =====
class DocumentResponse(BaseModel):
    id: int
    filename: str
    chunk_count: int
    created_at: datetime


# ===== 问答 =====
class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    intermediate_steps: list = []