# AI赋能的校园互助服务平台（v0.4.3 Demo）

按《开发项目计划.md》T2.1（工程脚手架）+ T3.4（管理员后台核心框架）+ T2.6（学生端）+ T3.6（适老化端）的最小可运行版本。
后端 **FastAPI + SQLite**（五服务单进程模块化，P3 可拆微服务），前端**纯静态页面零构建**（管理端 + 学生端 + 适老化端均为单文件 SPA）。

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

## 快速启动（全部在 D 盘项目目录内，不占 C 盘）

```powershell
cd D:\project_create\ai_school-system
# 首次：在项目目录内创建虚拟环境并安装依赖（venv 与 pip 缓存均在 D 盘）
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt --no-cache-dir --trusted-host pypi.tuna.tsinghua.edu.cn -i https://pypi.tuna.tsinghua.edu.cn/simple
# 启动
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
│   ├── config.py          # 配置（DB/上传目录均在项目内）
│   ├── database.py        # SQLAlchemy + SQLite
│   ├── models.py          # 数据模型（工单/用户/风险规则/积分规则/流水/审计）
│   ├── security.py        # pbkdf2 密码哈希 + 手写 JWT（零第三方依赖）
│   ├── rules.py           # 确定性规则引擎：解析/分级/打分 + Demo 版 ASR 模拟
│   ├── services/          # 五服务路由：users / orders / ai / credits / admin
│   └── tests/test_smoke.py
├── web/admin/index.html       # 管理端单页（纯 HTML/JS，无 npm、无构建）
├── web/student/index.html     # 学生端单页 SPA：登录/广场/发布/详情/我的（v0.3）
├── web/elder/index.html       # 适老化端单页 SPA：大图标高对比度语音优先（v0.4）
├── docs/接口文档.md        # 全部接口的说明
├── data/                  # 运行时生成：app.db（SQLite）、uploads/
└── .venv/                 # Python 虚拟环境（项目内，D 盘）
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
| T2.2 ASR 转写服务 | 🟡 接口形状已定（POST /ai/asr），现为模拟实现 |
| T2.3 意图解析与工单生成 | 🟡 规则版解析（词表+正则），LLM 接入后替换 |
| T2.4 风险分级 + L3 拦截 | ✅ 规则表引擎（管理员可配置）+ L3 硬拦截 + 拦截日志 |
| T2.5 工单状态机 | ✅ 主链路 + 非法迁移拒绝（有单测） |
| T2.6 学生端（移动优先） | ✅ 单文件 SPA：登录/广场/发布/详情/我的；语音链路为 Demo ASR |
| T3.4 管理员后台框架 | ✅ 看板/复核队列/订单管理/官方任务/风险规则/积分规则/用户管理/审计日志 |
| T3.3 积分闭环 | 🟡 规则增删改界面就绪、流水总览就绪；事件自动挂钩在 P3 补 |
| T3.6 适老化端 | ⬜ 按计划在后续版本开发 |

## 已知简化（按"先能跑"原则）

- ASR/LLM 为本地规则模拟，不调用外部接口（不花钱、不出网）；学生端语音链路走 `/ai/asr` Demo 实现。
- 积分流水尚未与工单事件自动挂钩（表、规则管理界面与流水查询接口已就绪）。
- 匹配引擎为 Top-1 简化打分（AHP 权重可解释结构已留好）。
- 看板趋势图为纯 CSS 迷你柱状图（无第三方图表库）。
- 学生端已上线（v0.3）；适老化端按计划在 T3.6 后续开发。
