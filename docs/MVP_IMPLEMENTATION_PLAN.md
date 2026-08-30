# AI 阅读助手 MVP 实施计划

## 1. 项目目标

构建一个个人使用的 AI 阅读助手 Web MVP，核心解决：

- 信息量过大
- 文章口水话多
- 内容重复
- 阅读成本高
- 历史内容难以再次检索和利用

第一版用户为单用户，不做登录，但后端和数据库预留 `user_id`，为后续 Web + App 共用同一套后端做准备。

---

## 2. MVP 核心流程

```text
用户粘贴 URL
↓
校验 URL
↓
检查是否已经保存
↓
普通 HTTP 抓取
↓失败
Playwright 浏览器渲染抓取
↓失败
用户手动粘贴正文
↓
正文清洗
↓
保存 clean_content
↓
AI 生成：
- 一句话总结
- 核心观点
- 详细摘要
- 标签
↓
文章切片
↓
Embedding
↓
pgvector 保存
↓
关键词搜索
↓
语义搜索
↓
基于文章库的 RAG 问答
```

---

## 3. V1 功能范围

### 必须实现

- 手动添加文章 URL
- URL 格式校验
- URL 重复检测
- 普通网页抓取
- Playwright 抓取兜底
- 手动粘贴正文兜底
- 正文清洗
- 保存清洗后的完整正文
- AI 一句话总结
- AI 核心观点
- AI 详细摘要
- AI 自动标签
- 收藏
- 文章列表
- 文章详情
- 标签筛选
- 收藏筛选
- 来源筛选
- 状态筛选
- 普通关键词搜索
- 文章切片
- Embedding
- pgvector
- 语义搜索
- 基础 RAG 问答
- RAG 引用来源
- 处理状态展示
- 失败重试
- 重新提取
- 重新生成 AI 内容
- 重新生成 Embedding
- Docker Compose 本地开发
- Git / GitHub 托管
- 后续支持免费或低成本公网部署

### V1 暂不实现

- 登录 / 注册
- OAuth
- 多用户正式体系
- RSS 自动订阅
- n8n
- 自动监控公众号更新
- 批量抓公众号历史文章
- Agent
- GraphRAG
- 知识图谱
- 多路召回
- rerank
- HyDE
- Query Rewrite
- Redis
- Celery
- Kafka
- RabbitMQ
- Elasticsearch
- 独立向量数据库
- 多轮聊天记录
- App
- 推荐算法
- 文章历史版本
- 原始 HTML 长期存储
- 自定义域名作为 V1 必选项

---

# 4. 技术栈

## 4.1 前端

- React
- TypeScript
- React Router
- TanStack Query
- axios
- axios 基础请求封装
- 业务 API 二次封装
- shadcn/ui
- Tailwind CSS
- ui-ux-pro-max-skill 用于 UI / UX 设计辅助

建议结构：

```text
apps/web/src/
├── api/
│   ├── request.ts
│   ├── article.ts
│   ├── tag.ts
│   ├── search.ts
│   └── rag.ts
├── components/
├── pages/
├── hooks/
├── types/
├── utils/
└── router/
```

---

## 4.2 后端

- Python
- FastAPI
- SQLAlchemy 2.x
- Pydantic
- Pydantic Settings
- Alembic
- PostgreSQL
- pgvector
- httpx
- BeautifulSoup / 正文提取库
- Playwright
- Docker

后端采用单体应用，但内部模块化。

```text
apps/server/app/
├── api/
├── models/
├── schemas/
├── services/
├── repositories/
├── crawler/
├── ai/
├── rag/
├── core/
└── db/
```

---

## 4.3 项目结构

采用 Monorepo。

```text
ai-reading-assistant/
├── apps/
│   ├── web/
│   └── server/
├── docs/
│   └── MVP_IMPLEMENTATION_PLAN.md
├── infra/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

第一版不引入 Turborepo，保持简单。

---

# 5. AI 模型方案

## 5.1 接口规范

统一采用 OpenAI-compatible API。

所有模型配置通过环境变量读取，禁止在业务代码中写死 API Key、Base URL、模型名称。

推荐配置：

```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=

EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024
```

---

## 5.2 Embedding

采用：

```text
阿里云百炼
text-embedding-v4
dimension = 1024
```

数据库：

```text
VECTOR(1024)
```

---

## 5.3 LLM 输出结构

每篇文章固定生成：

```json
{
  "one_sentence_summary": "一句话总结",
  "key_points": [
    "核心观点 1",
    "核心观点 2",
    "核心观点 3"
  ],
  "detailed_summary": "详细摘要",
  "tags": [
    "AI",
    "RAG"
  ]
}
```

Prompt 必须要求模型返回结构化 JSON。

后端必须校验模型返回结构，不可信任模型原始返回值。

---

# 6. RAG 参数

初始配置：

```env
RAG_CHUNK_SIZE=400
RAG_CHUNK_OVERLAP=80
RAG_TOP_K=3
RAG_SIMILARITY_THRESHOLD=0.35
```

注意：

- `chunk_size` 单位为 token
- `overlap` 单位为 token
- 相似度阈值 `0.35` 是初始实验值，必须允许通过配置调整
- RAG 只基于召回内容回答
- 没有足够相关内容时必须拒答
- 不允许模型使用外部知识自由补充答案

---

# 7. 数据库设计

## 7.1 articles

```text
id                  BIGINT PK
user_id             BIGINT NOT NULL DEFAULT 1

source_type         VARCHAR(32) NOT NULL
source_url          TEXT NOT NULL
source_name         VARCHAR(255)

title               TEXT
author              VARCHAR(255)
published_at        TIMESTAMPTZ

clean_content       TEXT
content_hash        CHAR(64)

one_sentence_summary TEXT
detailed_summary    TEXT
key_points          JSONB

favorite            BOOLEAN NOT NULL DEFAULT false

status              VARCHAR(32) NOT NULL DEFAULT 'pending'
fetch_status        VARCHAR(32) NOT NULL DEFAULT 'pending'
ai_status           VARCHAR(32) NOT NULL DEFAULT 'pending'
embedding_status    VARCHAR(32) NOT NULL DEFAULT 'pending'

fetch_error         TEXT
ai_error            TEXT
embedding_error     TEXT

created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

唯一约束：

```text
UNIQUE(user_id, source_url)
```

说明：

- `clean_content` 必须保存
- V1 不保存 raw_html
- `content_hash` 使用 SHA256
- 同一 URL 重新提取时更新原文章，不新建重复文章

---

## 7.2 tags

```text
id          BIGINT PK
user_id     BIGINT NOT NULL DEFAULT 1
name        VARCHAR(100) NOT NULL
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
```

唯一约束：

```text
UNIQUE(user_id, name)
```

---

## 7.3 article_tags

```text
article_id  BIGINT FK -> articles.id
tag_id      BIGINT FK -> tags.id
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
```

组合主键：

```text
PRIMARY KEY(article_id, tag_id)
```

删除文章时：

```text
ON DELETE CASCADE
```

删除标签时，仅删除对应关联关系，不删除文章。

---

## 7.4 article_chunks

```text
id           BIGINT PK
article_id   BIGINT FK -> articles.id
chunk_index  INTEGER NOT NULL
content      TEXT NOT NULL
token_count  INTEGER
embedding    VECTOR(1024)
metadata     JSONB
created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
```

建议约束：

```text
UNIQUE(article_id, chunk_index)
```

删除文章时：

```text
ON DELETE CASCADE
```

---

# 8. 状态设计

## 8.1 子状态

统一：

```text
pending
processing
completed
failed
```

字段：

```text
fetch_status
ai_status
embedding_status
```

---

## 8.2 总状态

```text
pending
processing
completed
partial_failed
failed
```

原则：

- 抓取失败且没有有效正文：`failed`
- 正文已经可用，但 AI 或 Embedding 某一步失败：`partial_failed`
- 所有主要处理完成：`completed`

---

# 9. 抓取策略

## 9.1 三层策略

```text
第一层
普通 HTTP 抓取

↓失败

第二层
Playwright 浏览器渲染抓取

↓失败

第三层
用户手动粘贴正文
```

公众号文章允许进入 Playwright 兜底。

V1 目标是：

- 尽量支持单篇微信公众号 URL
- 不承诺稳定自动抓取公众号全部历史文章
- 不做公众号自动监控

---

## 9.2 Crawler 模块

```text
crawler/
├── http_fetcher.py
├── browser_fetcher.py
├── extractor.py
├── cleaner.py
└── service.py
```

Crawler 只负责最终产出可用正文。

AI Pipeline 不关心正文来自：

- HTTP
- Playwright
- 用户粘贴

AI 只消费 `clean_content`。

---

# 10. 关键异常处理

| 场景 | V1 处理方式 |
|---|---|
| URL 格式错误 | 前端提示，后端拒绝 |
| URL 已存在 | 返回已有文章，用户选择查看已有内容或重新提取 |
| 网页访问失败 | `fetch_status=failed`，记录 `fetch_error`，允许重试 |
| 提取不到正文 | 抓取失败，允许 Playwright / 手动正文兜底 |
| 正文过短 | 判定为无有效正文，提示用户手动补充 |
| AI 摘要失败 | 正文保留，`ai_status=failed`，允许重新生成 |
| Embedding 失败 | 文章继续可用，`embedding_status=failed`，允许重生成 |
| RAG 无相关内容 | 明确返回“知识库中没有足够相关内容” |
| 重新提取失败 | 保留上一次成功的 `clean_content` |

---

# 11. 重新提取规则

用户选择重新提取时：

```text
重新抓取
↓
清洗正文
↓
计算 new_content_hash
↓
与旧 content_hash 比较
```

如果正文发生变化：

```text
更新 clean_content
更新 content_hash
重新生成：
- 一句话总结
- 核心观点
- 详细摘要
- 标签

删除旧 article_chunks
重新切片
重新 Embedding
```

如果正文没有变化：

```text
提示正文未变化
↓
由用户决定是否强制重新生成 AI 内容
```

必须遵守：

> 新抓取结果未成功前，不允许覆盖旧的有效 `clean_content`。

---

# 12. API 设计

统一：

```text
/api/v1
```

---

## 12.1 Articles

```text
POST   /api/v1/articles
GET    /api/v1/articles
GET    /api/v1/articles/{id}
PATCH  /api/v1/articles/{id}
DELETE /api/v1/articles/{id}

GET    /api/v1/articles/{id}/status

POST   /api/v1/articles/{id}/manual-content
POST   /api/v1/articles/{id}/reprocess
POST   /api/v1/articles/{id}/regenerate-ai
POST   /api/v1/articles/{id}/regenerate-embedding

PUT    /api/v1/articles/{id}/tags
```

---

## 12.2 Tags

```text
GET    /api/v1/tags
POST   /api/v1/tags
PATCH  /api/v1/tags/{id}
DELETE /api/v1/tags/{id}
```

---

## 12.3 Search

```text
GET  /api/v1/search/keyword
POST /api/v1/search/semantic
```

---

## 12.4 RAG

```text
POST /api/v1/ask
```

---

# 13. API 响应规范

统一响应结构：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

同时使用标准 HTTP 状态码：

```text
200 OK
201 Created
400 Bad Request
404 Not Found
409 Conflict
422 Validation Error
500 Internal Server Error
```

业务错误使用内部 `code`。

---

# 14. 页面结构

## 14.1 首页

主要目标：

> 快速添加文章并看到最近处理结果。

内容：

```text
URL 输入框
解析文章按钮

最近添加文章

处理中任务

快捷入口：
- 文章库
- 收藏
- AI 问答
```

V1 不做复杂数据大盘。

---

## 14.2 文章库

顶部：

- 关键词搜索
- 全部 / 收藏
- 标签筛选
- 来源筛选
- 状态筛选

文章卡片展示：

- 标题
- 一句话总结
- 来源
- 发布时间
- 标签
- 收藏状态
- 处理状态

列表不返回和不直接展示完整正文。

---

## 14.3 文章详情

展示顺序：

```text
标题
来源 / 作者 / 发布时间 / 原文链接
收藏

一句话总结

核心观点

详细摘要

标签

清洗后的正文

操作：
- 重新提取
- 重新生成 AI
- 重新生成 Embedding
- 删除
```

AI 信息必须出现在全文正文之前。

---

## 14.4 AI 问答

V1 只做单轮问答。

内容：

- 问题输入
- 提问按钮
- 只搜索收藏内容开关
- 标签筛选
- AI 回答
- 引用来源
- 匹配内容摘录

暂不做：

- conversation
- messages
- 多轮上下文

---

# 15. 前端 API 封装

```text
apps/web/src/api/
├── request.ts
├── article.ts
├── tag.ts
├── search.ts
└── rag.ts
```

基础 axios：

```ts
const request = axios.create({
  baseURL: '/api/v1'
})
```

业务层调用：

```text
articleApi.create()
articleApi.list()
articleApi.detail()
articleApi.reprocess()

tagApi.list()

searchApi.keyword()
searchApi.semantic()

ragApi.ask()
```

---

# 16. 环境变量

禁止提交真实 `.env`。

需要：

```text
.env
.env.example
.gitignore
```

`.env.example` 示例：

```env
DATABASE_URL=

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=

EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024

RAG_CHUNK_SIZE=400
RAG_CHUNK_OVERLAP=80
RAG_TOP_K=3
RAG_SIMILARITY_THRESHOLD=0.35
```

`.env` 必须加入 `.gitignore`。

---

# 17. Docker Compose

本地使用 Docker Compose。

至少包含：

```text
postgres + pgvector
```

第一阶段前端和后端可以直接本地启动。

后续可以再决定是否将：

```text
web
server
```

也容器化。

---

# 18. 异步任务演进

## 第一阶段

同步跑通主链路：

```text
create article
↓
process_article(article_id)
```

所有复杂处理必须位于 Service。

禁止把：

- 抓取
- AI
- Embedding

直接写在 FastAPI Router 内。

---

## 第二阶段

主链路跑通后改：

```text
FastAPI BackgroundTasks
```

Router 只负责：

```text
创建文章记录
↓
返回 article_id
↓
后台执行 process_article(article_id)
```

核心 Service 逻辑尽量不改。

---

# 19. 开发阶段

## Phase 0：项目初始化

目标：

- Monorepo 建立
- React 项目可启动
- FastAPI 项目可启动
- Docker PostgreSQL + pgvector 可启动
- 前后端连通
- 环境变量可用

验收：

```text
GET /health
```

前端可以正常请求后端。

---

## Phase 1：数据库基础

实现：

- SQLAlchemy Models
- Alembic
- articles
- tags
- article_tags
- article_chunks
- pgvector extension

验收：

- migration 可执行
- migration 可回滚
- 表结构正确
- 唯一约束正确
- 外键和 cascade 正确

---

## Phase 2：基础文章 CRUD

实现：

- 创建 URL Article
- URL 校验
- URL 去重
- Article 列表
- Article 详情
- 收藏
- 删除

验收：

```text
POST /articles
GET /articles
GET /articles/{id}
PATCH /articles/{id}
DELETE /articles/{id}
```

均正常工作。

---

## Phase 3：普通网页抓取

实现：

- httpx Fetcher
- 正文提取
- 正文清洗
- clean_content 保存
- content_hash
- fetch status
- fetch error

验收：

输入普通文章 URL：

```text
URL
→ 正文
→ clean_content
→ DB
```

成功。

---

## Phase 4：Playwright 抓取

实现：

- 普通抓取失败自动进入 Playwright
- 浏览器资源正确关闭
- 超时处理
- 微信公众号单篇 URL 尝试支持

验收：

至少准备：

- 普通网页
- 动态网页
- 微信公众号文章

三类测试 URL。

---

## Phase 5：手动正文兜底

实现：

```text
POST /articles/{id}/manual-content
```

验收：

抓取失败后，用户粘贴正文仍可以继续进入 AI Pipeline。

---

## Phase 6：AI 摘要和标签

实现：

- OpenAI-compatible Client
- 配置化 Base URL / Key / Model
- Prompt
- JSON 结构校验
- 一句话总结
- 核心观点
- 详细摘要
- 标签
- AI 状态
- AI 错误处理

验收：

任意有效 `clean_content` 可以稳定得到结构化结果。

---

## Phase 7：标签系统

实现：

- 自动创建不存在的标签
- article_tags
- 标签列表
- 手动创建标签
- 修改标签
- 删除标签
- 修改文章标签

验收：

文章可以按标签筛选。

---

## Phase 8：Chunk + Embedding

实现：

- token-based chunk
- chunk size 400
- overlap 80
- text-embedding-v4
- 1024 维
- article_chunks
- embedding 状态
- embedding 错误处理

验收：

有效文章可以生成 chunks 和 embedding。

---

## Phase 9：关键词搜索

实现：

```text
GET /search/keyword
```

至少检索：

- title
- one_sentence_summary
- detailed_summary
- clean_content

V1 不上 Elasticsearch。

---

## Phase 10：语义搜索

实现：

```text
POST /search/semantic
```

流程：

```text
query
↓
query embedding
↓
pgvector
↓
top_k
↓
article 聚合
```

验收：

语义相近但关键词不同的问题，能够找到相关历史文章。

---

## Phase 11：基础 RAG

实现：

```text
POST /ask
```

支持：

- top_k = 3
- similarity threshold
- favorite_only
- tag_ids
- 只基于召回结果回答
- 无相关内容时拒答
- 返回引用来源

验收：

返回：

```json
{
  "answer": "...",
  "sources": [...]
}
```

每个 source 至少包含：

- article_id
- title
- chunk_id
- excerpt

---

## Phase 12：重新处理

实现：

- reprocess
- regenerate-ai
- regenerate-embedding
- content_hash 比较
- 失败时保留旧正文

验收：

可以独立重试不同处理阶段。

---

## Phase 13：React UI

完成：

- 首页
- 文章库
- 文章详情
- AI 问答
- Loading
- Empty
- Error
- Processing
- Partial Failed

使用：

```text
ui-ux-pro-max-skill
+
shadcn/ui
+
Tailwind CSS
```

重点是阅读体验，不做传统后台管理系统风格。

---

## Phase 14：异步化

同步链路稳定后，再切：

```text
BackgroundTasks
```

实现：

```text
POST /articles
↓
尽快返回 article_id
↓
后台继续处理
```

前端：

```text
GET /articles/{id}/status
```

轮询处理进度。

V1 暂不使用 WebSocket / SSE。

---

## Phase 15：Docker / README / GitHub

实现：

- docker-compose
- `.env.example`
- README
- 初始化脚本
- 开发启动说明
- 数据库 migration 说明
- GitHub repository

确认真实 `.env` 未进入 Git。

---

## Phase 16：公网部署

目标：

- 使用免费或低成本平台
- 暂不要求购买域名
- 优先平台默认公网地址
- GitHub 代码仓库 + Online Demo

部署平台选型放到项目本地稳定之后再决定。

---

# 20. Codex 执行规则

Codex 必须遵守以下规则。

## Rule 1：严格按 Phase 顺序执行

不得跳过数据库、Crawler、AI Pipeline 等基础阶段直接做完整 UI。

---

## Rule 2：一次只执行一个 Phase

每个 Phase 完成后：

1. 总结修改内容
2. 列出新增文件
3. 列出修改文件
4. 说明执行过哪些测试
5. 汇报测试结果
6. 说明是否达到本 Phase 验收标准
7. 等待人工确认后进入下一个 Phase

---

## Rule 3：禁止擅自扩大 MVP

不得自行加入：

- Redis
- Celery
- RabbitMQ
- Kafka
- Elasticsearch
- Qdrant
- Agent
- GraphRAG
- 用户登录
- OAuth
- App
- n8n

如认为必须新增依赖或改变方案，必须先说明原因，不得直接实施。

---

## Rule 4：业务逻辑必须进 Service

Router 不允许堆积复杂逻辑。

Router 负责：

```text
参数
权限（未来）
Service 调用
Response
```

Crawler、AI、RAG、Article Processing 都必须拆 Service。

---

## Rule 5：AI Provider 必须解耦

禁止在业务代码中写死：

- 百炼
- Qwen
- text-embedding-v4
- API Key
- Base URL

必须通过 Provider / Client / Settings 封装。

---

## Rule 6：真实 Secret 不允许进入仓库

必须检查：

```text
.env
API Key
数据库密码
```

不得进入 Git。

---

## Rule 7：优先简单实现

第一版优先：

- 可运行
- 可测试
- 可理解
- 可扩展

不要过早设计复杂抽象。

---

## Rule 8：每个 Phase 必须可运行

禁止大量创建空目录、空接口、TODO 后直接宣布 Phase 完成。

---

## Rule 9：异常场景必须覆盖

关键 Service 至少测试：

- 正常成功
- URL 重复
- 抓取失败
- 正文为空
- AI 失败
- Embedding 失败

---

## Rule 10：任何重构不得破坏已通过验收的 Phase

每次进入新 Phase 前运行已有核心测试。

---

# 21. MVP 最终验收标准

最终用户应该能够：

```text
1. 打开 Web
2. 粘贴一个 URL
3. 系统抓取正文
4. 普通抓取失败时自动尝试 Playwright
5. 再失败时可以手动粘贴正文
6. 系统保存 clean_content
7. 自动生成一句话总结
8. 自动生成核心观点
9. 自动生成详细摘要
10. 自动生成标签
11. 自动切片
12. 自动生成 Embedding
13. 在文章库查看文章
14. 收藏文章
15. 按标签筛选
16. 普通关键词搜索
17. 语义搜索
18. 基于文章库提问
19. 获得带来源引用的回答
20. 失败的处理阶段可以重新执行
```

满足以上链路即视为 MVP 完成。

---

# 22. 实施原则

本项目第一版核心价值始终是：

> 降低长文章和低信息密度内容的阅读成本，并把有价值内容沉淀成可检索、可问答的个人知识库。

技术只是为产品目标服务。

开发优先级：

```text
抓取质量
>
正文质量
>
AI 摘要质量
>
数据可靠性
>
搜索
>
RAG
>
UI 美化
>
复杂架构
```

不要为了展示 AI 技术而牺牲实际阅读体验。
