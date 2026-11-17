# -*- coding: utf-8 -*-
"""积分服务：查询信用分/流水 + 申诉登记（6.5 credit）。结算引擎本身在 credit_rules 挂钩，
Demo 阶段完成事件先由工单服务写入固定流水，P3 的 T3.3 完整实现。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, CreditLedger, User
from ..security import get_current_user

router = APIRouter()


@router.get("/api/v1/credits/{user_id}", tags=["积分服务"])
def get_credit(user_id: int, db: Session = Depends(get_db), _: dict = Depends(get_current_user)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    return {"user_id": u.id, "credit_score": u.credit_score}


@router.get("/api/v1/credits/{user_id}/ledger", tags=["积分服务"])
def get_ledger(user_id: int, page: int = 1, size: int = 20,
               db: Session = Depends(get_db), _: dict = Depends(get_current_user)):
    q = select(CreditLedger).where(CreditLedger.user_id == user_id)
    rows = db.scalars(q.order_by(CreditLedger.id.desc())).all()
    return {"total": len(rows), "items": [
        {"id": r.id, "order_id": r.order_id, "event": r.event, "rule_id": r.rule_id,
         "rule_version": r.rule_version, "delta": r.delta, "remark": r.remark,
         "operator": r.operator, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows[(page - 1) * size: page * size]]}


class AppealIn(BaseModel):
    ledger_id: int
    reason: str


@router.post("/api/v1/credits/appeal", tags=["积分服务"])
def appeal(body: AppealIn, payload: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """积分申诉登记（R15 可申诉）：Demo 阶段仅写审计日志留痕。"""
    ledger = db.get(CreditLedger, body.ledger_id)
    if not ledger:
        raise HTTPException(404, "流水不存在")
    db.add(AuditLog(action="credit_appeal", target=f"ledger:{ledger.id}",
                    detail={"reason": body.reason}, operator=payload.get("name", "")))
    db.commit()
    return {"message": "申诉已登记，待管理员处理", "ledger_id": ledger.id}
