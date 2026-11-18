# -*- coding: utf-8 -*-
"""全局配置：所有产物都在 D 盘项目目录内，不占 C 盘。
C 盘占用说明见项目根 README.md 的「磁盘占用说明」。"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根 ai_school-system

# SQLite 数据库文件位置（项目目录内）
DB_PATH = Path(os.environ.get("AIC_DB_PATH", BASE_DIR / "data" / "app.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 上传文件目录（项目目录内）
UPLOAD_DIR = Path(os.environ.get("AIC_UPLOAD_DIR", BASE_DIR / "data" / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# JWT 密钥（Demo 用，生产需换成环境变量/配置中心）
SECRET_KEY = os.environ.get("AIC_SECRET_KEY", "demo-secret-key-change-me")
JWT_ALGO = "HS256"
TOKEN_EXPIRE_HOURS = 12

# 管理端默认账号（首次启动自动创建）
ADMIN_DEFAULT_USER = "admin"
ADMIN_DEFAULT_PASSWORD = "admin123"

# ============ 智谱 GLM 接入配置（T2.3/T2.4：LLM 解析与风险语义增强） ============
# 安全约定：Key 只从环境变量读取，不硬编码进代码/git。
# 未配置 Key 或调用失败时，自动降级到 rules.py 的本地规则实现（R16 熔断降级）。
GLM_API_KEY = os.environ.get("AIC_GLM_API_KEY", "")            # 智谱 API Key（必填才有真实 LLM）
GLM_BASE_URL = os.environ.get("AIC_GLM_BASE_URL",
                              "https://open.bigmodel.cn/api/paas/v4/")  # 智谱 OpenAI 兼容端点
GLM_MODEL = os.environ.get("AIC_GLM_MODEL", "glm-4-flash")     # Demo 默认免费模型，可换 glm-4-plus 等
GLM_TIMEOUT = float(os.environ.get("AIC_GLM_TIMEOUT", "10"))   # 单次调用超时（秒），超时走降级
# 视觉模型（多模态拍照报修）：识别故障照片生成工单描述，免费档 glm-4v-flash
GLM_VL_MODEL = os.environ.get("AIC_GLM_VL_MODEL", "glm-4v-flash")

# ASR 真实语音识别（T2.2）：智谱 GLM 目前主推文本/视觉模型，语音识别
# 需要单独的 ASR 服务（讯飞/阿里/腾讯）。未配置时 /ai/asr 保持 Demo 模拟。
ASR_API_KEY = os.environ.get("AIC_ASR_API_KEY", "")
ASR_BASE_URL = os.environ.get("AIC_ASR_BASE_URL", "")
ASR_APP_ID = os.environ.get("AIC_ASR_APP_ID", "")

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台中文输出
