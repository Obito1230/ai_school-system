# -*- coding: utf-8 -*-
"""应用入口：FastAPI 应用组装 + 初始化数据 + 静态管理页托管。
启动：python -m uvicorn backend.main:app --port 8000（在项目根目录执行）"""
from pathlib import Path

# ---- .env 加载（最早执行）：项目根 .env 的 KEY=VALUE 注入环境变量 ----
# 密钥只放本地 .env（.gitignore 已排除），优先级低于已设置的系统环境变量
def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k and k not in os.environ:      # 已有系统环境变量时不覆盖
            os.environ[k] = v

import os
_load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import BASE_DIR, ADMIN_DEFAULT_PASSWORD, ADMIN_DEFAULT_USER
from .database import Base, SessionLocal, engine
from .models import CreditRule, RiskRule, User
from .security import hash_password
from .services import ai, ai2, admin, credits, orders, users

app = FastAPI(
    title="AI赋能的校园互助服务平台 · 管理端框架（Demo）",
    version="0.1.0",
    description="M2 前最小可运行框架：用户/工单/AI算法/积分/运营管理 五服务 REST API + 管理端静态页",
)

# CORS：本地联调放开（生产收敛）
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (users.router, orders.router, ai.router, ai2.router, credits.router, admin.router):
    app.include_router(r)


@app.get("/api/health", tags=["系统"])
def health():
    return {"status": "ok", "service": "ai-campus-mutual-aid", "version": app.version}


# ---------------- 初始化：建表 + 种子数据 ----------------
SEED_RISK_RULES = [
    # condition 为 Python 表达式，变量可用 task_type / urgency / scope（管理员在后台配置）
    {"dimension": "task_type", "condition": "task_type=='代办跑腿'", "level": "L2",
     "action": "warn_manual_review", "official_channel_ref": ""},
    {"dimension": "task_type", "condition": "'维修' in task_type or '搬运' in task_type", "level": "L3",
     "action": "block_and_guide", "official_channel_ref": "校内后勤服务中心 / 校园保卫处"},
    {"dimension": "urgency", "condition": "urgency=='特急'", "level": "L2",
     "action": "warn_manual_review", "official_channel_ref": ""},
]

SEED_CREDIT_RULES = [
    {"rule_code": "publish_reward", "event": "publish", "condition": "守约", "delta": +2},
    {"rule_code": "accept_reward", "event": "accept", "condition": "守约", "delta": +1},
    {"rule_code": "complete_reward", "event": "complete", "condition": "凭证核验通过", "delta": +5},
    {"rule_code": "rate_reward", "event": "rate", "condition": "守约", "delta": +1},
    {"rule_code": "breach_penalty", "event": "complete", "condition": "失信", "delta": -10},
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if not db.scalar(select(User).where(User.username == ADMIN_DEFAULT_USER)):
            db.add(User(username=ADMIN_DEFAULT_USER,
                        password_hash=hash_password(ADMIN_DEFAULT_PASSWORD),
                        real_name="系统管理员", role="admin", tenant_id="default"))
            db.add(User(username="stu01", password_hash=hash_password("123456"),
                        real_name="张同学", role="student", tenant_id="信息学院"))
            db.add(User(username="stu02", password_hash=hash_password("123456"),
                        real_name="李同学", role="student", tenant_id="信息学院"))
            db.commit()
        if db.scalar(select(RiskRule).limit(1)) is None:
            for r in SEED_RISK_RULES:
                db.add(RiskRule(updated_by="seed", adjust_reason="初始种子规则", **r))
            db.commit()
        if db.scalar(select(CreditRule).limit(1)) is None:
            for r in SEED_CREDIT_RULES:
                db.add(CreditRule(updated_by="seed", **r))
            db.commit()
    finally:
        db.close()


init_db()

# ---------------- 静态页（纯 HTML/JS，无构建步骤） ----------------
# 管理端（/admin）与学生端（/app，单文件 index.html，hash 路由）
web_admin = Path(BASE_DIR) / "web" / "admin"
web_admin.mkdir(parents=True, exist_ok=True)
app.mount("/admin", StaticFiles(directory=str(web_admin), html=True), name="admin")

web_student = Path(BASE_DIR) / "web" / "student"
web_student.mkdir(parents=True, exist_ok=True)
app.mount("/app", StaticFiles(directory=str(web_student), html=True), name="student")

# 适老化端（退休教职工，/elder，大图标高对比度语音优先，单文件 index.html）
web_elder = Path(BASE_DIR) / "web" / "elder"
web_elder.mkdir(parents=True, exist_ok=True)
app.mount("/elder", StaticFiles(directory=str(web_elder), html=True), name="elder")
