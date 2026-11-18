# AI赋能的校园互助服务平台（v0.5.1）

按《开发项目计划.md》T2.1（工程脚手架）+ T3.4（管理员后台核心框架）+ T2.6（学生端）+ T3.6（适老化端）的最小可运行版本。
后端 **FastAPI + SQLite**（五服务单进程模块化，P3 可拆微服务），前端**纯静态页面零构建**（管理端 + 学生端 + 适老化端均为单文件 SPA）。

**v0.5.1 变更**：多模态 + 适老端信用页——
- **多模态拍照报修**：学生端发布页第三 Tab「📷 拍照报修」，前端 canvas 压缩（最长边 800px）→ `POST /api/v1/ai/vision`（GLM-4V-Flash 视觉识别 → JSON 槽位，`_VALID_TYPES` 枚举防幻觉；无 Key 降级规则解析）→ 结构化表单可改 → 二次风控发布
- **适老端「我的信用」页**：首页第三入口，信用分 96px 大字按分值着色 + 流水大卡片（事件/时间/±分），老人只读不做申诉
- 技术文档 PDF 导出（10 页，满足 ≤30 页要求）

**v0.5.0 变更**：AI 能力深化（传智杯赛道对齐）——
- **RAG 校园知识库问答**：`backend/services/kb.py` 内置 8 篇校园语料（校园卡/图书馆/报修/保卫处/学业帮扶/勤工助学/心理/平台规则），TF 余弦召回（2-gram 分词，零外部依赖，可平迁向量库）；`POST /api/v1/ai/ask` 检索增强生成，返回 `sources` 可溯源
- **SSE 流式输出**：`POST /api/v1/ai/ask/stream`（sources→delta→done 事件流）；学生端 AI 助手页 fetch+ReadableStream 消费，逐句渲染 + AI 思考状态可视化
- **Function Calling 工具调用**：`GET /api/v1/ai/tools/list`（MCP 风格工具 schema 注册表）+ `POST /api/v1/ai/tools/call`（LLM 路由 → 白名单执行，防幻觉工具名；无 Key 时规则路由兜底）
- **AI 安全加固**：提示词注入清洗（_INJECT_PAT）+ 敏感内容输出过滤（_SENSITIVE_PAT），拦截可解释（`injected`/`sensitive_blocked` 字段）
- 学生端新增「AI 助手」页：流式渲染、错误边界（流式失败自动回退非流式）、来源徽标展示

**v0.4.3 变更**：接入智谱 GLM（T2.3）——
- `/api/v1/ai/parse` 语义解析接入 GLM（OpenAI 兼容端点，`httpx` 直连不引 SDK）：LLM 输出 JSON 槽位并校验枚举合法性
- **R16 熔断降级**：Key 未配置 / 超时（默认 10s）/ 返回不合法时自动回退本地规则解析，Demo 行为不变
- 配置走环境变量（Key 不进代码）：`AIC_GLM_API_KEY` / `AIC_GLM_MODEL`（默认 glm-4-flash）/ `AIC_GLM_TIMEOUT`
- ASR（T2.2）保持 Demo 模拟，`AIC_ASR_*` 配置位已预留；`/ai/risk` 保持规则表驱动（R14 确定性拦截）
- 新增 `backend/services/glm_client.py`（GLM 封装：glm_chat / glm_chat_json，失败一律返回 None 由调用方降级）

**v0.4.2 变更**：信用积分闭环（R15 最小实现）——
- 后端接单 +1 / 完成 +5 / 评价时发布者 +2、承接者按星级（≥3 星 +1×score，<3 星 -2）自动落账，流水留痕 rule_id/rule_version
- 学生端「我的」页新增「我的信用记录」：展开查看积分流水（事件/加减分/备注/时间），单笔可发起申诉（POST /credits/appeal）

**v0.4 变更**：新增退休教职工适老化端——
- 新增 `web/elder/index.html`：单文件 SPA（零第三方依赖、Hash 路由），挂载于 **/elder/**
- 对照工信部《APP适老化通用设计规范》(2021)：大图标（80px+）、大字号（基准 20px/正文 28px+）、大点击区（按钮 ≥96px 高）、高对比度（米白底近黑字 >7:1）、大行距 1.7
- 流程极简：首页仅两个大入口（我要求助 / 我的工单）；求助页**语音优先**（按住说话 → ASR → 解析回显 → 逐项可点改 → 确认发布），文字输入兜底
- L3 拦截弹窗大字展示官方渠道指引；复用学生端同一套 /api/v1 接口与 Bearer 鉴权，后端零改动（仅 main.py 挂载 /elder 静态目录）

**v0.3 变更**：新增学生端单页应用——
- 新增 `web/student/index.html`：单文件 SPA（零第三方依赖、Hash 路由、移动端优先 480px 居中），挂载于 **/app/**
- 5 个页面：登录 / 任务广场（类型 Tab 筛选）/ 发布求助（文字解析 + 语音录音）/ 工单详情（接单→完成→评价）/ 我的（信用分 + 我发布的/我承接的）
- 发布链路：文字或语音（MediaRecorder→base64）→ 智能解析回显（**全部槽位可手动修改**）→ 确认发布；**L3 风险直接弹窗引导官方渠道，不进广场**
- 风格与管理端统一：深蓝主题、圆角卡片、L1绿/L2黄/L3红彩色徽标、统一 toast/弹窗
- 后端配套最小改动（接口形状不变）：发布时手工槽位优先于解析结果；`GET /orders/mine`（我的发布+承接）；工单 DTO 增加 `review_record`；`main.py` 挂载 `/app` 静态目录
- 全链路实测通过：登录→广场→发布→接单→完成→评价→我的，L3 拦截（含「搬运/维修」关键词）回填官方渠道指引

**v0.2 变更**：管理端功能完善 + UI 重设计——
- 新增「订单管理」页：全量工单筛选（状态/风险/关键字）、详情弹窗、管理员取消
- 新增「用户管理」编辑能力：新建账号、编辑角色/租户/启用禁用、信用分调整（写流水留痕）x
- 新增「积分规则」增删改界面与「积分流水」总览接口
- 看板升级：今日新增、官方任务数、近 7 日新建/拦截趋势图、状态/风险分布条
- 全新 UI：深色侧边栏分组导航 + 复核角标、卡片式看板、统一弹窗/toast 组件

## 技术架构

```
┌────────────────────────── 浏览器（三端单文件 SPA，零构建） ──────────────────────────┐
│  管理端 /admin/        学生端 /app/（含拍照报修）  适老化端 /elder/（含信用页）              │
│  (桌面) Vue 风格组件化  (移动 480px) Hash 路由  (适老规范) 大图标高对比语音优先            │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                        原生 fetch · Bearer JWT · RESTful /api/v1
┌──────────────────────────────────┴───────────────────────────────────────────────┐
│  FastAPI 单进程五服务模块化（P3 可拆微服务）                                          │
│  ├─ users    注册登录 / JWT 鉴权 / 多租户字段                                        │
│  ├─ orders   工单状态机 / 接单完成评价 / 风险拦截                                     │
│  ├─ ai       意图解析 · RAG 问答 · SSE 流式 · Function Calling · AI 安全             │
│  ├─ credits  信用积分流水 / 申诉                                                     │
│  └─ admin    看板 / 复核 / 规则管理 / 审计                                          │
├──────────────────────────────────────────────────────────────────────────────────┤
│  AI 层：GLM-4-Flash（OpenAI 兼容端点，httpx 直连）                                    │
│  ├─ 意图解析：LLM JSON 槽位 + 枚举校验，失败降级规则引擎（R16 熔断）                    │
│  ├─ RAG：TF 余弦召回校园语料 → 拼接上下文生成 → 无 Key 纯检索兜底                       │
│  ├─ 流式：SSE（sources→delta→done）                                                  │
│  ├─ 工具：search_orders / get_credit / search_kb（白名单 MCP 风格 schema）             │
│  ├─ 多模态：GLM-4V-Flash 拍照报修（图片→槽位 JSON，降级规则解析）                      │
│  └─ 安全：提示词注入清洗 / 敏感输出过滤 / 规则表确定性 L3 拦截（R14）                    │
├──────────────────────────────────────────────────────────────────────────────────┤
│  数据层：SQLite（SQLAlchemy 2.0 Mapped）· 规则表/流水表留痕 · 审计日志                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

设计原则：**零外部依赖可运行**（无 npm/无构建/无外部数据库）、**AI 可降级**（无 Key 全功能可用）、**可解释可追溯**（来源标注/流水留痕/审计日志）。

## 团队信息

| 角色 | 职责 |
| --- | --- |
| 队长 / 后端架构 | 五服务模块化设计、AI 集成（GLM/RAG/流式/工具调用）、风控与积分规则引擎 |
| 前端工程 | 管理端/学生端/适老端三端 SPA（原生 HTML/CSS/JS，Hash 路由组件化） |
| 产品 / 测试 | 需求对齐计划文档、全链路 E2E 实测、演示材料 |

> 团队成员姓名与学号请在提交前补全此表（大赛要求 README 含团队信息）。

## 快速启动（全部在 D 盘项目目录内，不占 C 盘）

```powershell
cd D:\project_create\ai_school-system
# 首次：在项目目录内创建虚拟环境并安装依赖（venv 与 pip 缓存均在 D 盘）
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt --no-cache-dir --trusted-host pypi.tuna.tsinghua.edu.cn -i https://pypi.tuna.tsinghua.edu.cn/simple
# 启动（GLM Key 可选，未设置时 AI 自动降级规则引擎，功能完整可用；环境变量模板见 .env.example）
$env:AIC_GLM_API_KEY = "在这里粘贴你的智谱Key"
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

启动后：
- 学生端页面：http://127.0.0.1:8000/app/ （演示账号 `stu01 / 123456`、`stu02 / 123456`）
- 适老化端页面：http://127.0.0.1:8000/elder/（退休教职工，大图标高对比度语音优先，同一演示账号）
- 管理端页面：http://127.0.0.1:8000/admin/ （默认账号 `admin / admin123`）
- 接口文档（Swagger，可直接调试）：http://127.0.0.1:8000/docs

## 冒烟测试

```powershell
.\.venv\Scripts\python -m pip install pytest httpx2 --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple
.\.venv\Scripts\python -m pytest backend\tests\test_smoke.py -q
```

## 目录结构

```
ai_school-system/
├── backend/               # 后端（FastAPI 五服务）
│   ├── main.py            # 应用入口：路由组装 + 初始化种子数据 + 托管静态页
│   ├── config.py          # 配置（DB/上传目录均在项目内；GLM/ASR 环境变量）
│   ├── database.py        # SQLAlchemy + SQLite
│   ├── models.py          # 数据模型（工单/用户/风险规则/积分规则/流水/审计）
│   ├── security.py        # pbkdf2 密码哈希 + 手写 JWT（零第三方依赖）
│   ├── rules.py           # 确定性规则引擎：解析/分级/打分 + Demo 版 ASR 模拟
│   ├── services/
│   │   ├── users.py       # 注册登录 / JWT
│   │   ├── orders.py      # 工单状态机 / 接单完成评价 / 信用落账
│   │   ├── ai.py          # 意图解析 / ASR / 风险
│   │   ├── ai2.py         # RAG 问答 / SSE 流式 / Function Calling / AI 安全
│   │   ├── kb.py          # 校园知识库语料 + TF 余弦召回
│   │   ├── glm_client.py  # GLM 封装（OpenAI 兼容端点，失败返回 None 降级）
│   │   ├── credits.py     # 积分流水 / 申诉
│   │   └── admin.py       # 看板 / 复核 / 规则管理 / 审计
│   └── tests/test_smoke.py
├── web/admin/index.html       # 管理端单页（纯 HTML/JS，无 npm、无构建）
├── web/student/index.html     # 学生端单页 SPA：登录/广场/发布（文字+语音+拍照）/详情/我的/AI助手
├── web/elder/index.html       # 适老化端单页 SPA：大图标高对比度语音优先 + 信用页
├── docs/接口文档.md        # 全部接口的说明
├── docs/技术文档.md        # 参赛技术文档（概述/架构/AI方案/创新点）
├── docs/演示视频录制指南.md # 演示视频分镜脚本与录制流程
├── docs/decisions.md       # 技术决策记录（ADR）
├── .env.example            # 环境变量模板
├── data/                   # 运行时生成：app.db（SQLite）、uploads/
└── .venv/                  # Python 虚拟环境（项目内，D 盘）
```

## 磁盘占用说明（C 盘）

**本项目自身不占用 C 盘**：虚拟环境 `.venv\`、SQLite 数据库 `data\app.db`、上传文件 `data\uploads\` 全部在项目目录（D 盘）内。代码与页面为纯文本文件。

唯二可能触及 C 盘的既有环境（非本项目安装，本次开发也未向 C 盘写入）：

| 文件/目录 | 位置 | 说明 |
|---|---|---|
| Python 解释器（3.11.9，约 100 MB） | `C:\Users\dc213\AppData\Local\Programs\Python\Python311\` | 开发机原本已安装，项目直接复用，未新装 |
| pip 临时下载缓存 | `C:\Users\dc213\AppData\Local\pip\cache\` | 已用 `--no-cache-dir` 禁用，**不会写入**；若之前装过包留下过缓存，可执行 `python -m pip cache purge` 清空 |

> 每次运行 `python -m venv`、`pip install` 时命令本身来自上面那个 C 盘 Python，但它只读运行，不占新空间。

## 实现范围与计划任务的对应

| 计划任务 | 本框架状态 |
|---|---|
| T2.1 脚手架/数据层/多租户字段 | ✅ 五服务可启动，`tenant_id` 字段贯通（隔离逻辑 P3 强化） |
| T2.2 ASR 转写服务 | 🟡 接口形状已定（POST /ai/asr），现为模拟实现，`AIC_ASR_*` 已预留 |
| T2.3 意图解析与工单生成 | ✅ GLM 优先 + 规则引擎降级（枚举校验防幻觉） |
| T2.4 风险分级 + L3 拦截 | ✅ 规则表引擎（管理员可配置）+ L3 硬拦截 + 拦截日志 |
| T2.5 工单状态机 | ✅ 主链路 + 非法迁移拒绝（有单测） |
| T2.6 学生端（移动优先） | ✅ 单文件 SPA：登录/广场/发布（文字+语音+拍照多模态）/详情/我的/AI助手 |
| T3.4 管理员后台框架 | ✅ 看板/复核队列/订单管理/官方任务/风险规则/积分规则/用户管理/审计日志 |
| T3.3 积分闭环 | ✅ 事件自动挂钩（accept+1/complete+5/rate 阶梯），流水留痕可申诉 |
| T3.6 适老化端 | ✅ 大图标高对比度语音优先（对照工信部适老规范 2021） |

## 参赛材料索引

- 演示视频：按 `docs/演示视频录制指南.md` 录制（6 分钟分镜脚本）
- 技术文档：`docs/技术文档.md` + 已导出 `docs/技术文档.pdf`（10 页，≤30 页达标）
- 环境变量模板：`.env.example`（Key 不进代码与 git）
- 接口文档：`docs/接口文档.md`；运行时 Swagger：http://127.0.0.1:8000/docs

## 已知简化（按"先能跑"原则）

- ASR 为本地模拟（接口形状已定，`AIC_ASR_*` 预留真实识别接入位）。
- RAG 检索为 TF 余弦（零依赖可运行）；语料规模扩大后可平迁向量数据库（召回接口不变）。
- 匹配引擎为 Top-1 简化打分（AHP 权重可解释结构已留好）。
- 看板趋势图为纯 CSS 迷你柱状图（无第三方图表库）。
- SSE 流式为服务端逐句推送（模拟 token 间隔）；接真实 LLM 流式 API 时替换 delta 生成即可，前端无需改动。
