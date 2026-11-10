"""数据库层：SQLAlchemy 引擎、会话、建库建表。"""
from __future__ import annotations

import pymysql
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.harness.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _url(with_db: bool = True) -> str:
    db = f"/{settings.mysql_database}" if with_db else "/"
    return (
        f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}{db}?charset=utf8mb4"
    )


def ensure_database() -> None:
    """确保目标数据库存在（连服务器但不指定库，执行 CREATE DATABASE）。"""
    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


# 引擎与会话工厂（延迟到首次使用时才真正连接）
engine = create_engine(_url(), pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：每个请求一个会话，用完关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建库 + 建表（幂等）。"""
    ensure_database()
    # 导入模型以注册到 Base.metadata
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
