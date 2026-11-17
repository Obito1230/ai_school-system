# -*- coding: utf-8 -*-
"""确定性规则引擎（R14：打分/结算不调用生成式模型）。
含：AI 模拟器（T2.2/T2.3 真实接口接入层——parse_intent 已接 GLM，失败自动降级到本文件规则）
与 Top-1 匹配。"""
import random
import re


def rule_based_risk(task_type: str, urgency: str, scope: str, rules: list[dict]) -> tuple[str, float]:
    """按管理员配置的规则表（R11）确定风险等级。规则即代码外置。
    返回 (level, confidence)。"""
    expr_env = {"task_type": task_type, "urgency": urgency, "scope": scope}
    for r in sorted(rules, key=lambda x: x.get("priority", 0), reverse=True):
        cond = r.get("condition", "")
        try:
            if eval(cond, {"__builtins__": {}}, expr_env):  # noqa: S307 — 条件由管理员配置，沙箱内置无
                return r["level"], 0.92
        except Exception:
            continue
    # 兜底默认分级
    if urgency in ("紧急", "特急"):
        return "L2", 0.80
    return "L1", 0.90


# 允许的槽位取值（LLM 输出校验用，防幻觉越界）
_VALID_TYPES = {"学业答疑", "生活互助", "后勤服务", "代办跑腿", "设备维修", "搬运协助",
                "教室清扫", "讲座会务", "其他"}
_VALID_URG = {"低", "普通", "特急"}

_PARSE_SYSTEM = (
    "你是校园互助平台的工单解析器。从求助文本中抽取结构化槽位，只输出 JSON，不要解释。"
    '格式：{"task_type":"...","urgency":"...","location":"...","time_slot":"...","description":"..."}\n'
    "task_type 只能取：学业答疑/生活互助/后勤服务/代办跑腿/设备维修/搬运协助/教室清扫/讲座会务/其他；"
    "urgency 只能取：低/普通/特急；location/time_slot 抽不到就留空字符串；"
    "description 用原文本或轻微润色，保持原意。"
)


def parse_intent(text: str) -> dict:
    """语义解析槽位填充（R6/R7）。
    优先走 GLM（T2.3 已接入）；Key 未配置 / 超时 / 返回不合法时，
    降级到 _rule_parse_intent 本地关键词规则（R16 熔断降级，Demo 行为不变）。"""
    parsed = None
    if _glm_ok():
        raw = _glm_chat_json(
            "求助文本：" + text,
            _PARSE_SYSTEM,
        )
        if raw and raw.get("task_type") in _VALID_TYPES and raw.get("urgency") in _VALID_URG:
            parsed = {
                "task_type": raw["task_type"],
                "urgency": raw["urgency"],
                "location": str(raw.get("location") or ""),
                "time_slot": str(raw.get("time_slot") or ""),
                "description": str(raw.get("description") or text),
            }
    if parsed is None:                       # ---- 降级路径：本地规则 ----
        parsed = _rule_parse_intent(text)
    parsed["confidence"] = round(min(parsed.get("confidence", 0.9), 0.95), 2)
    return parsed


def _rule_parse_intent(text: str) -> dict:
    """Demo 版语义解析：关键词规则抽取槽位（作为 GLM 的降级回退）。"""
    task_types = {
        "答疑": "学业答疑", "辅导": "学业答疑", "讲题": "学业答疑",
        "取": "代办跑腿", "带": "代办跑腿", "送": "代办跑腿", "买": "代办跑腿",
        "修": "设备维修", "装": "设备维修",
        "搬": "搬运协助", "抬": "搬运协助",
        "打扫": "教室清扫", "清扫": "教室清扫", "保洁": "教室清扫",
        "会务": "讲座会务", "讲座": "讲座会务", "签到": "讲座会务",
    }
    task_type, hit = "其他", False
    for kw, tt in task_types.items():
        if kw in text:
            task_type = tt
            hit = True
            break
    urgency = "特急" if any(w in text for w in ("马上", "立刻", "尽快", "现在", "急")) else "普通"
    m = re.search(r"(今天|明天|后天|周[一二三四五六日]|[上下]午|\d{1,2}[点时:：]\d{0,2}分?)", text)
    time_slot = m.group(1) if m else ""
    m2 = re.search(r"(教\d{3}|教学楼[\d一二三四五六七八九十]*|实验楼[\d一二三四五六七八九十]*|图书馆|宿舍\d*|食堂[\d一二三四五六七八九十]*|\S{2,8}楼\s?\S{0,4}教室)", text)
    location = m2.group(1) if m2 else ""
    conf = 0.75 + 0.1 * hit + 0.05 * bool(location)
    return {
        "task_type": task_type,
        "urgency": urgency,
        "location": location,
        "time_slot": time_slot,
        "description": text,
        "confidence": round(min(conf, 0.95), 2),
    }


def mock_asr(text_or_none: str | None = None) -> dict:
    """Demo 版 ASR：无真实语音接口，直接返回传入文本或模拟文本。
    T2.2 将替换为商用 ASR 封装 + 专有名词校正 + 真实置信度。"""
    text = text_or_none or "你好，我明天上午十点想请人帮我在图书馆三楼取一份资料送到宿舍6号楼"
    confidence = round(random.uniform(0.75, 0.98), 2)
    return {"transcript": text, "confidence": confidence, "manual_fallback": confidence < 0.80}


# ---------- GLM 延迟导入（避免循环依赖；未装 httpx 也不影响纯 Demo 运行） ----------
def _glm_ok() -> bool:
    try:
        from .services.glm_client import glm_available
        return glm_available()
    except Exception:
        return False


def _glm_chat_json(prompt: str, system: str) -> dict | None:
    try:
        from .services.glm_client import glm_chat_json
        return glm_chat_json(prompt, system)
    except Exception:
        return None


def match_score(order: dict, volunteer: dict) -> dict:
    """多要素加权打分（R13/R14 确定性引擎，Top-1 简化版）。
    权重为 AHP 初始权重的 Demo 值，T3.2 完善为可配置。"""
    w = {"skill": 0.35, "credit": 0.30, "rate": 0.20, "avail": 0.15}
    skill = volunteer.get("skill_score", 0.6)
    credit = volunteer.get("credit_score", 100) / 120.0
    rate = volunteer.get("completion_rate", 0.9)
    avail = volunteer.get("availability", 0.8)
    total = w["skill"] * skill + w["credit"] * credit + w["rate"] * rate + w["avail"] * avail
    return {
        "total": round(total, 4),
        "explain": {
            "技能匹配": {"weight": w["skill"], "value": skill, "contribution": round(w["skill"] * skill, 4)},
            "信用分": {"weight": w["credit"], "value": credit, "contribution": round(w["credit"] * credit, 4)},
            "完成率": {"weight": w["rate"], "value": rate, "contribution": round(w["rate"] * rate, 4)},
            "空闲度": {"weight": w["avail"], "value": avail, "contribution": round(w["avail"] * avail, 4)},
        },
    }
