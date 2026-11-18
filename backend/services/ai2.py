# -*- coding: utf-8 -*-
"""AI 增强服务（传智杯 AI 深度专项）：
1. POST /ai/ask    —— RAG 检索增强问答（校园知识库 recall → GLM 生成 → 无 Key 纯检索兜底）
2. POST /ai/tools/call —— Function Calling：LLM 意图理解后调用平台工具（查工单/查信用/知识库检索）
3. GET  /ai/tools/list —— 暴露工具注册表（MCP 风格的 tool schema，供评审/前端展示）
4. 输出安全：prompt 注入清洗 + 敏感内容过滤 + 兜底话术（AI 安全与可控性）
"""
import json
import re
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, WorkOrder
from ..rules import _glm_chat_json, _glm_ok, parse_intent  # 复用 GLM 封装与解析
from ..security import get_current_user
from . import kb

router = APIRouter()

# ============================================================
# AI 安全：输入清洗与输出过滤（AI 安全与可控性 4%）
# ============================================================
_INJECT_PAT = re.compile(
    r"(ignore|disregard|无视|忽略|忘记).{0,8}(previous|above|instruction|prompt|规则|指令|提示|设定|身份)"
    r"|(你现在是|假装你是|acting as|jailbreak|越狱|破解|绕过)", re.I)
_SENSITIVE_PAT = re.compile(
    r"(现金交易|转账|刷单|代考|替考|作弊|办证|贷款|套现|色情|博彩|赌博|代写论文|黑客|攻击)")


def sanitize_input(text: str) -> tuple[str, bool]:
    """输入清洗：检测提示词注入。返回 (清洗后文本, 是否疑似注入)。"""
    injected = bool(_INJECT_PAT.search(text or ""))
    cleaned = _INJECT_PAT.sub("〔内容已过滤〕", text or "")
    return cleaned.strip(), injected


def check_output(text: str) -> tuple[str, bool]:
    """输出过滤：命中敏感主题则替换为兜底话术（内容安全兜底）。"""
    if _SENSITIVE_PAT.search(text or ""):
        return ("抱歉，该话题涉及平台禁止内容。校园互助禁止现金交易、代考作弊等行为，"
                "如有相关需求请使用官方渠道。"), True
    return (text or "").strip(), False

# ============================================================
# 1. RAG 问答
# ============================================================

_ASK_SYSTEM = (
    "你是校园互助平台的智能助手「小互助」。仅根据下方提供的【参考资料】回答用户问题："
    "答案在资料中就简洁作答并注明来源条目；资料没有就如实说「我暂时没有查到相关校园信息」，"
    "并建议用户咨询相关部门，不要编造。回答不超过 150 字，用适合学生的友好语气。"
)


class AskIn(BaseModel):
    question: str


@router.post("/api/v1/ai/ask", tags=["AI算法服务"])
def ask(body: AskIn, _: dict = Depends(get_current_user)):
    """RAG 问答：检索增强生成（RAG 技术应用）。
    链路：输入清洗 → KB Top-3 召回 → GLM 增强生成 → 输出安全过滤 → 无 Key 降级为纯检索摘要。"""
    question, injected = sanitize_input(body.question)
    if not question:
        return {"answer": "请输入你的问题～", "sources": [], "injected": injected, "mode": "guard"}
    hits = kb.recall(question, k=3)
    ctx = "\n".join(f"[{h['id']}] {h['title']}：{h['content']}" for h in hits) or "（无）"
    mode, answer, blocked = "rag_llm", None, False
    if _glm_ok():
        raw = _glm_chat_json(
            json.dumps({"question": question, "references": [
                {"id": h["id"], "title": h["title"], "content": h["content"]} for h in hits]}, ensure_ascii=False),
            _ASK_SYSTEM + "\n输出 JSON：{\"answer\":\"...\"}")
        if raw and raw.get("answer"):
            answer, blocked = check_output(str(raw["answer"]))
    if answer is None:  # 无 Key / LLM 失败 → 纯检索兜底（R16 降级，服务永不 500）
        if hits:
            top = hits[0]
            answer = f"为你查到「{top['title']}」：{top['content']}"
        else:
            answer = "我暂时没有查到相关校园信息，建议到信息门户查询或咨询辅导员。"
        mode = "rag_fallback"
    return {"answer": answer, "mode": mode,
            "sources": [{"id": h["id"], "title": h["title"], "score": h["score"]} for h in hits],
            "injected": injected, "sensitive_blocked": blocked}


# ============================================================
# 1b. RAG 问答 · 流式版（SSE）：AI 交互体验（思考状态可视化 + 逐字输出）
# ============================================================

def _sse(event: str, data: dict) -> str:
    """SSE 帧：event: <name>\\ndata: <json>\\n\\n"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/v1/ai/ask/stream", tags=["AI算法服务"])
def ask_stream(body: AskIn, _: dict = Depends(get_current_user)):
    """RAG 流式问答（text/event-stream）。
    事件序列：sources（检索到的资料）→ delta（逐段答案）→ done（收尾元数据）。
    Demo 无真实流式 LLM 端点，故生成后按标点切片模拟逐段推送——前端消费方式与真流式完全一致，
    换 streaming LLM 时只需替换 delta 生成源，接口协议不变。"""
    question, injected = sanitize_input(body.question)
    hits = kb.recall(question, k=3) if question else []

    def gen():
        yield _sse("sources", {"items": [{"id": h["id"], "title": h["title"]} for h in hits]})
        if not question:
            yield _sse("delta", {"text": "请输入你的问题～"})
        elif injected:
            yield _sse("delta", {"text": "检测到疑似提示词注入，该请求已被安全策略拦截。"})
        else:
            # 复用 ask 的生成/兜底逻辑拿完整答案，再切片推送
            full = _rag_answer(question, hits)
            answer, blocked = check_output(full) if _glm_ok() else (full, False)
            for piece in re.split(r"(?<=[。！？；\n])", answer):  # 按句切
                if piece:
                    yield _sse("delta", {"text": piece})
                    time.sleep(0.12)  # 模拟 token 间隔（真实接入时删除）
        yield _sse("done", {"mode": "stream", "count": len(hits)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _rag_answer(question: str, hits: list[dict]) -> str:
    """非流式 RAG 答案生成（流式/非流式共用）：GLM 优先，失败纯检索兜底。"""
    if _glm_ok():
        ctx = json.dumps({"question": question, "references": [
            {"id": h["id"], "title": h["title"], "content": h["content"]} for h in hits]}, ensure_ascii=False)
        raw = _glm_chat_json(ctx, _ASK_SYSTEM + "\n输出 JSON：{\"answer\":\"...\"}")
        if raw and raw.get("answer"):
            return str(raw["answer"])
    if hits:
        return f"为你查到「{hits[0]['title']}」：{hits[0]['content']}"
    return "我暂时没有查到相关校园信息，建议到信息门户查询或咨询辅导员。"

# ============================================================
# 2. Function Calling 工具注册表与执行器
# ============================================================

# MCP/Function-Calling 风格 schema：LLM 按此理解可调用哪些工具、参数是什么
TOOLS = [
    {"name": "search_orders",
     "description": "按关键词与状态查询平台互助工单列表",
     "parameters": {"type": "object", "properties": {
         "keyword": {"type": "string", "description": "标题/描述关键词，如 高数、跑腿"},
         "status": {"type": "string", "enum": ["published", "accepted", "completed", "blocked"],
                    "description": "工单状态，默认 published"}},
         "required": []}},
    {"name": "get_credit",
     "description": "查询指定用户名的当前信用积分",
     "parameters": {"type": "object", "properties": {
         "username": {"type": "string", "description": "用户名，如 stu01"}}, "required": ["username"]}},
    {"name": "search_kb",
     "description": "检索校园知识库（办事指南/求助渠道/平台规则）",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "问题关键词"}}, "required": ["query"]}},
]


def _exec_tool(db: Session, name: str, args: dict) -> dict:
    """工具执行器：白名单分发（未注册工具一律拒绝，可控性）。"""
    if name == "search_orders":
        q = db.query(WorkOrder)
        st = args.get("status") or "published"
        if hasattr(WorkOrder.status, "value"):
            q = q.filter(WorkOrder.status == st)
        if args.get("keyword"):
            kw = f"%{args['keyword']}%"
            q = q.filter((WorkOrder.description.like(kw)) | (WorkOrder.title.like(kw)) if WorkOrder.title is not None
                         else WorkOrder.description.like(kw))
        rows = q.order_by(WorkOrder.id.desc()).limit(5).all()
        return {"tool": name, "result": [{"id": o.id, "desc": (o.description or "")[:40],
                                          "status": o.status, "risk": o.risk_level} for o in rows]}
    if name == "get_credit":
        u = db.scalar(__import__("sqlalchemy").select(User).where(User.username == args.get("username", "")))
        return {"tool": name, "result": {"username": args.get("username"),
                                         "credit_score": u.credit_score if u else None}}
    if name == "search_kb":
        hits = kb.recall(args.get("query", ""), k=2)
        return {"tool": name, "result": [{"title": h["title"], "content": h["content"]} for h in hits]}
    return {"tool": name, "result": None, "error": "未注册的工具"}


class ToolCallIn(BaseModel):
    question: str


_TOOL_SYSTEM = (
    "你是校园互助平台的工具调用助手。根据用户问题决定是否调用工具：需要查工单/查信用/查校园知识库时，"
    "从可用工具中选择一个并给出参数；都不需要则 tool 为 null。"
    '只输出 JSON：{"tool":"工具名或null","arguments":{...}}。可用工具：'
    + json.dumps([{t["name"]: t["description"]} for t in TOOLS], ensure_ascii=False)
)


@router.get("/api/v1/ai/tools/list", tags=["AI算法服务"])
def tools_list(_: dict = Depends(get_current_user)):
    """工具注册表（Function Calling / MCP 风格 schema）。"""
    return {"tools": TOOLS}


@router.post("/api/v1/ai/tools/call", tags=["AI算法服务"])
def tools_call(body: ToolCallIn, payload: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Function Calling 全链路：LLM 决策（选工具+参数）→ 白名单执行 → 结果回传。
    无 Key 时按规则直接路由到 search_kb（降级仍可用）。"""
    question, injected = sanitize_input(body.question)
    if not question:
        return {"tool": None, "result": None, "note": "问题为空"}
    decision = None
    if _glm_ok() and not injected:
        decision = _glm_chat_json(question, _TOOL_SYSTEM)
    if not (decision and decision.get("tool")):
        # 降级路由：明显是办事咨询→知识库；带积分字样→查信用；否则检索工单
        if re.search(r"信用|积分|多少分", question):
            m = re.search(r"[a-zA-Z0-9_]+", question)
            decision = {"tool": "get_credit", "arguments": {"username": m.group(0) if m else "stu01"}}
        elif re.search(r"怎么办|在哪|如何|怎么|流程|渠道|时间|规则", question):
            decision = {"tool": "search_kb", "arguments": {"query": question}}
        else:
            decision = {"tool": "search_orders", "arguments": {"keyword": question[:12]}}
        mode = "rule_route"
    else:
        mode = "llm_route"
    tool = decision["tool"]
    if tool and tool not in {t["name"] for t in TOOLS}:  # 幻觉工具名 → 拒绝执行
        return {"tool": tool, "result": None, "mode": mode, "error": "工具不在注册表中，已拒绝执行"}
    out = _exec_tool(db, tool, decision.get("arguments") or {})
    out.update({"mode": mode, "injected": injected})
    return out
