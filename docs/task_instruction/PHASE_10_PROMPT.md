请执行 MVP_IMPLEMENTATION_PLAN.md 的 Phase 10，只完成 Semantic Search，不进入 Phase 11。

Phase 0～9 已完成并验收。当前会话可能经过上下文压缩，因此不要只依赖历史对话；开始前重新阅读实施计划及现有 SearchService、EmbeddingService、EmbeddingClient、ArticleChunk Model 和相关测试，以仓库当前代码为准。

先运行全量测试确认基线。

【目标】

实现：

POST /api/v1/search/semantic

流程：

query
→ 百炼 text-embedding-v4
→ 1024维 query vector
→ PostgreSQL / pgvector
→ article_chunks.embedding 相似度检索
→ 返回相关 Article / Chunk

本阶段只做语义搜索。

可以调用 Embedding API，但禁止调用 LLM，不生成回答，不实现 RAG。

【请求】

建议：

POST /api/v1/search/semantic

{
  "query": "如何提高知识处理系统的可靠性？",
  "top_k": 3
}

query：
- trim 后不能为空
- 设置合理最大长度
- 只用于生成 query embedding

top_k 默认使用现有：

RAG_TOP_K=3

限制合理范围，避免无限查询。

【Embedding】

必须复用 Phase 8 已有：

EmbeddingService / OpenAICompatibleEmbeddingClient

使用：

EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024

要求：

- query embedding 必须真实为 1024 维
- 配置/API/网络/401/429/5xx/维度错误继续使用现有安全错误体系
- 不重复实现第二套 Embedding Client
- 不修改 Article 或 article_chunks

【pgvector 检索】

使用 PostgreSQL + pgvector 对：

article_chunks.embedding

执行 cosine distance / cosine similarity 检索。

优先使用 pgvector + SQLAlchemy 官方/现有项目兼容写法，不手写不安全 SQL。

明确 distance 与 similarity 的转换，例如：

similarity = 1 - cosine_distance

返回给 API 的 score 语义必须统一：
越大表示越相关。

【阈值】

使用现有配置：

RAG_SIMILARITY_THRESHOLD=0.35

只返回达到阈值的结果。

阈值逻辑必须与 score 定义一致。

如果没有达到阈值的结果：

正常返回 200 + 空列表，
不是系统错误。

【用户隔离】

只能检索当前 user_id 的数据。

Article 必须满足合理的可搜索条件，例如：

embedding_status=completed

不能返回其他用户的 chunks。

【Chunk 与 Article】

Semantic Search 的检索单位是 chunk。

返回结果至少包含：

- article_id
- title
- chunk_id
- chunk_index
- excerpt/content
- score

可附带：
- one_sentence_summary
- source_url
- source_name
- tags

不要返回完整 clean_content。

同一 Article 可能多个 chunk 命中。

V1 优先保留最相关 chunk，并避免同一 Article 大量占满 top_k。

推荐：

1. 先获取足够候选 chunk
2. 按 similarity 从高到低
3. 同一 Article 只保留最高分 chunk
4. 最终返回 top_k 个 Article 结果

如果现有实施计划明确规定其他策略，以计划为准，并在报告中说明。

排序：

score DESC
→ 稳定次序作为 tie-breaker。

【Service】

保持清晰边界：

Search Router
→ SearchService
→ EmbeddingService
→ Embedding Client

以及：

SearchService
→ PostgreSQL / pgvector

Router 不写向量计算、SQL 或业务逻辑。

Phase 9 Keyword Search 保持不变。

【只读】

Semantic Search 除远程生成 query embedding 外必须是只读操作。

禁止：

- 保存 query embedding
- 新建 article_chunks
- 重新生成 Article embedding
- 修改 Article 状态
- 修改 clean_content
- 修改 AI 摘要/标签

【错误处理】

覆盖：

- query 为空
- Embedding 配置缺失
- Embedding API timeout/network
- 401/429/5xx
- query vector 维度错误
- pgvector 查询异常

对外错误不能包含：

- API Key
- Authorization
- traceback
- 数据库敏感信息

“没有相似内容”不是异常。

【自动化测试】

Mock Embedding API，不依赖公网。

至少覆盖：

- query → embedding → pgvector 查询
- 1024 维 query vector
- cosine similarity / score 计算正确
- threshold 生效
- score 越大越相关
- top_k
- score DESC
- 同 Article 多 chunk 去重，只保留最高分
- user_id 隔离
- 只检索合法 embedding Article
- 无命中返回空结果
- query 空/纯空白
- Embedding 失败安全处理
- 搜索只读
- 不调用 LLM
- Phase 9 Keyword Search 不受影响
- Phase 0～9 全量回归

【真实百炼 + PostgreSQL 验收】

使用真实：

text-embedding-v4
+
PostgreSQL / pgvector

准备几篇语义明显不同的临时 Article/chunks。

执行：

自然语言 query
→ 真实 query embedding
→ pgvector cosine search
→ Semantic Search API

确认：

- 百炼 query embedding 调用成功
- query vector = 1024维
- 能召回语义相关内容
- 明显无关内容排序更低或被 threshold 排除
- score 排序正确
- user_id 隔离正确
- top_k 正确
- 同 Article 不重复占结果
- 不调用 LLM
- 不修改 Article/chunks/status

不要为了验收人为伪造“真实相似度结果”。

记录实际 score 和返回顺序，但不得输出 API Key。

验收后清理临时数据。

【依赖 / DB / 回归】

原则上：

- 不新增依赖
- 不修改数据库结构
- 不新增 migration
- 暂不新增 HNSW 索引

执行：

- 全量 pytest
- pip check
- alembic current
- alembic check
- git diff --check

【禁止】

不要实现：

- RAG
- LLM Answer
- /ask
- Prompt 拼接
- citations generation
- conversation history
- HNSW
- Hybrid Search
- Elasticsearch / Meilisearch
- LangChain / LangGraph
- BackgroundTasks
- 前端
- Phase 11

【完成报告】

完成后停止并报告：

- 修改/新增文件
- Semantic Search API
- Service 调用结构
- query embedding 复用方式
- pgvector cosine 查询实现
- distance / similarity / score 定义
- threshold 策略
- top_k 策略
- 同 Article 多 chunk 去重策略
- user_id 隔离
- 返回 Schema
- 错误处理
- 自动化测试和 Phase 0～9 回归
- 真实百炼 + PostgreSQL 验证
- 实际 query vector 维度
- 实际返回 score / 顺序
- 是否调用 LLM
- 是否修改任何 Article/chunk/status
- pip / Alembic / git diff
- 是否修改数据库结构
- Phase 10 checklist
- 明确说明未进入 Phase 11

完成后停止，等待人工验收。