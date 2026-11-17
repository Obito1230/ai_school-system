# -*- coding: utf-8 -*-
"""AI 算法服务：asr/parse/risk 三个接口（6.5 ai）。
Demo 为规则实现；真实 ASR/LLM 接口在 T2.2/T2.3/T2.4 接入，本层保持接口形状不变。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RiskRule
from ..rules import mock_asr, parse_intent, rule_based_risk
from ..security import get_current_user

router = APIRouter()


class AsrIn(BaseModel):
    text: str | None = None  # Demo：直接传文本模拟；真实版为音频文件
    audio_b64: str | None = None  # 预留：T2.2 音频 base64


@router.post("/api/v1/ai/asr", tags=["AI算法服务"])
def asr(body: AsrIn, _: dict = Depends(get_current_user)):
    r = mock_asr(body.text)
    if r["manual_fallback"]:
        r["manual_fallback"] = True
        r["note"] = "置信度低于阈值，建议二次校验或人工兜底（R5）"
    return r


class ParseIn(BaseModel):
    text: str


@router.post("/api/v1/ai/parse", tags=["AI算法服务"])
def parse(body: ParseIn, _: dict = Depends(get_current_user)):
    """意图分类 + 槽位填充（R6/R7）。"""
    return parse_intent(body.text)


class RiskIn(BaseModel):
    task_type: str = ""
    urgency: str = ""
    scope: str = "校内"


@router.post("/api/v1/ai/risk", tags=["AI算法服务"])
def risk(body: RiskIn, db: Session = Depends(get_db), _: dict = Depends(get_current_user)):
    """风险分级（R8–R11）：等级 + 置信度，规则表驱动。"""
    rules = [dict(id=x.id, condition=x.condition, level=x.level, action=x.action)
             for x in db.scalars(select(RiskRule)).all()]
    level, conf = rule_based_risk(body.task_type, body.urgency, body.scope, rules)
    return {"level": level, "confidence": conf}
