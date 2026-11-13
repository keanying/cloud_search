# 云搜浏览器 cloud_search

以对话为入口、由云端 AI 与受控浏览器完成搜索研究、采集整理、分析和报告交付的产品（V1.2：聊天前台 + 云端执行 + 右侧只读阅览）。

- **前端**：Vue 3 + TypeScript + Vite + Pinia + Tailwind（`web/`）
- **后端**：Python 3.12+ / FastAPI（API 与 worker 同一代码库，`backend/`）
- **智能体**：Pydantic AI（单智能体运行时）+ 自研 DAG 编排（状态在 MySQL）
- **大模型**：任意 OpenAI 兼容接口（OpenAI / DeepSeek / Kimi / 火山方舟 / 通义千问 / 智谱 / 自建网关），在管理后台按智能体角色绑定主模型与备用模型
- **搜索**：**不使用搜索 API**，由云端浏览器（Playwright + Chromium）打开必应/百度/搜狗搜索页面；遇到验证码自动冷却换引擎，绝不破解
- **数据库**：MySQL 8（`cloudsearch_app`，表名 `src_opr_*_f` / `src_prd_*_f`）；本地开发可用 SQLite

## 快速开始（本地开发）

```bash
# 后端（首次会自动建 SQLite 表，并在 API 进程内嵌 worker）
cd backend
uv sync
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers uv run uvicorn cloudsearch.app:app --port 8000   # 已安装 Chromium 时
# 或先安装浏览器：uv run playwright install chromium
```

```bash
# 前端
cd web
pnpm install
pnpm dev     # http://localhost:5173 ，/api 代理到 127.0.0.1:8000
```

1. 打开页面注册账号——**第一个注册的账号是管理员**。
2. 进入「管理后台 → 大模型」：添加供应方（填 API Key，仅加密保存）→ 添加模型（勾选能力：工具调用 / JSON Schema / JSON 模式，填单价）→ 「智能体绑定」里至少绑定 `default`，也可为 8 个角色分别指定模型和备用模型。
3. 回到首页直接提问。

## Docker 部署

```bash
cp .env.example .env   # 修改 CS_SECRET_KEY、CS_MASTER_KEY
docker compose up -d --build
# 访问 http://localhost:8080
```

服务：`mysql`（MySQL 8）、`api`（启动时 `alembic upgrade head`）、`worker`（云端浏览器与智能体执行，可水平扩展）、`web`（nginx，已为 SSE 关闭缓冲）。

## 目录结构

```
backend/cloudsearch/
  agents/                     八个智能体，各自独立子包（schemas / prompts / agent / README）
    requirement_compiler/     需求编译：识别 chat / clarify / task，生成 TaskSpec
    coordinator/              协调：阶段规划（程序）+ 覆盖度评估与补查（模型）
    search_planner/           搜索规划：生成搜索词矩阵
    browser_researcher/       浏览研究：程序化读页 + 必要时由模型选择交互动作
    extractor/                信息抽取：事实/字段 + 逐字原文摘录
    verifier/                 核验：摘录逐字定位（程序）+ 跨来源冲突（模型）
    analyst/                  分析：受限计算方案，DuckDB 确定性执行
    report_writer/            写作：带 [n] 引用的回答/报告，引用由程序校验
    base.py                   AgentSpec、统一调用（模型解析、栅栏、预算、用量与费用）
  llm/                        供应方预设、按角色解析模型（备用链、能力矩阵 → 输出方式）
  browser/                    浏览器池（每任务独立 context、阅览帧）、SSRF 出口防护、实读
  search/                     浏览器搜索引擎适配（必应/百度/搜狗）、轮换与冷却、诱饵结果检测
  orchestrator/               执行上下文（栅栏/预算/可复用步骤）、四模式流水线、控制命令、文件导出
  services/                   事件与投影（SSE）、对话轮次处理
  worker/                     worker 主循环（领取对话轮次与任务运行）
  api/                        FastAPI 路由与契约（schemas.py）
  db/                         SQLAlchemy 模型（MySQL 8 / SQLite）
backend/migrations/           Alembic 迁移
backend/tests/                端到端与单元测试（假模型 + 假浏览器，不触网不计费）
web/src/                      Vue 3 前端（views / components / stores / api）
```

## 核心行为（对应 PRD/技术文档的硬约束）

- 首屏是聊天框；普通对话、澄清不会启动浏览器或建任务。「智能模式」只是选择策略，任务模式只有 quick_search / research / dataset / hybrid。
- 清晰的简单问题自动执行；数据/混合任务首次必须确认字段，确认绑定 `plan_hash`，计划变化后旧确认失效。
- **右侧阅览只读**：打开/切换/刷新/关闭阅览都不会创建浏览器、导航或停止任务；P0 为定期截图（标注帧时间、过期、断连），含密码框的页面不提供画面。
- **停止当前轮**只停止该轮绑定的任务：递增 `cancel_generation`，worker 在下一个栅栏点停止；停止后到达的结果被隔离（`late_result_quarantined`），不进入来源/报告，也不再发起新的模型调用；已提交的来源保留。
- **暂停/继续**：同一任务新 run，已成功的节点直接复用（不重复搜索、读取、计费）。
- 证据：摘录必须能在实读正文中逐字定位，否则丢弃；数据字段无可校验摘录则置空并注明原因；来源冲突的字段不取平均、置空并标注；发布时间只取页面声明，未知为空。
- 引用：回答中的 `[n]` 由程序校验，不存在的序号被删除。
- 计算：模型只给受限方案，DuckDB 参数化执行；缺失值不当 0。
- 导出：CSV（UTF-8 BOM、防公式注入）、XLSX（数据/字段字典/来源/分析）、JSON、Markdown 报告。
- 费用：按每次实际响应的模型计价；单价未知记为 unknown，不记 0；任务有请求次数上限。

## 测试

```bash
cd backend
uv run pytest -q                                   # SQLite
CS_TEST_DATABASE_URL="mysql+asyncmy://user:pwd@127.0.0.1:3306/cs_test?charset=utf8mb4" uv run pytest -q   # MySQL 8
```

## 当前状态与后续

已实现：聊天前台、八智能体流水线（四种模式）、浏览器搜索与实读、只读阅览、来源/证据、数据与报告文件、停止/暂停/继续/续做、多模型配置与费用记录。

尚未实现（按设计文档属后续阶段）：附件上传与解析、实时视频阅览（live）、人工登录接管、业务数据库投递、桌面客户端、S3/OSS 对象存储适配器、人工审核流。
