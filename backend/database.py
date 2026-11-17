# -*- coding: utf-8 -*-
"""数据库连接与会话管理（SQLAlchemy 2.x + SQLite）。
租户字段 tenant_id 贯穿所有业务表，为 R16 多租户隔离打基础。"""
from datetime import datetime

from sqlalchemy import create_engine, DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DB_PATH

# check_same_thread=False：FastAPI 多线程访问 SQLite 必需
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
metadata = MetaData()


class Base(DeclarativeBase):
    """声明式基类，统一时间戳字段。"""
    metadata = metadata


def _dt():
    return datetime.now()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_dt)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_dt, onupdate=_dt)


def get_db():
    """FastAPI 依赖：每请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
