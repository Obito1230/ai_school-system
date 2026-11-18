# -*- coding: utf-8 -*-
"""AI 算法服务：asr/parse/risk 三个接口（6.5 ai）。
Demo 为规则实现；真实 ASR/LLM 接口在 T2.2/T2.3/T2.4 接入，本层保持接口形状不变。
vision：多模态拍照报修（GLM-4V-Flash 识别故障照片 → 工单槽位，全部可人工核对）。"""
import base64

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import RiskRule
from ..rules import mock_asr, parse_intent, rule_based_risk

_VALID_TYPES = {"学业答疑", "生活互助", "后勤服务", "代办跑腿", "设备维修", "搬运协助",
                "教室清扫", "讲座会务", "其他"}
from ..security import get_current_user
from .glm_client import glm_vision_json

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


# ---------------- 多模态：拍照报修（GLM-4V-Flash） ----------------
class VisionIn(BaseModel):
    image_b64: str                      # 照片 base64（不带 data: 前缀）
    note: str = ""                      # 用户可选拍照附言


_VISION_SYSTEM = (
    "你是校园后勤报修助手。看图识别故障/求助场景，输出 JSON，不要解释。"
    '格式：{"scene":"一句话场景","description":"包含故障对象与现象的工单描述",'
    '"task_type":"...","urgency":"..."}\n'
    "task_type 只能取：学业答疑/生活互助/后勤服务/代办跑腿/设备维修/搬运协助/教室清扫/讲座会务/其他；"
    "urgency 只能取：低/普通/特急（涉及漏水断电等安全隐患判特急）。"
)

_VISION_PROMPT = "识别这张照片里的故障或求助需求并输出 JSON。{note}"


@router.post("/api/v1/ai/vision", tags=["AI算法服务"])
def vision(body: VisionIn, _: dict = Depends(get_current_user)):
    """拍照报修：照片 → 视觉模型识别 → 结构化槽位（前端回显全部可改，R6）。
    校验 base64 合法性；模型失败/未配 Key 返回 mode=degraded 前端走文字发布。"""
    # 快速校验：非法 base64 直接 400（防止脏数据打到模型）
    try:
        raw = base64.b64decode(body.image_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="image_b64 不是合法的 base64")
    if len(raw) < 100:
        raise HTTPException(status_code=400, detail="图片内容过小")
    prompt = _VISION_PROMPT.format(note=f"\n用户附言：{body.note}" if body.note else "")
    parsed = glm_vision_json(body.image_b64, prompt, _VISION_SYSTEM)
    if parsed and parsed.get("task_type") not in _VALID_TYPES:
        parsed = None  # 防幻觉：越界类型按失败降级
    if parsed:
        return {"mode": "glm-4v", "scene": parsed.get("scene", ""),
                "description": parsed.get("description", ""),
                "task_type": parsed.get("task_type", ""),
                "urgency": parsed.get("urgency", "普通")}
    # 降级：无 Key/模型失败 → 若有附言走规则解析，否则提示改用文字发布
    if body.note:
        r = parse_intent(body.note)
        return {"mode": "degraded", "scene": "", "description": r.get("description", body.note),
                "task_type": r.get("task_type", ""), "urgency": r.get("urgency", "普通")}
    return {"mode": "degraded", "scene": "", "description": "", "task_type": "", "urgency": ""}
