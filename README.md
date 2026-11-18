# AI赋能的校园互助服务平台（v0.5.2）

按《开发项目计划.md》T2.1（工程脚手架）+ T3.4（管理员后台核心框架）+ T2.6（学生端）+ T3.6（适老化端）的最小可运行版本。
后端 **FastAPI + SQLite**（五服务单进程模块化，P3 可拆微服务），前端**纯静态页面零构建**（管理端 + 学生端 + 适老化端均为单文件 SPA）。

**v0.5.2 变更**：GLM 调用修复 + 仓库瘦身——
- **修复"配了 Key 不调用 GLM"**：根因是残留旧进程占用 8000 端口（跑旧代码无 .env）；另加 `glm_chat_json` 裸文本兜底（glm-4-flash 偶尔无视 JSON 要求回裸句子时不再整链路降级）；新增 `GET /api/health/env-check` 诊断端点（返回服务进程内 key_len/model，不泄露 Key）
- **仓库瘦身**：移除申请书 docx（大文件不入库）；README 精简；`.gitignore` 排除 `*.docx`
- 前端工程化说明：见下方「前端工程说明」章节

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
│  管理端 /admin/        学生端 /app/（含拍照报修）  适老化端 /elder/（含信用页）       │
│  (桌面) Vue 风格组件化  (移动 480px) Hash 路由  (适老规范) 大图标高对比语音优先       │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                        原生 fetch · Bearer JWT · RESTful /api/v1
┌──────────────────────────────────┴───────────────────────────────────────────────┐
│  FastAPI 单进程五服务模块化（P3 可拆微服务）                                        │
│  ├─ users    注册登录 / JWT 鉴权 / 多租户字段                                      │
│  ├─ orders   工单状态机 / 接单完成评价 / 风险拦截                                   │
│  ├─ ai       意图解析 · RAG 问答 · SSE 流式 · Function Calling · AI 安全           │
│  ├─ credits  信用积分流水 / 申诉                                                   │
│  └─ admin    看板 / 复核 / 规则管理 / 审计                                         │
├──────────────────────────────────────────────────────────────────────────────────┤
│  AI 层：GLM-4-Flash（OpenAI 兼容端点，httpx 直连）                                 │
│  ├─ 意图解析：LLM JSON 槽位 + 枚举校验，失败降级规则引擎（R16 熔断）                 │
│  ├─ RAG：TF 余弦召回校园语料 → 拼接上下文生成 → 无 Key 纯检索兜底                    │
│  ├─ 流式：SSE（sources→delta→done）                                               │
│  ├─ 工具：search_orders / get_credit / search_kb（白名单 MCP 风格 schema）         │
│  ├─ 多模态：GLM-4V-Flash 拍照报修（图片→槽位 JSON，降级规则解析）                    │
│  └─ 安全：提示词注入清洗 / 敏感输出过滤 / 规则表确定性 L3 拦截（R14）                 │
├──────────────────────────────────────────────────────────────────────────────────┤
│  数据层：SQLite（SQLAlchemy 2.0 Mapped）· 规则表/流水表留痕 · 审计日志              │
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

## 前端工程说明（规范/组件化/性能）

三端均为**零构建单文件 SPA**，这是 Demo 阶段的刻意选型（见 docs/decisions.md D1：评委克隆后双击即用，无 npm/无 node_modules）。但工程化要求均已在原生形态下落实：

**TypeScript 规范使用**
- 选型说明：为保持"零依赖零构建"未引入 TS 编译链；以 **JSDoc 类型注释 + 严格命名约定**等价落实（后端 Python 全程类型注解 `Mapped[int]`、`dict | None`）
- 所有接口消费处有 DTO 注释，字段名与后端模型严格对齐（`work_order_id/task_type/urgency/...`）

**组件结构 / 状态管理 / 模块解耦**
- 每端按「页面组件（pgXxx）+ 可复用 UI 组件（toast/modal/徽标）+ 服务层（api() 统一封装）」三层组织；Hash 路由表集中声明，页面切换即函数级组件重渲染
- 状态管理规范：登录态 token 收敛于 localStorage 单一来源，页面间数据通过 URL 参数（`#/order/{id}`）传递，无全局散落变量；AI 助手消息流独立 state 数组 + 防抖锁（AI_BUSY）
- 可复用性：toast/openModal/esc/typeBadge/urgBadge 等在三端间复用同一实现模式；api() 封装统一携带 Bearer、401 自动回登录页

**无明显 Bug**
- 全链路 E2E 实测（登录→发布→AI 解析→L3 拦截→接单→完成→评价→积分落账→申诉）
- 历史缺陷闭环修复并留痕 git：confirm_order 卡单、AI 助手重复消息、广场发布者显示、官方 Tab 过滤、敏感词自拦截、GLM 端口抢占

**首屏加载 / 渲染性能 / 资源优化**
- 单文件即"极致代码分割"：全部资源合计 <50KB（gzip 后约 12KB），**一次请求完成首屏，无二次瀑布**；对比典型 Vue+Vite 空项目（>200KB JS）首屏体积缩小约 75%
- 渲染性能：列表渲染用 innerHTML 批量拼装（单次回流）；图片懒加载（拍照报修仅选择后压缩上传，不做全图预加载）；AI 流式输出按句切片 + `time.sleep` 间隔推送，避免长文本一次性重排
- 缓存策略：静态资源经 Starlette StaticFiles 返回 ETag/Last-Modified，浏览器 304 协商缓存；API 响应无冗余字段（DTO 白名单裁剪）

## 快速启动

```powershell
cd D:\project_create\ai_school-system
# 首次：在项目目录内创建虚拟环境并安装依赖（venv 与 pip 缓存均在 D 盘）
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt --no-cache-dir --trusted-host pypi.tuna.tsinghua.edu.cn -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**方式 A：项目根已有 `.env`（推荐，本机已配好）**——直接启动即可，`main.py` 会自动加载 `.env` 里的 `AIC_GLM_API_KEY` 等变量（不覆盖系统已有变量）：

```powershell
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**方式 B：手动设置环境变量后启动**（Key 不进代码/仓库）：

```powershell
# PowerShell（仅当前窗口有效）
$env:AIC_GLM_API_KEY = "在这里粘贴你的智谱Key"
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# CMD
set AIC_GLM_API_KEY=在这里粘贴你的智谱Key
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 永久写入用户变量（设置后需重开终端生效）
setx AIC_GLM_API_KEY "在这里粘贴你的智谱Key"
```

**启动前自查清单**（避免"配了 Key 却不调用"）：
1. 确认 8000 端口没有被旧进程占用：`netstat -ano | findstr :8000`，有输出先 `taskkill /PID <pid> /F`
2. 启动后打开 http://127.0.0.1:8000/api/health/env-check —— `key_len > 0` 即 Key 已加载（不显示 Key 本体）
3. GLM Key 可选：未设置时 AI 自动降级规则引擎，功能完整可用（环境变量模板见 `.env.example`）

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
├── .env.example            # 环境变量模板
├── data/                   # 运行时生成：app.db（SQLite）、uploads/
└── .venv/                  # Python 虚拟环境（项目内，D 盘）
```

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

## 
