# GistAI

AI 阅读助手 MVP。当前仅完成 Phase 0 项目初始化。

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

访问 `http://localhost:5173`。开发服务器会将 `/health` 代理到 FastAPI。

### 后端

```powershell
cd apps/server
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

访问 `http://127.0.0.1:8000/health`。

### PostgreSQL + pgvector

```powershell
docker compose up -d postgres
```

复制 `.env.example` 为本地 `.env` 后再填写真实配置；不要提交 `.env` 或任何密钥。
