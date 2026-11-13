# 云搜浏览器 cloud_search

以对话为入口、由云端 AI 与受控浏览器完成搜索研究、采集整理、分析和报告交付的产品（V1.2：聊天前台 + 云端执行 + 右侧只读阅览）。

- **前端**：Vue 3 + TypeScript + Vite + Pinia + Tailwind（`web/`）
- **后端**：Python 3.12+ / FastAPI（API 与 worker 同一代码库，`backend/`）
- **智能体**：Pydantic AI（单智能体运行时）+ 自研 DAG 编排（状态在 MySQL）
- **大模型**：任意 OpenAI 兼容接口（OpenAI / DeepSeek / Kimi / 火山方舟 / 通义千问 / 智谱 / 自建网关），在管理后台按智能体角色绑定主模型与备用模型
- **搜索**：**不使用搜索 API**，由云端浏览器（Playwright + Chromium）打开必应/百度/搜狗搜索页面；遇到验证码自动冷却换引擎，绝不破解
- **数据库**：MySQL 8（`cloudsearch_app`，表名 `src_opr_*_f` / `src_prd_*_f`）；本地开发可用 SQLite

## 需要安装的组件（Windows 开发机）

| 组件 | 版本 | 说明 |
|---|---|---|
| **Python** | 3.12 或 3.13（64 位） | https://www.python.org/downloads/ ，安装时勾选 “Add python.exe to PATH” |
| **Node.js** | 20 或 22 LTS | https://nodejs.org/ ，自带 npm 与 corepack（自动提供 pnpm） |
| Git | 任意 | 拉取代码 |
| uv（可选） | 最新 | `pip install uv`，有则按 uv.lock 锁定版本且安装更快；没有则自动用 pip |
| MySQL 8（可选） | 8.0+ | 本地开发默认用 SQLite，零安装；生产用 MySQL |

以下由启动脚本**自动安装到项目目录内**，无需手动处理：Python 依赖（`cloud_search/.venv`）、前端依赖（`web/node_modules`）与打包产物（`web/dist`）。所有依赖都有 Windows 预编译包，不需要 C/C++ 编译器。

**浏览器**：默认 `browser.channel: auto`——Windows 直接使用系统自带的 **Microsoft Edge**（或已安装的 Chrome），不需要下载；只有找不到可用浏览器时（如 Linux 服务器）才下载 Playwright 自带 Chromium 到 `cloud_search/.playwright`。

## 一键启动

**Windows**：双击 `start.bat`（或在命令行执行 `start.bat`）。首次会自动：

1. 生成 `config.yaml`（从 `config.example.yaml` 复制）
2. 在根目录创建 `.venv` 并安装后端依赖
3. 下载 Chromium 到 `.playwright`
4. 安装前端依赖并打包
5. 迁移/创建数据库，启动服务并打开浏览器 → http://127.0.0.1:8000（页面与接口同一端口）

之后再启动会自动跳过已完成的步骤（依赖或前端代码有变化时才重新安装/打包）。macOS/Linux 开发机用 `./start.sh`。

常用参数（`start.bat` 与 `./start.sh` 相同）：

```
start.bat --dev          前端热更新开发模式（http://127.0.0.1:5173）
start.bat --no-install   跳过依赖检查，启动更快
start.bat --rebuild      强制重装依赖并重新打包
start.bat --port 8001    临时换端口
```

**多下载源自动切换**：安装前会并发测速，按从快到慢依次尝试，某个源失败或卡住（20 秒无数据）自动换下一个：

| 下载内容 | 候选源 |
|---|---|
| Python 包 | 官方 PyPI、清华、阿里云、腾讯云、华为云 |
| 前端包 | 官方 npm、阿里云 npmmirror、腾讯云、华为云 |
| Chromium | 官方、阿里云 npmmirror、华为云（清华/腾讯无此镜像） |

Python 依赖从 `requirements.txt` 安装（由 `uv.lock` 导出，**锁定版本和文件哈希**，任何镜像下载到的文件都必须与官方一致）。也可以在 `config.yaml` 的 `install` 分区指定只用哪些源。修改依赖后重新导出：`uv lock && uv export --frozen --no-emit-project --all-groups -o requirements.txt`。

首次使用：**第一个注册的账号是管理员**。在 `config.yaml` 的 `llm` 分区配置大模型（或在页面“管理后台 → 大模型”中添加），至少绑定 `default` 角色即可开始提问。

## 统一配置 config.yaml

所有配置集中在根目录 `config.yaml`（模板 `config.example.yaml`，含逐项中文说明；该文件含密码/API Key，已被 git 忽略）：

| 分区 | 内容 |
|---|---|
| `server` | 监听地址与端口 |
| `database` | `type: sqlite/mysql`、MySQL 连接信息、是否自动建表 |
| `security` | JWT 密钥、API Key 加密主密钥、是否开放注册 |
| `browser` / `search` | 云端浏览器（内核 auto/Edge/Chrome/自带、无头、代理、并发）与搜索引擎顺序、冷却 |
| `task` / `worker` | 单任务上限、执行器（内嵌/独立、进程数、并发） |
| `storage` | 文件存储目录 |
| `install` | 下载源（留空自动测速选择；可指定 pip / npm / Chromium 源列表） |
| `llm` | 大模型供应方、模型、单价、8 个智能体的模型绑定（启动时同步进数据库） |

优先级：环境变量 `CS_*` > `config.yaml` > 默认值。写错键名会在启动时报错并指出是哪一项。

## 服务器部署（Linux）

```bash
cp config.example.yaml config.yaml      # 修改：server.host=0.0.0.0、database.type=mysql、security 密钥、worker.embedded=false
scripts/server.sh setup                 # 安装 .venv / Chromium（root 时连同系统依赖）/ 前端打包 / 数据库迁移
scripts/server.sh start                 # 启动 API（含页面）与 worker.processes 个独立 worker
scripts/server.sh status                # 进程、健康接口、数据库、Chromium、磁盘
scripts/server.sh check                 # 同上，异常时退出码 1（可配合 cron/监控告警）
scripts/server.sh restart
scripts/server.sh stop
scripts/server.sh logs [api|worker]     # 跟踪日志（logs/ 目录）
```

更新代码后：`git pull && scripts/server.sh setup && scripts/server.sh restart`。

也可用 Docker：`cp config.example.yaml config.yaml && docker compose up -d --build`，访问 http://localhost:8080 。

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
run.py / start.bat / start.sh 一键启动（环境 + 前端打包 + 运行）
scripts/server.sh             服务器 启动/停止/重启/检查
config.example.yaml           统一配置模板（复制为 config.yaml）
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
- 模型兼容：DeepSeek / Kimi / 通义 / 智谱使用 pydantic-ai 专用适配器（思考模式、reasoning_content 回传等）；任何模型若因“不支持强制工具调用 / 思考模式 / 不支持工具”被拒（400），自动降级输出方式（强制工具 → 自动工具 → 提示词 JSON）重试，并把能力写回模型配置。管理后台“测试”会同时验证结构化输出。
- 数据库结构升级：启动时自动迁移（包括早期直接建表、没有迁移记录的库）。

## 测试

```bash
uv run pytest -q                                   # 在仓库根目录执行；SQLite
CS_TEST_DATABASE_URL="mysql+asyncmy://user:pwd@127.0.0.1:3306/cs_test?charset=utf8mb4" uv run pytest -q   # MySQL 8
```

## 当前状态与后续

已实现：聊天前台、八智能体流水线（四种模式）、浏览器搜索与实读、只读阅览、来源/证据、数据与报告文件、停止/暂停/继续/续做、多模型配置与费用记录。

尚未实现（按设计文档属后续阶段）：附件上传与解析、实时视频阅览（live）、人工登录接管、业务数据库投递、桌面客户端、S3/OSS 对象存储适配器、人工审核流。
