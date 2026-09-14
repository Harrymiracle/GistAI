# GistAI

AI 阅读助手 MVP。

## 架构

```text
文章导入与清洗 → AI 摘要 / 标签 → Chunk / Embedding → PostgreSQL + pgvector
                                                    ↓
React Chat → Agent API → 检索 / 全文读取 / 证据评估 → 有来源的回答
                         ↓
                 PostgreSQL Checkpoint
```

普通 RAG 提供单轮知识库问答；Agent 在固定预算和运行策略内支持知识库检索、一次查询改写、
受控 Web Search、知识库与网页全文读取、证据评估以及 Partial / Insufficient 安全结束。

## 目录结构

```text
.
├── apps/
│   ├── web/       # React + TypeScript 前端
│   └── server/    # FastAPI 后端
├── docs/          # 实施计划
├── infra/         # 基础设施相关文件
├── docker-compose.yml
└── .env.example
```

## 本地启动

### 前端

```powershell
npm install --registry=https://registry.npmmirror.com
npm run dev:web
```

访问 `http://localhost:5173`。开发服务器会将 `/health` 和 `/api` 代理到 FastAPI。

AI 助手页面位于 `/agent`，调用 `POST /api/v1/agent/chat`。首次请求由后端生成
`thread_id`，同一页面内的后续请求复用该值。服务端使用 `user_id:thread_id` 隔离用户，
并通过 PostgreSQL Checkpointer 在服务重启后恢复同一 conversation。页面刷新仍会开始
一个新的本地对话，因为 V1 尚未提供历史会话管理界面。

### 后端

```powershell
cd apps/server
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Playwright 浏览器安装在本机用户缓存中，不会写入 Git 仓库。

访问 `http://127.0.0.1:8000/health`。

### PostgreSQL + pgvector

```powershell
docker compose up -d postgres
```

复制 `.env.example` 为本地 `.env` 后再填写真实配置；不要提交 `.env` 或任何密钥。
应用启动时会使用同一个 PostgreSQL 实例初始化 LangGraph 官方 checkpoint 表；这些表由
Checkpointer 自身的 `setup()` 管理，不纳入业务 Alembic migration。多进程首次启动时，
初始化过程使用 PostgreSQL advisory lock 串行执行，运行期连接池由应用生命周期统一关闭。

## 当前限制

- 对话消息会随 conversation 增长，V1 不做长期记忆压缩。
- 不支持长期 Memory、跨会话用户画像和会话历史管理。
- 不支持 Streaming、Multi-Agent、Reranker 和自动保存 Web 内容。
