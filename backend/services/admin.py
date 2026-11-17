# -*- coding: utf-8 -*-
"""运营管理服务：风险规则配置/复核队列/官方任务/看板/审计/订单管理/用户管理/积分流水
（6.5 admin，v0.2 扩充：全部工单查询、订单详情与管理员取消、用户编辑、积分流水总览、看板趋势）。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (AuditLog, CreditLedger, CreditRule, OrderStatus, RiskRule,
                      User, WorkOrder)
from ..security import hash_password, require_admin

router = APIRouter()


def _audit(db: Session, action: str, target: str, detail: dict, operator: str) -> None:
    db.add(AuditLog(action=action, target=target, detail=detail, operator=operator))


# ---------------- 风险规则配置（R11） ----------------
class RiskRuleIn(BaseModel):
    dimension: str = "task_type"
    condition: str            # 如 "task_type=='代办跑腿'"
    level: str                # L1/L2/L3
    action: str               # auto_publish / warn_manual_review / block_and_guide
    official_channel_ref: str = ""
    adjust_reason: str = ""


@router.get("/api/v1/admin/risk-rules", tags=["运营管理服务"])
def list_risk_rules(db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    rows = db.scalars(select(RiskRule)).all()
    return {"items": [{"id": r.id, "dimension": r.dimension, "condition": r.condition, "level": r.level,
                       "action": r.action, "official_channel_ref": r.official_channel_ref,
                       "version": r.version, "updated_by": r.updated_by,
                       "adjust_reason": r.adjust_reason,
                       "updated_at": r.updated_at.isoformat() if r.updated_at else None} for r in rows]}


@router.post("/api/v1/admin/risk-rules", tags=["运营管理服务"])
def create_risk_rule(body: RiskRuleIn, payload: dict = Depends(require_admin), db: Session = Depends(get_db)):
    if body.level not in ("L1", "L2", "L3"):
        raise HTTPException(400, "level 必须是 L1/L2/L3")
    r = RiskRule(**body.model_dump(), version=1, updated_by=payload.get("name", "admin"))
    db.add(r)
    _audit(db, "risk_rule_create", f"risk_rule:{r.condition}", body.model_dump(), payload.get("name", ""))
    db.commit()
    db.refresh(r)
    return {"id": r.id}


@router.put("/api/v1/admin/risk-rules/{rule_id}", tags=["运营管理服务"])
def update_risk_rule(rule_id: int, body: RiskRuleIn, payload: dict = Depends(require_admin),
                     db: Session = Depends(get_db)):
    r = db.get(RiskRule, rule_id)
    if not r:
        raise HTTPException(404, "规则不存在")
    old = {"level": r.level, "action": r.action, "condition": r.condition}
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    r.version += 1
    r.updated_by = payload.get("name", "admin")
    _audit(db, "risk_rule_update", f"risk_rule:{rule_id}",
           {"old": old, "new": body.model_dump(), "reason": body.adjust_reason}, payload.get("name", ""))
    db.commit()
    return {"id": r.id, "version": r.version}


@router.delete("/api/v1/admin/risk-rules/{rule_id}", tags=["运营管理服务"])
def delete_risk_rule(rule_id: int, payload: dict = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(RiskRule, rule_id)
    if not r:
        raise HTTPException(404, "规则不存在")
    _audit(db, "risk_rule_delete", f"risk_rule:{rule_id}",
           {"condition": r.condition, "level": r.level}, payload.get("name", ""))
    db.delete(r)
    db.commit()
    return {"deleted": rule_id}


# ---------------- 人工复核队列（R12） ----------------
@router.get("/api/v1/admin/review-queue", tags=["运营管理服务"])
def review_queue(db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    rows = db.scalars(select(WorkOrder).where(WorkOrder.status == OrderStatus.PENDING_MANUAL_REVIEW.value)
                      .order_by(WorkOrder.id)).all()
    return {"items": [{
        "id": o.id, "work_order_no": o.work_order_no, "title": o.title,
        "task_type": o.task_type, "urgency": o.urgency, "location": o.location,
        "risk_level": o.risk_level, "risk_confidence": o.risk_confidence,
        "transcript": o.transcript, "status": o.status,
    } for o in rows]}


class ReviewDecideIn(BaseModel):
    decision: str            # approve / reject / reclassify
    new_level: str | None = None  # reclassify 时的新等级
    opinion: str = ""        # 复核意见（留痕）


@router.post("/api/v1/admin/review-queue/{order_id}/decide", tags=["运营管理服务"])
def review_decide(order_id: int, body: ReviewDecideIn, payload: dict = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """人工复核：通过（发布）/ 驳回（拦截）/ 改判（重设等级后发布或拦截）。"""
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(404, "工单不存在")
    if o.status != OrderStatus.PENDING_MANUAL_REVIEW.value:
        raise HTTPException(400, f"工单状态为 {o.status}，不在待复核队列")
    admin = payload.get("name", "admin")
    o.review_record = {"operator": admin, "decision": body.decision,
                       "opinion": body.opinion, "time": datetime.now().isoformat(),
                       "before_level": o.risk_level,
                       "after_level": body.new_level or o.risk_level}
    if body.decision == "approve":
        o.status = OrderStatus.PUBLISHED.value
    elif body.decision == "reject":
        o.blocked_reason = f"人工复核驳回：{body.opinion}"
        o.blocked_at = datetime.now()
        o.blocked_by = admin
        o.status = OrderStatus.BLOCKED.value
    elif body.decision == "reclassify":
        if body.new_level not in ("L1", "L2", "L3"):
            raise HTTPException(400, "new_level 必须是 L1/L2/L3")
        o.risk_level = body.new_level
        if body.new_level == "L3":
            o.blocked_reason = f"人工改判 L3 拦截：{body.opinion}"
            o.blocked_at = datetime.now()
            o.blocked_by = admin
            o.status = OrderStatus.BLOCKED.value
        else:
            o.status = OrderStatus.PUBLISHED.value
    else:
        raise HTTPException(400, "decision 必须是 approve/reject/reclassify")
    _audit(db, "manual_review", o.work_order_no, o.review_record, admin)
    db.commit()
    return {"id": o.id, "status": o.status, "risk_level": o.risk_level}


# ---------------- 官方志愿任务发布（R18） ----------------
class OfficialTaskIn(BaseModel):
    title: str
    task_type: str = "讲座会务"
    description: str = ""
    location: str = ""
    time_slot: str = ""
    tenant_id: str = "default"


@router.post("/api/v1/admin/official-tasks", tags=["运营管理服务"])
def create_official_task(body: OfficialTaskIn, payload: dict = Depends(require_admin), db: Session = Depends(get_db)):
    """官方志愿任务与个人工单同一任务广场展示（R18）。"""
    o = WorkOrder(
        work_order_no=f"OF{datetime.now():%Y%m%d%H%M%S}{db.query(WorkOrder.id).count() + 1:04d}",
        tenant_id=body.tenant_id, requester_id=int(payload["sub"]) if payload.get("sub") else 0,
        title=body.title, task_type=body.task_type, description=body.description,
        location=body.location, time_slot=body.time_slot,
        risk_level="L1", status=OrderStatus.PUBLISHED.value, is_official=True,
    )
    db.add(o)
    _audit(db, "official_task_create", o.work_order_no, body.model_dump(), payload.get("name", ""))
    db.commit()
    return {"id": o.id, "work_order_no": o.work_order_no, "status": o.status}


@router.get("/api/v1/admin/official-tasks", tags=["运营管理服务"])
def list_official_tasks(db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    rows = db.scalars(select(WorkOrder).where(WorkOrder.is_official == True)  # noqa: E712
                      .order_by(WorkOrder.id.desc())).all()
    return {"items": [{"id": o.id, "work_order_no": o.work_order_no, "title": o.title,
                       "task_type": o.task_type, "location": o.location, "time_slot": o.time_slot,
                       "description": o.description, "status": o.status,
                       "created_at": o.created_at.isoformat() if o.created_at else None} for o in rows]}


# ---------------- 订单管理（v0.2 新增：全部工单/详情/取消） ----------------
@router.get("/api/v1/admin/orders", tags=["运营管理服务"])
def admin_list_orders(status: str | None = None, risk_level: str | None = None,
                      keyword: str | None = None, is_official: bool | None = None,
                      page: int = 1, size: int = 20,
                      db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """管理端全量工单查询（含待复核/拦截/已取消），供「订单管理」页筛选。"""
    q = select(WorkOrder)
    if status:
        q = q.where(WorkOrder.status == status)
    if risk_level:
        q = q.where(WorkOrder.risk_level == risk_level)
    if is_official is not None:
        q = q.where(WorkOrder.is_official == is_official)
    rows = db.scalars(q.order_by(WorkOrder.id.desc())).all()
    if keyword:
        rows = [r for r in rows if keyword in r.title or keyword in r.description
                or keyword in r.location or keyword in r.work_order_no]
    users = {u.id: u.username for u in db.scalars(select(User)).all()}
    total = len(rows)
    items = []
    for r in rows[(page - 1) * size: page * size]:
        d = _order_admin_dto(r)
        d["requester"] = users.get(r.requester_id, str(r.requester_id))
        items.append(d)
    return {"total": total, "items": items}


def _order_admin_dto(o: WorkOrder) -> dict:
    return {
        "id": o.id, "work_order_no": o.work_order_no, "tenant_id": o.tenant_id,
        "requester_id": o.requester_id, "title": o.title, "transcript": o.transcript,
        "asr_confidence": o.asr_confidence, "task_type": o.task_type, "urgency": o.urgency,
        "location": o.location, "time_slot": o.time_slot, "description": o.description,
        "parse_confidence": o.parse_confidence, "risk_level": o.risk_level,
        "risk_confidence": o.risk_confidence, "status": o.status, "is_official": o.is_official,
        "blocked_reason": o.blocked_reason, "blocked_by": o.blocked_by,
        "official_channel_ref": o.official_channel_ref,
        "review_record": o.review_record, "completion_proof": o.completion_proof,
        "rating": o.rating,
        "volunteer_id": o.volunteer_id,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


@router.get("/api/v1/admin/orders/{order_id}", tags=["运营管理服务"])
def admin_order_detail(order_id: int, db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(404, "工单不存在")
    return _order_admin_dto(o)


@router.post("/api/v1/admin/orders/{order_id}/cancel", tags=["运营管理服务"])
def admin_cancel_order(order_id: int, body: dict | None = None, payload: dict = Depends(require_admin),
                       db: Session = Depends(get_db)):
    """管理员强制取消（终态），留痕。"""
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(404, "工单不存在")
    if o.status in (OrderStatus.BLOCKED.value, OrderStatus.EVALUATED.value, OrderStatus.CANCELLED.value):
        raise HTTPException(400, f"当前状态 {o.status} 不可取消")
    admin = payload.get("name", "admin")
    o.status = OrderStatus.CANCELLED.value
    o.blocked_reason = f"管理员取消：{(body or {}).get('reason', '')}"
    _audit(db, "admin_cancel", o.work_order_no, {"reason": (body or {}).get("reason", "")}, admin)
    db.commit()
    return {"id": o.id, "status": o.status}


# ---------------- 用户管理（v0.2 新增：新建/编辑/启用禁用/信用分调整） ----------------
class UserCreateIn(BaseModel):
    username: str
    password: str
    real_name: str = ""
    role: str = "student"
    tenant_id: str = "default"


class UserEditIn(BaseModel):
    real_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    tenant_id: str | None = None
    credit_delta: int | None = None      # 信用分增减（写流水）
    credit_reason: str = ""              # 调整依据（留痕）


@router.post("/api/v1/admin/users", tags=["运营管理服务"])
def admin_create_user(body: UserCreateIn, payload: dict = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(400, "用户名已存在")
    if body.role not in ("student", "senior", "admin"):
        raise HTTPException(400, "role 必须是 student/senior/admin")
    u = User(username=body.username, password_hash=hash_password(body.password),
             real_name=body.real_name, role=body.role, tenant_id=body.tenant_id)
    db.add(u)
    _audit(db, "user_create", body.username, {"role": body.role, "tenant_id": body.tenant_id},
           payload.get("name", ""))
    db.commit()
    db.refresh(u)
    return {"id": u.id, "username": u.username, "role": u.role}


@router.put("/api/v1/admin/users/{user_id}", tags=["运营管理服务"])
def admin_edit_user(user_id: int, body: UserEditIn, payload: dict = Depends(require_admin),
                    db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    admin = payload.get("name", "admin")
    changes: dict = {}
    for k in ("real_name", "role", "is_active", "tenant_id"):
        v = getattr(body, k)
        if v is not None:
            changes[k] = v
            setattr(u, k, v)
    if body.credit_delta is not None:
        u.credit_score = max(0, u.credit_score + body.credit_delta)
        db.add(CreditLedger(user_id=u.id, event="admin_adjust", delta=body.credit_delta,
                            remark=body.credit_reason or "管理员调整", operator=admin))
        changes["credit_delta"] = body.credit_delta
    _audit(db, "user_edit", u.username, changes, admin)
    db.commit()
    return {"id": u.id, "username": u.username, "real_name": u.real_name, "role": u.role,
            "is_active": u.is_active, "credit_score": u.credit_score}


# ---------------- 积分规则 / 积分流水 ----------------
@router.get("/api/v1/admin/credit-rules", tags=["运营管理服务"])
def list_credit_rules(db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    rows = db.scalars(select(CreditRule)).all()
    return {"items": [{"id": r.id, "rule_code": r.rule_code, "event": r.event, "condition": r.condition,
                       "delta": r.delta, "enabled": r.enabled, "version": r.version} for r in rows]}


class CreditRuleIn(BaseModel):
    rule_code: str
    event: str
    condition: str = "守约"
    delta: int
    enabled: bool = True


@router.post("/api/v1/admin/credit-rules", tags=["运营管理服务"])
def create_credit_rule(body: CreditRuleIn, payload: dict = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(CreditRule).where(CreditRule.rule_code == body.rule_code)):
        raise HTTPException(400, "规则编码已存在")
    r = CreditRule(**body.model_dump(), version=1, updated_by=payload.get("name", ""))
    db.add(r)
    _audit(db, "credit_rule_create", body.rule_code, body.model_dump(), payload.get("name", ""))
    db.commit()
    return {"id": r.id}


@router.put("/api/v1/admin/credit-rules/{rule_id}", tags=["运营管理服务"])
def update_credit_rule(rule_id: int, body: CreditRuleIn, payload: dict = Depends(require_admin),
                       db: Session = Depends(get_db)):
    r = db.get(CreditRule, rule_id)
    if not r:
        raise HTTPException(404, "规则不存在")
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    r.version += 1
    r.updated_by = payload.get("name", "")
    _audit(db, "credit_rule_update", body.rule_code, body.model_dump(), payload.get("name", ""))
    db.commit()
    return {"id": r.id, "version": r.version}


@router.delete("/api/v1/admin/credit-rules/{rule_id}", tags=["运营管理服务"])
def delete_credit_rule(rule_id: int, payload: dict = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(CreditRule, rule_id)
    if not r:
        raise HTTPException(404, "规则不存在")
    _audit(db, "credit_rule_delete", r.rule_code, {"delta": r.delta}, payload.get("name", ""))
    db.delete(r)
    db.commit()
    return {"deleted": rule_id}


@router.get("/api/v1/admin/credit-ledger", tags=["运营管理服务"])
def admin_credit_ledger(user_id: int | None = None, page: int = 1, size: int = 20,
                        db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """全平台积分流水（每笔可追溯事件/规则/操作人，R15）。"""
    q = select(CreditLedger)
    if user_id:
        q = q.where(CreditLedger.user_id == user_id)
    rows = db.scalars(q.order_by(CreditLedger.id.desc())).all()
    users = {u.id: u.username for u in db.scalars(select(User)).all()}
    total = len(rows)
    items = [{"id": r.id, "user_id": r.user_id, "user": users.get(r.user_id, str(r.user_id)),
              "order_id": r.order_id, "event": r.event, "delta": r.delta,
              "remark": r.remark, "operator": r.operator,
              "created_at": r.created_at.isoformat() if r.created_at else None}
             for r in rows[(page - 1) * size: page * size]]
    return {"total": total, "items": items}


# ---------------- 运营看板（v0.2：新增近7日趋势/今日数据） ----------------
@router.get("/api/v1/admin/dashboard", tags=["运营管理服务"])
def dashboard(db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """运营看板（T3.4）：基础计数 + 近7日新建/拦截趋势。"""
    total_orders = db.scalar(select(func.count(WorkOrder.id))) or 0
    by_status = dict(db.execute(select(WorkOrder.status, func.count(WorkOrder.id))
                                .group_by(WorkOrder.status)).all())
    by_level = dict(db.execute(select(WorkOrder.risk_level, func.count(WorkOrder.id))
                               .where(WorkOrder.risk_level != "")
                               .group_by(WorkOrder.risk_level)).all())
    # 近 7 日趋势（Python 侧聚合，Demo 数据量小）
    today = datetime.now().date()
    start = today - timedelta(days=6)
    rows = db.execute(select(WorkOrder.created_at, WorkOrder.status)).all()
    trend: dict[str, dict[str, int]] = {}
    for i in range(7):
        d = (start + timedelta(days=i)).isoformat()
        trend[d] = {"created": 0, "blocked": 0}
    for created_at, status in rows:
        if not created_at:
            continue
        d = created_at.date().isoformat()
        if d in trend:
            trend[d]["created"] += 1
            if status == OrderStatus.BLOCKED.value:
                trend[d]["blocked"] += 1
    today_str = today.isoformat()
    return {
        "total_users": db.scalar(select(func.count(User.id))) or 0,
        "total_orders": total_orders,
        "today_orders": trend.get(today_str, {}).get("created", 0),
        "orders_by_status": by_status,
        "orders_by_risk_level": by_level,
        "pending_review": by_status.get(OrderStatus.PENDING_MANUAL_REVIEW.value, 0),
        "blocked": by_status.get(OrderStatus.BLOCKED.value, 0),
        "official_tasks": db.scalar(select(func.count(WorkOrder.id)).where(WorkOrder.is_official == True)) or 0,  # noqa: E712
        "credit_flows": db.scalar(select(func.count(CreditLedger.id))) or 0,
        "trend_7d": trend,
        "generated_at": datetime.now().isoformat(),
    }


@router.get("/api/v1/admin/audit-logs", tags=["运营管理服务"])
def audit_logs(action: str | None = None, page: int = 1, size: int = 50,
               db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """审计日志（拦截日志/复核留痕/规则变更/登录，可追溯 R10/R11）。"""
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    rows = db.scalars(q.order_by(AuditLog.id.desc())).all()
    return {"total": len(rows), "items": [{
        "id": r.id, "action": r.action, "target": r.target, "detail": r.detail,
        "operator": r.operator, "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows[(page - 1) * size: page * size]]}
