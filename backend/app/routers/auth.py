"""认证接口：注册、登录。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenResponse)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户，成功后直接返回 token（省一次登录）。"""
    exists = db.query(User).filter(User.username == body.username).first()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return schemas.TokenResponse(
        access_token=create_access_token(user.id),
        username=user.username,
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    """登录，校验密码后签发 token。"""
    user = db.query(User).filter(User.username == body.username).first()
    # 用户不存在和密码错误返回同样的提示，避免暴露"这个用户名存在"
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return schemas.TokenResponse(
        access_token=create_access_token(user.id),
        username=user.username,
    )


@router.get("/me")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """返回当前登录用户的基本信息。"""
    u = db.query(User).filter(User.id == int(user["sub"])).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"id": u.id, "username": u.username}
