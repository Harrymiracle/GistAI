# GistAI

AI 阅读助手 MVP。

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
`thread_id`，同一页面内的后续请求复用该值。当前 checkpoint 仍保存在服务进程内存中，
因此刷新页面会开始新对话，服务重启后已有对话上下文也会丢失。

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
