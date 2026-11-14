# 本地 / 私有服务器完整部署（数据不出域）

目标：文档解析、大模型都跑在你自己的机器或内网服务器上，上传的文件和对话内容不发往任何外部服务；
所需的软件与模型由启动脚本**随启动一起自动准备**（首次下载，之后离线运行）。

## 一、组成

| 组件 | 作用 | 在哪运行 | 由谁准备 |
|---|---|---|---|
| 云搜浏览器（本项目） | 页面、API、8 个智能体、云端浏览器 | 本机 `.venv` | `start.bat` / `run.py` / `scripts/server.sh setup` |
| MinerU 4.x | PDF/扫描件/图片/Office → Markdown（OCR、表格、公式、版面） | 本机 `.venv-mineru`，模型在 `.mineru/models`，只监听 127.0.0.1 | 同上（`mineru.local: true`） |
| 本地大模型 | 智能体推理 | Ollama（本机）或 vLLM/Xinference 等（内网 GPU 服务器） | Ollama 模型由启动脚本拉取；Ollama 本体需先安装 |
| 数据库 | SQLite（默认）或内网 MySQL 8 | 本机 / 内网 | `config.yaml` 的 database |

## 二、硬件建议

| 场景 | CPU / 内存 | 显卡 | MinerU tier | 本地大模型 |
|---|---|---|---|---|
| 个人电脑试用 | 8 核 / 16GB | 无 | `basic`（模型约 0.8GB） | qwen3:8b（约 5GB，CPU 可跑但较慢） |
| 部门服务器 | 16 核 / 32GB | 1 张 16–24GB 显卡 | `standard` | qwen3:14b / qwen3:32b |
| 高并发 | 32 核 / 64GB+ | 多卡 | `standard`，`extras: full` | vLLM 部署 Qwen3 系列 |

磁盘：MinerU 环境约 0.7GB + 模型 0.8GB（basic）/ 数 GB（standard）；大模型按所选模型大小预留。

## 三、配置（config.yaml）

```yaml
mineru:
  local: true                 # 本机托管 MinerU：自动安装、下载模型、离线启动
  tier: basic                 # 无显卡用 basic；有显卡/12 核以上可用 standard
  model_source: modelscope    # 国内用 modelscope；失败会自动换 huggingface（经 hf-mirror.com）

privacy:
  data_local_only: true       # 开启数据不出域

local_llm:
  ollama_models: [qwen3:8b]   # 启动时自动拉取，并登记为“本地模型（Ollama）”，没有默认模型时设为默认
```

使用内网 GPU 服务器上的模型（vLLM / Xinference / 公司网关）时，不用 Ollama，改在 `llm` 分区登记：

```yaml
llm:
  providers:
    - name: 内网大模型
      type: openai_compatible
      base_url: http://10.0.0.20:8000/v1
      api_key: anything
      models:
        - {name: Qwen3-32B, supports_tools: true}
  bindings:
    default: {model: 内网大模型/Qwen3-32B}

privacy:
  data_local_only: true
  allowed_hosts: [llm.corp.example]   # 如果内网网关用的是域名
```

## 四、启动

**Windows（开发机）**：双击 `start.bat`（或 `python run.py`）。首次会依次：

1. 安装主程序依赖、浏览器、前端；
2. 安装 MinerU 到 `.venv-mineru`（多个 pip 镜像自动测速、失败换源）；
3. 下载 MinerU 模型到 `.mineru/models`（ModelScope → HuggingFace 镜像）；
4. 确保 Ollama 在运行并拉取 `local_llm.ollama_models`；
5. 迁移数据库，离线启动 MinerU（127.0.0.1:8002），再启动主程序。

之后每次启动都会跳过已完成的步骤；按 Ctrl+C 会一起停止 MinerU。

每次启动都会**重启 MinerU**：如果 8002 端口还被上次残留的本项目 MinerU 占着（例如在 PyCharm 里直接点了停止），
会先结束它再重新启动；占用端口的若是其他程序则不会动它，只提示 PID 与命令行。想沿用正在运行的 MinerU 可加
`python run.py --keep-mineru`。Windows 上启动器还会把 MinerU、主程序、worker 放进同一个“作业”，启动器被强制结束时系统会一并结束它们，不再残留。

**Linux 服务器**：

```bash
scripts/server.sh setup     # 安装依赖、MinerU 与模型、拉取 Ollama 模型、迁移
scripts/server.sh start     # 启动 MinerU（离线）+ API + worker
scripts/server.sh status    # 查看 api / worker / mineru / 浏览器 / 健康状态
scripts/server.sh logs mineru
```

Ollama 在 Linux 上通常以系统服务运行（官方安装脚本会配置 systemd），本项目不负责启停它。

**完全离线的机器**：在能联网的同型号机器上执行一次 setup，然后把整个目录（含 `.venv`、`.venv-mineru`、`.mineru`、`.playwright`、`web/dist`）
连同 Ollama 的模型目录（Linux `~/.ollama`，Windows `%USERPROFILE%\.ollama`）拷过去，启动时加 `--no-install`。

## 五、数据不出域的范围

开启 `privacy.data_local_only` 后，程序强制执行：

- 大模型：只调用本机/内网地址（localhost、私网 IP、`*.local/*.internal/*.lan`、`allowed_hosts`）；公网供应方被拒绝，
  后台“测试”也不会向它发请求。代理软件的 fake-ip 网段（198.18.0.0/15）不算内网。
- 文件解析：不使用 mineru.net 云端/轻量接口，只用本机 MinerU 或内置解析。
- 涉及上传文件的任务不联网搜索（即使模型要求联网也会被关闭），避免文件内容出现在搜索词里。
- 不涉及文件的提问仍可联网搜索公开信息——搜索本身就是访问公网；如果完全不需要联网，只用文件问答即可。

在 **管理后台 → 运行参数 → 部署配置（只读）** 可以看到“文件解析”和“数据不出域”的当前状态。
