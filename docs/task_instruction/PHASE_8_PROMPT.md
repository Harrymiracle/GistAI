请执行 MVP_IMPLEMENTATION_PLAN.md 的 Phase 8，只完成 Chunk + Embedding，不进入 Phase 9。

Phase 0～7 已完成并验收。开始前阅读实施计划、Article/AI Service、article_chunks Model 和现有状态逻辑，并运行全量测试确认基线。

【目标】

实现：

clean_content
→ Token Chunking
→ article_chunks
→ 百炼 text-embedding-v4
→ 1024 维向量
→ PostgreSQL + pgvector

为后续 Keyword Search、Semantic Search 和 RAG 准备数据。

【配置】

使用既定环境变量：

EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024

RAG_CHUNK_SIZE=400
RAG_CHUNK_OVERLAP=80

如果现有配置命名略有不同，遵循项目现状并保持一致。

Embedding 配置不得硬编码。
真实 API Key 只从本机 .env 读取，不得输出、记录或提交 Git。

【Chunk】

仅处理已有有效 clean_content 的 Article。

按 token 切块，不按字符简单截断：

chunk_size = 400 tokens
overlap = 80 tokens

要求：

- 保持原文顺序
- chunk_index 从 0 连续递增
- 尽量避免空 chunk
- 最后一块允许不足 400 tokens
- 短文章也至少产生一个有效 chunk
- token_count 保存实际 token 数
- chunk content 保存到 article_chunks.content

如果需要 tokenizer，选择与当前模型场景兼容、轻量且可维护的方案，并在报告中说明。

不要引入 LangChain/LangGraph 只为了切块。

【Embedding Client】

保持轻量分层，例如：

ArticleService
→ EmbeddingService
   ├→ Chunker
   └→ EmbeddingClient
        ↓
百炼 OpenAI-compatible Embedding API

Embedding Client 只负责模型调用和错误转换。

优先批量请求多个 chunk，避免无必要地逐 chunk 调 API；同时考虑 API 单次输入限制，使用合理 batch。

必须验证返回：
- 数量与输入 chunk 一致
- 每个 embedding 恰好 1024 维
- 顺序与输入 chunk 一致

异常结果不得写入半套向量数据。

【持久化】

使用现有 article_chunks：

- article_id
- chunk_index
- content
- token_count
- embedding VECTOR(1024)
- metadata

成功后该 Article 的 chunks 和 embedding 必须完整可读取。

同一 Article 重新生成时：
- 不产生重复 chunk_index
- 新 chunks + embeddings 全部准备成功后，再安全替换旧 chunks
- 新生成失败时尽量保留旧的有效 chunks/embeddings
- 不允许先删除旧数据再调用远程 Embedding API

保证 `(article_id, chunk_index)` 唯一约束。

【状态】

只有：

fetch_status=completed
ai_status=completed
clean_content 有效

时才进入本阶段 Embedding。

开始：

embedding_status=processing
status=processing
embedding_error=null

成功：

embedding_status=completed
embedding_error=null
status=completed

因为此时 fetch + AI + embedding 均完成。

失败：

embedding_status=failed
embedding_error=安全、明确的错误
status=partial_failed

失败时不得破坏：
- clean_content
- content_hash
- AI 摘要
- tags
- 已有有效 chunks/embeddings（如果属于重新生成场景）

【Pipeline】

继续使用当前同步 pipeline，不实现 BackgroundTasks。

Article：

抓取/手动正文成功
→ AI
→ AI 成功
→ Chunk + Embedding

AI 失败时不要执行 Embedding。

如果实施计划将 regenerate-embedding 放在 Phase 12，则本阶段不要提前实现该 API。

【错误处理】

至少覆盖：

- Embedding 配置缺失
- timeout / 网络异常
- 401 / 429 / 5xx
- 空响应
- 返回数量错误
- embedding 维度不是 1024
- 非法向量数据

不得暴露 API Key、Authorization、traceback 等敏感信息。

【测试】

自动化测试必须 Mock Embedding API，不消耗真实 Token。

至少覆盖：

- token chunking
- 400 / overlap 80 行为
- 短文章
- chunk_index
- token_count
- 多 chunk 顺序
- Embedding 1024 维
- chunks + vectors 正确持久化
- 成功后 embedding_status=completed、status=completed
- AI 失败时不执行 Embedding
- Embedding 失败 → partial_failed
- Embedding 失败不破坏正文/摘要/tags
- 返回数量错误
- 返回维度错误
- 重新生成安全替换逻辑（如果本阶段内部流程支持）
- Phase 0～7 全量回归

【真实百炼验证】

Mock 测试通过后，用本机 .env 做一次真实：

Article
→ clean_content
→ AI
→ Chunk
→ text-embedding-v4
→ VECTOR(1024)
→ PostgreSQL

确认：

- article_chunks 实际生成
- chunk_index/token_count/content 正确
- embedding 实际为 1024 维
- embedding_status=completed
- embedding_error=null
- status=completed
- 原 clean_content/content_hash/AI 结果/tags 正常

独立从 PostgreSQL 二次读取验证。

如果 Embedding 配置缺失，只报告缺少哪些变量，不猜 API Key/Base URL。

验收数据完成后清理。

【依赖与数据库】

优先复用现有 OpenAI-compatible SDK。

原则上不修改数据库结构，因为 article_chunks 和 VECTOR(1024) 已在 Phase 1 建立。

确需修改只能新增 Alembic migration，不修改历史 migration。

执行：

- 全量 pytest
- pip check
- alembic current
- alembic check
- git diff --check

【禁止】

本阶段不要实现：

- Keyword Search
- Semantic Search
- similarity threshold
- HNSW
- RAG
- Agent
- LangChain/LangGraph
- BackgroundTasks
- Redis/Celery
- 前端
- 登录系统

不要进入 Phase 9。

【完成报告】

完成后停止并报告：

- 修改/新增文件
- Chunker / Embedding Service / Client 设计
- tokenizer 方案
- 400/80 切块实现
- Embedding batch 策略
- 1024 维校验
- chunks/vector 持久化与安全替换策略
- 状态流转和错误处理
- 自动化测试及 Phase 0～7 回归
- 真实百炼 text-embedding-v4 验证
- 实际 chunk 数、token_count、向量维度
- pip / Alembic / git diff 状态
- 是否修改数据库
- Phase 8 checklist
- 明确说明未进入 Phase 9

完成后停止，等待人工验收。