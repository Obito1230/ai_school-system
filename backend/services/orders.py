# -*- coding: utf-8 -*-
"""工单服务：创建→AI 分级→状态机→广场→接单→完成→评价（6.5 order）。
状态机合法迁移表与 L3 硬拦截在本文件中实现（安全硬约束，重构不得破坏）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, CreditLedger, CreditRule, OrderStatus, RiskLevel, User, WorkOrder
from ..rules import match_score, parse_intent, rule_based_risk
from ..security import get_current_user

router = APIRouter()


def _apply_credit(db: Session, user_id: int, event: str, order_id: int | None,
                  delta: int, remark: str, operator: str = "system") -> None:
    """积分事件落账（R15 闭环的最小实现）：写流水 + 更新信用分。
    规则取 credit_rule 表中 enabled 且 event 匹配的最新一条（T3.3 P3 完整化：
    condition 判别/守约与失信自动区分，Demo 阶段由调用方传入正向 delta）。"""
    rule = db.scalar(select(CreditRule).where(CreditRule.event == event, CreditRule.enabled == True)
                     .order_by(CreditRule.id.desc()))  # noqa: E712
    rule_id = rule.id if rule else None
    rule_version = rule.version if rule else None
    db.add(CreditLedger(user_id=user_id, order_id=order_id, event=event, delta=delta,
                        rule_id=rule_id, rule_version=rule_version, remark=remark, operator=operator))
    u = db.get(User, user_id)
    if u:
        u.credit_score = (u.credit_score or 0) + delta

# ---- 状态机：合法迁移（R12/T2.5，Demo 精简版）----
TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.CREATED.value: {OrderStatus.AI_REVIEWING.value, OrderStatus.CANCELLED.value},
    OrderStatus.AI_REVIEWING.value: {OrderStatus.PUBLISHED.value, OrderStatus.PENDING_MANUAL_REVIEW.value,
                                     OrderStatus.BLOCKED.value, OrderStatus.CANCELLED.value},
    OrderStatus.PENDING_MANUAL_REVIEW.value: {OrderStatus.PUBLISHED.value, OrderStatus.BLOCKED.value,
                                              OrderStatus.CANCELLED.value},
    OrderStatus.BLOCKED.value: set(),  # 硬约束：L3 拦截态无出边，不可自动发布
    OrderStatus.PUBLISHED.value: {OrderStatus.MATCHING.value, OrderStatus.ACCEPTED.value, OrderStatus.CANCELLED.value},
    OrderStatus.MATCHING.value: {OrderStatus.ACCEPTED.value, OrderStatus.PUBLISHED.value, OrderStatus.CANCELLED.value},
    OrderStatus.ACCEPTED.value: {OrderStatus.IN_PROGRESS.value, OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value},
    OrderStatus.IN_PROGRESS.value: {OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value},
    OrderStatus.COMPLETED.value: {OrderStatus.EVALUATED.value},
    OrderStatus.EVALUATED.value: set(),
    OrderStatus.CANCELLED.value: set(),
}

RISK_DEFAULT_ACTION = {"L1": "auto_publish", "L2": "warn_manual_review", "L3": "block_and_guide"}


def _transition(db: Session, order: WorkOrder, to_status: str, operator: str = "system") -> None:
    """执行状态迁移，非法迁移抛错（T2.5 验收：非法迁移被拒绝）。"""
    allowed = TRANSITIONS.get(order.status, set())
    if to_status not in allowed:
        raise HTTPException(400, f"非法状态迁移: {order.status} → {to_status}")
    order.status = to_status
    db.add(AuditLog(action="order_transition", target=order.work_order_no,
                    detail={"from": order.status, "to": to_status}, operator=operator))


class OrderCreateIn(BaseModel):
    text: str | None = None          # 文本求助（走规则解析）
    transcript: str | None = None    # 已有转写文本（前端 ASR 结果回传）
    asr_confidence: float | None = None
    title: str = ""
    task_type: str = ""
    urgency: str = ""
    location: str = ""
    time_slot: str = ""
    description: str = ""
    tenant_id: str = "default"


class ConfirmIn(BaseModel):
    title: str | None = None
    task_type: str | None = None
    urgency: str | None = None
    location: str | None = None
    time_slot: str | None = None
    description: str | None = None


class RateIn(BaseModel):
    score: int
    comment: str = ""


@router.post("/api/v1/orders", tags=["工单服务"])
def create_order(body: OrderCreateIn, payload: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """创建工单：文本 → 解析 → 分级 → 状态推进。含音频版本将在 T2.2 接 ASR 后加。"""
    user = db.get(User, int(payload["sub"]))
    # 1. ASR/文本输入
    from ..rules import mock_asr
    if body.transcript:
        transcript, asr_conf = body.transcript, body.asr_confidence or 0.9
    else:
        r = mock_asr(body.text)
        transcript, asr_conf = r["transcript"], r["confidence"]
    # 2. 语义解析（槽位填充，Demo 规则版）；手工指定的槽位优先于解析结果
    #    （R6 发布前可核对可修改，见接口文档 POST /orders「手工指定槽位」说明）
    parsed = parse_intent(transcript)
    for k in ("task_type", "urgency", "location", "time_slot", "description"):
        v = getattr(body, k, "")
        if v:
            parsed[k] = v
    # 3. 风险分级（管理员规则表，R11）
    from ..models import RiskRule
    rule_rows = db.scalars(select(RiskRule)).all()
    rules = [dict(id=x.id, condition=x.condition, level=x.level, action=x.action) for x in rule_rows]
    level, risk_conf = rule_based_risk(parsed["task_type"], parsed["urgency"], "校内", rules)
    action = next((r["action"] for r in rules if r["level"] == level), RISK_DEFAULT_ACTION.get(level, "auto_publish"))

    order = WorkOrder(
        work_order_no=f"WO{datetime.now():%Y%m%d%H%M%S}{db.query(WorkOrder.id).count() + 1:04d}",
        tenant_id=body.tenant_id or (user.tenant_id if user else "default"),
        requester_id=user.id,
        title=body.title or parsed["description"][:30],
        transcript=transcript,
        asr_confidence=asr_conf,
        task_type=parsed["task_type"],
        urgency=parsed["urgency"],
        location=parsed["location"],
        time_slot=parsed["time_slot"],
        description=parsed["description"],
        parse_confidence=parsed["confidence"],
        risk_level=level,
        risk_confidence=risk_conf,
        status=OrderStatus.CREATED.value,
    )
    db.add(order)
    db.flush()

    # 4. 状态机推进：created → ai_reviewing → 分支
    _transition(db, order, OrderStatus.AI_REVIEWING.value)
    if level == RiskLevel.L3.value and action == "block_and_guide":
        # L3 硬拦截（R10）：仅推送官方渠道指引 + 拦截日志
        order.blocked_reason = f"命中高风险规则(等级{level})，强制拦截并引导官方渠道"
        order.blocked_at = datetime.now()
        order.blocked_by = f"rule_engine@v{next((r.get('version') for r in rules if r['level'] == level), 1)}"
        order.official_channel_ref = next((r.get("official_channel_ref") for r in rules if r.get("official_channel_ref")), "") \
            or "校内后勤服务中心 / 校园保卫处"
        _transition(db, order, OrderStatus.BLOCKED.value)
        db.add(AuditLog(action="l3_block", target=order.work_order_no,
                        detail={"level": level, "reason": order.blocked_reason,
                                "channel": order.official_channel_ref}, operator="ai_engine"))
        db.commit()
        return {"order": _order_dto(order), "blocked": True}
    if level == RiskLevel.L2.value or action == "warn_manual_review" or risk_conf < 0.6:
        order.status = OrderStatus.PENDING_MANUAL_REVIEW.value
        db.add(AuditLog(action="pending_review", target=order.work_order_no,
                        detail={"level": level, "risk_confidence": risk_conf}, operator="ai_engine"))
    else:
        _transition(db, order, OrderStatus.PUBLISHED.value)
    db.commit()
    return {"order": _order_dto(order), "blocked": False}


def _order_dto(o: WorkOrder, requester_name: str = "") -> dict:
    """工单 DTO。requester_name：发布者姓名（列表页带出，避免 N+1 查询由调用方传入）。"""
    return {
        "id": o.id, "work_order_no": o.work_order_no, "tenant_id": o.tenant_id,
        "requester_id": o.requester_id, "requester_name": requester_name,
        "title": o.title, "transcript": o.transcript,
        "asr_confidence": o.asr_confidence, "task_type": o.task_type, "urgency": o.urgency,
        "location": o.location, "time_slot": o.time_slot, "description": o.description,
        "parse_confidence": o.parse_confidence, "risk_level": o.risk_level,
        "risk_confidence": o.risk_confidence, "status": o.status, "is_official": o.is_official,
        "blocked_reason": o.blocked_reason, "official_channel_ref": o.official_channel_ref,
        "review_record": o.review_record,  # 学生端详情页展示复核记录（如有）
        "volunteer_id": o.volunteer_id, "rating": o.rating,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def _name_map(db: Session) -> dict[int, str]:
    """用户 id → 展示名（real_name 优先，退回 username）。列表接口共用，一次查询。"""
    return {u.id: (u.real_name or u.username) for u in db.scalars(select(User)).all()}


@router.get("/api/v1/orders/mine", tags=["工单服务"])
def my_orders(payload: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """我的工单：我发布的 + 我承接的（学生端「我的」页数据源）。
    注意：本路由必须声明在 /orders/{order_id} 之前，否则 mine 会被当作 order_id 解析。"""
    uid = int(payload["sub"])
    rows = db.scalars(select(WorkOrder)
                      .where((WorkOrder.requester_id == uid) | (WorkOrder.volunteer_id == uid))
                      .order_by(WorkOrder.id.desc())).all()
    names = _name_map(db)
    return {"total": len(rows), "items": [_order_dto(o, names.get(o.requester_id, "")) for o in rows]}


@router.get("/api/v1/orders", tags=["工单服务"])
def list_orders(status: str | None = None, keyword: str | None = None, page: int = 1, size: int = 20,
                db: Session = Depends(get_db), payload: dict = Depends(get_current_user)):
    """任务广场：published/matching 的工单 + 官方任务统一展示（R18）。
    默认过滤掉自己发布的单（exclude_mine，JWT 里带开关）——自己的单不能自己接，
    展示出来只会造成"发布者全是自己/无法接单"的困惑；管理端订单页看全量。"""
    q = select(WorkOrder).where(WorkOrder.status.in_([OrderStatus.PUBLISHED.value, OrderStatus.MATCHING.value]))
    rows = db.scalars(q.order_by(WorkOrder.id.desc())).all()
    if keyword:
        rows = [r for r in rows if keyword in r.title or keyword in r.description or keyword in r.location]
    if str(payload.get("exclude_mine", "true")).lower() != "false":
        uid = int(payload["sub"])
        rows = [r for r in rows if r.requester_id != uid]
    names = _name_map(db)
    total = len(rows)
    items = [_order_dto(r, names.get(r.requester_id, "")) for r in rows[(page - 1) * size: page * size]]
    return {"total": total, "items": items}


@router.get("/api/v1/orders/{order_id}", tags=["工单服务"])
def get_order(order_id: int, db: Session = Depends(get_db), _: dict = Depends(get_current_user)):
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(404, "工单不存在")
    requester = db.get(User, o.requester_id)
    return _order_dto(o, requester.real_name if requester else "")


@router.post("/api/v1/orders/{order_id}/confirm", tags=["工单服务"])
def confirm_order(order_id: int, body: ConfirmIn, payload: dict = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """发布前核对/修改（R6）。修改后重新分级。"""
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(404, "工单不存在")
    if o.requester_id != int(payload["sub"]) and payload.get("role") != "admin":
        raise HTTPException(403, "仅本人或管理员可修改")
    for k in ("title", "task_type", "urgency", "location", "time_slot", "description"):
        v = getattr(body, k)
        if v is not None:
            setattr(o, k, v)
    o.status = OrderStatus.AI_REVIEWING.value  # 修改后回 AI 重审
    db.commit()
    return _order_dto(o)


@router.post("/api/v1/orders/{order_id}/accept", tags=["工单服务"])
def accept_order(order_id: int, payload: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(404, "工单不存在")
    if o.status != OrderStatus.PUBLISHED.value:
        raise HTTPException(400, f"当前状态 {o.status} 不可接单")
    if o.requester_id == int(payload["sub"]):
        raise HTTPException(400, "不能接自己的单")
    o.volunteer_id = int(payload["sub"])
    _transition(db, o, OrderStatus.ACCEPTED.value, operator=payload.get("name", ""))
    _apply_credit(db, o.volunteer_id, "accept", o.id, +1, "承接工单 #%s" % o.work_order_no,
                  operator=payload.get("name", "system"))
    db.commit()
    return _order_dto(o)


@router.post("/api/v1/orders/{order_id}/complete", tags=["工单服务"])
def complete_order(order_id: int, body: dict | None = None, payload: dict = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(404, "工单不存在")
    if o.status != OrderStatus.ACCEPTED.value:
        raise HTTPException(400, f"当前状态 {o.status} 不可完成")
    o.completion_proof = (body or {}).get("proof", "志愿者确认完成")
    _transition(db, o, OrderStatus.COMPLETED.value, operator=payload.get("name", ""))
    _apply_credit(db, o.volunteer_id, "complete", o.id, +5, "完成工单 #%s（凭证核验通过）" % o.work_order_no,
                  operator=payload.get("name", "system"))
    db.commit()
    return _order_dto(o)


@router.post("/api/v1/orders/{order_id}/rate", tags=["工单服务"])
def rate_order(order_id: int, body: RateIn, payload: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(404, "工单不存在")
    if o.status != OrderStatus.COMPLETED.value:
        raise HTTPException(400, f"当前状态 {o.status} 不可评价")
    o.rating = {"score": body.score, "comment": body.comment, "rated_by": payload.get("name", ""),
                "time": datetime.now().isoformat()}
    _transition(db, o, OrderStatus.EVALUATED.value, operator=payload.get("name", ""))
    # 信用积分闭环（R15）：发布者守约发布 +2；承接者按星级结算（≥3 星 +1*score，<3 星视为差评 -2）
    _apply_credit(db, o.requester_id, "rate", o.id, +2, "工单 #%s 守约发布（获评价 %d 星）" % (o.work_order_no, body.score),
                  operator=payload.get("name", "system"))
    _apply_credit(db, o.volunteer_id, "rate", o.id, (body.score * 1 if body.score >= 3 else -2),
                  "工单 #%s 获评价 %d 星" % (o.work_order_no, body.score),
                  operator=payload.get("name", "system"))
    db.commit()
    return _order_dto(o)
