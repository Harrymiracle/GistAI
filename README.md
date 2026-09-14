# GistAI

GistAI 是一个面向个人知识库的 AI 阅读助手。它可以导入和清洗网页文章，生成摘要与标签，构建向量索引，并通过普通 RAG 或受控 Agent 基于知识库和 Web Search 回答问题。

## 当前能力

- 文章导入、正文抽取、Playwright 动态页面回退与手动内容补充
- AI 摘要、标签管理、关键词搜索与语义搜索
- 文本切片、Embedding、基于 PostgreSQL + pgvector 的 RAG 问答
- Agent 知识库检索、一次查询改写、受控 Web Search、全文读取与证据评估
- 回答来源展示，以及 `Complete`、`Partial`、`Insufficient` 等证据状态
- 基于 PostgreSQL Checkpointer 的多轮对话状态持久化与用户隔离

## 系统架构

```text
文章导入与清洗 → AI 摘要 / 标签 → Chunk / Embedding → PostgreSQL + pgvector
                                                    ↓
React Chat → Agent API → 检索 / 全文读取 / 证据评估 → 有来源的回答
                         ↓
                 PostgreSQL Checkpoint
```

普通 RAG 提供单轮知识库问答；Agent 在固定预算和运行策略内组合知识库检索、查询改写、Web Search、全文读取和证据评估，并在证据不足时安全结束。

## 技术栈

| 模块 | 主要技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite、React Router、TanStack Query、Axios |
| 后端 | Python、FastAPI、SQLAlchemy、Alembic、LangGraph |
| 数据库 | PostgreSQL 16、pgvector |
| AI 能力 | OpenAI 兼容的 LLM / Embedding API、Tavily Web Search |
| 内容抽取 | Trafilatura、Playwright |

Web Search 已通过独立 Provider 接口接入。当前默认实现为 Tavily，后续可以在不改动 Agent 主流程的情况下替换搜索服务。

## 目录结构

```text
.
├── apps/
│   ├── web/                 # React + TypeScript 前端
│   └── server/              # FastAPI 后端、Alembic 迁移与测试
├── docs/                    # 产品、架构与各阶段实施文档
├── infra/                   # 基础设施相关文件
├── docker-compose.yml       # PostgreSQL + pgvector
├── package.json             # 前端 workspace 命令
└── .env.example             # 本地配置模板
```

## 环境要求

推荐使用 Windows PowerShell，并提前安装：

- Python 3.12
- Node.js 22 与 npm 10
- Docker Desktop（用于运行 PostgreSQL + pgvector）

本项目当前开发环境使用上述版本。其他兼容版本可能也能运行，但建议优先保持一致。

默认使用以下本地端口：

| 服务 | 端口 |
| --- | ---: |
| 前端 Vite | 5173 |
| FastAPI 后端 | 8000 |
| PostgreSQL | 5432 |

## 本地启动

以下命令均假设当前目录为仓库根目录。首次启动请依次完成数据库、后端和前端配置。

### 1. 创建本地配置

```powershell
Copy-Item .env.example .env
```

在本机编辑 `.env`，按需填写 LLM、Embedding 和 Web Search 配置。`.env` 已被 Git 忽略，不要提交真实密钥，也不要将密钥写入代码、日志或截图。

默认数据库配置与 `docker-compose.yml` 一致，可直接用于本地开发。使用文章摘要和 Agent 时需要配置 LLM；使用语义检索和 RAG 时需要配置 Embedding；使用联网检索时需要配置 Tavily Web Search。

### 2. 启动 PostgreSQL + pgvector

```powershell
docker compose up -d postgres
docker compose ps
```

请确认 `gistai-postgres` 已启动并通过健康检查，再继续启动后端。

### 3. 安装并启动后端

打开一个新的 PowerShell 窗口：

```powershell
Set-Location apps/server

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
.\.venv\Scripts\python.exe -m playwright install chromium

.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Alembic 负责业务表迁移。LangGraph checkpoint 表由后端启动时通过官方 Checkpointer 的 `setup()` 初始化，不纳入业务 Alembic migration。后端启动阶段需要连接 PostgreSQL，因此数据库不可用时服务会直接启动失败。

Playwright 浏览器安装在本机用户缓存中，不会写入 Git 仓库。

### 4. 安装并启动前端

再打开一个 PowerShell 窗口，并回到仓库根目录：

```powershell
npm install --registry=https://registry.npmmirror.com
npm run dev:web
```

前端开发服务器会将 `/health` 和 `/api` 请求代理到 `http://127.0.0.1:8000`。

### 5. 访问服务

| 页面或接口 | 地址 |
| --- | --- |
| 前端首页 | `http://127.0.0.1:5173` |
| AI 助手 | `http://127.0.0.1:5173/agent` |
| 后端健康检查 | `http://127.0.0.1:8000/health` |
| Swagger API 文档 | `http://127.0.0.1:8000/docs` |
| OpenAPI 描述 | `http://127.0.0.1:8000/openapi.json` |

## 环境变量说明

完整变量和本地默认值请查看 `.env.example`。主要配置分组如下：

| 配置组 | 变量 | 用途 |
| --- | --- | --- |
| 数据库 | `DATABASE_URL`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD` | 业务数据、pgvector 与 Agent checkpoint |
| LLM | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`LLM_TIMEOUT_SECONDS` | 摘要、标签、RAG 和 Agent 推理 |
| Embedding | `EMBEDDING_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSION` | 文章向量化与语义检索 |
| Web Search | `WEB_SEARCH_BASE_URL`、`WEB_SEARCH_API_KEY`、`WEB_SEARCH_MAX_RESULTS` | Agent 联网检索，当前默认 Tavily |
| 网页抓取 | `FETCH_*`、`PLAYWRIGHT_*` | HTTP 抓取、重定向和动态页面回退 |
| RAG | `RAG_*` | 切片大小、重叠、召回数量和相似度阈值 |
| Agent | `AGENT_MAX_FULLTEXT_CONTEXT_TOKENS` | 全文读取的上下文预算 |

如果更改 `EMBEDDING_DIMENSION`，需要确保它与 Embedding 服务返回的向量维度以及数据库中的 vector 字段一致。

## Agent 对话说明

前端 AI 助手调用 `POST /api/v1/agent/chat`。首次请求由后端生成 `thread_id`，当前页面内的后续请求会复用该值。

服务端使用 `user_id:thread_id` 作为 checkpoint 隔离键，因此同一对话可以在后端重启后继续。页面刷新会开始新的本地对话，因为当前版本尚未提供会话列表和历史会话恢复界面。

## 常用开发命令

### 后端测试

```powershell
Set-Location apps/server
.\.venv\Scripts\python.exe -m pytest -q
```

### 数据库迁移

```powershell
Set-Location apps/server
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 前端生产构建

在仓库根目录执行：

```powershell
npm run build:web
```

### 停止服务

前端和后端可在各自终端中按 `Ctrl+C` 停止。数据库可执行：

```powershell
docker compose stop postgres
```

如需移除容器和网络但保留命名数据卷，可执行 `docker compose down`。不要随意使用 `docker compose down -v`，该命令会删除本地 PostgreSQL 数据卷。

## 常见问题

### 后端启动时报数据库或 checkpoint 连接错误

先执行 `docker compose ps`，确认 PostgreSQL 健康检查通过，再核对 `.env` 中的 `DATABASE_URL` 和本机 `5432` 端口占用情况。后端会在启动时初始化 checkpoint，因此不能脱离 PostgreSQL 运行。

### 数据表不存在

进入 `apps/server` 后执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 动态网页抓取失败

确认已在后端虚拟环境中执行：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

### 前端能打开但接口请求失败

确认 FastAPI 正在 `127.0.0.1:8000` 运行，并先访问 `/health` 检查后端状态。Vite 的本地代理目标固定为该地址。

### AI 或搜索功能提示配置缺失

检查 `.env` 中对应的 LLM、Embedding 或 Web Search 配置。只排查变量是否存在和服务地址是否可达，不要在终端输出、截图或提交 API Key。

## 当前限制

- 对话消息会随 conversation 增长，当前版本不做长期记忆压缩。
- 不支持长期 Memory、跨会话用户画像和会话历史管理。
- 不支持 Streaming、Multi-Agent、Reranker 和自动保存 Web 内容。
