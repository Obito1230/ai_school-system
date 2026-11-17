# -*- coding: utf-8 -*-
"""数据模型（对应计划第6章数据契约）。"""
import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, TimestampMixin


class RiskLevel(str, enum.Enum):
    L1 = "L1"  # 低风险：自动发布
    L2 = "L2"  # 中风险：预警+人工复核
    L3 = "L3"  # 高风险：拦截


class OrderStatus(str, enum.Enum):
    CREATED = "created"
    AI_REVIEWING = "ai_reviewing"
    PENDING_MANUAL_REVIEW = "pending_manual_review"
    BLOCKED = "blocked"
    PUBLISHED = "published"
    MATCHING = "matching"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EVALUATED = "evaluated"
    CANCELLED = "cancelled"


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    real_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="student")  # student/senior/admin
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)  # 学院/校区租户
    credit_score: Mapped[int] = mapped_column(Integer, default=100)  # 互助信用分（R13/R15）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RiskRule(Base, TimestampMixin):
    """风险规则表（R11：管理员配置，改配置即生效，留痕）。"""
    __tablename__ = "risk_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dimension: Mapped[str] = mapped_column(String(32))  # task_type / urgency / scope
    condition: Mapped[str] = mapped_column(String(128))  # 条件表达式，如 "task_type==代办跑腿"
    level: Mapped[str] = mapped_column(String(4))  # L1/L2/L3
    action: Mapped[str] = mapped_column(String(32))  # auto_publish / warn_manual_review / block_and_guide
    official_channel_ref: Mapped[str] = mapped_column(String(256), default="")  # 官方渠道指引
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    adjust_reason: Mapped[str] = mapped_column(String(256), default="")


class WorkOrder(Base, TimestampMixin):
    """工单表（6.1 work_order）。"""
    __tablename__ = "work_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # 展示编号 WO+日期+序号
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    requester_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    transcript: Mapped[str] = mapped_column(Text, default="")  # ASR 转写文本
    asr_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    task_type: Mapped[str] = mapped_column(String(32), default="其他")  # 任务类型
    urgency: Mapped[str] = mapped_column(String(16), default="普通")  # 紧急程度
    location: Mapped[str] = mapped_column(String(128), default="")
    time_slot: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    parse_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(4), default="")  # L1/L2/L3（AI 初判，管理员可改判）
    risk_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.CREATED.value, index=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)  # 官方志愿任务（R18）
    blocked_reason: Mapped[str] = mapped_column(Text, default="")
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    blocked_by: Mapped[str] = mapped_column(String(128), default="")
    official_channel_ref: Mapped[str] = mapped_column(String(256), default="")
    review_record: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 人工复核留痕
    volunteer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 接单志愿者
    completion_proof: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {score, comment, rated_by}


class CreditRule(Base, TimestampMixin):
    """积分规则（6.4 credit_rule）。"""
    __tablename__ = "credit_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(64), unique=True)
    event: Mapped[str] = mapped_column(String(32))  # publish/accept/complete/rate
    condition: Mapped[str] = mapped_column(String(64), default="守约")
    delta: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="")


class CreditLedger(Base, TimestampMixin):
    """积分流水（每笔可追溯到事件/规则版本/操作人，R15）。"""
    __tablename__ = "credit_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event: Mapped[str] = mapped_column(String(32))
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delta: Mapped[int] = mapped_column(Integer)
    remark: Mapped[str] = mapped_column(String(256), default="")
    operator: Mapped[str] = mapped_column(String(64), default="system")


class AuditLog(Base, TimestampMixin):
    """操作审计：拦截日志、复核留痕、规则变更留痕、登录等（R10/R11）。"""
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), index=True)  # login / block / review / rule_change ...
    target: Mapped[str] = mapped_column(String(128), default="")  # 对象，如工单号
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    operator: Mapped[str] = mapped_column(String(64), default="system")
