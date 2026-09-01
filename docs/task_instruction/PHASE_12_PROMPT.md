请执行 MVP_IMPLEMENTATION_PLAN.md 的 Phase 12，只完成 Reprocessing / Regeneration，不进入 Phase 13。

Phase 0～11 已完成并验收。开始前重新阅读实施计划、ArticleService、Fetcher/Playwright、AIService、EmbeddingService、现有 Article API、状态模型和相关测试，以仓库当前代码为准。

先运行全量测试确认基线。

【目标】

正式实现并验收：

POST /api/v1/articles/{id}/reprocess
POST /api/v1/articles/{id}/regenerate-ai
POST /api/v1/articles/{id}/regenerate-embedding

复用现有能力，不重新实现第二套抓取、AI 或 Embedding Pipeline。

核心原则：

旧有效数据必须受到保护。
新结果只有完整成功后才能替换对应旧数据。

不要进入 Phase 13 前端。

--------------------------------------------------
一、reprocess：重新提取整条 Pipeline
--------------------------------------------------

POST /api/v1/articles/{id}/reprocess

目标流程：

existing Article
→ 重新 Fetch
→ HTTP / Playwright fallback
→ 新 clean_content
→ content_hash
→ AI
→ Chunk + Embedding
→ 成功后更新 Article

要求：

1. 只能操作当前 user_id 的 Article。
2. source_url 必须有效；manual-only 且无可重新抓取 URL 的情况要明确处理。
3. 复用现有 HTTP → Playwright fallback。
4. 不创建新的 Article。
5. 不改变 Article id。
6. 不产生重复 Article。

【旧数据保护】

这是本阶段最重要要求。

重新抓取开始时，不得先清空：

- clean_content
- content_hash
- AI summary
- key_points
- tags
- chunks
- embeddings

必须先获取并验证新正文。

如果 Fetch / Clean 失败：

→ 保留全部旧有效数据
→ 记录本次失败状态/安全错误
→ 不覆盖旧 clean_content

如果新正文成功，再继续后续 Pipeline。

如果 AI 失败：

→ 保留新抓取正文是否替换，必须遵循现有实施计划的原子性设计
→ 至少不得破坏旧 AI 成功结果和旧 Embedding
→ 明确报告最终采用的事务/阶段策略

如果 Embedding 失败：

→ 不得删除旧有效 chunks/embeddings
→ 不得保存半套向量

优先采用“新结果完整准备后再原子替换”的安全策略。

【content_hash】

重新抓取成功后计算新 SHA256。

如果：

new_content_hash == old_content_hash

不要无意义重复调用 AI / Embedding。

按照实施计划处理“正文未变化”的情况。

如果现有 API 不适合交互式确认，V1 可以：

- 返回明确的 content_unchanged 状态/消息
- 默认跳过 AI/Embedding

不要为了 Phase 12 引入复杂确认流程。

如果实施计划已有明确约定，以计划为准。

--------------------------------------------------
二、regenerate-ai
--------------------------------------------------

POST /api/v1/articles/{id}/regenerate-ai

目标：

使用当前已经保存的 clean_content：

clean_content
→ LLM
→ 新 summary / key_points / tags

要求：

- 不重新 Fetch
- 不修改 clean_content
- 不修改 content_hash
- 不重新生成 Embedding
- 不修改现有 chunks/vectors
- 只能操作当前 user_id
- clean_content 无效时拒绝执行

【原子替换】

调用 LLM 前不得删除旧：

- one_sentence_summary
- detailed_summary
- key_points
- tags

新 AI 结果必须：

生成
→ Schema 校验
→ 完整成功
→ 同一事务替换 AI fields + tags

如果 LLM/API/Schema/DB 失败：

→ 保留旧 AI 结果和旧 tags
→ ai_status=failed
→ ai_error=安全错误
→ overall status 根据现有状态规则正确计算

特别注意：

regenerate-ai 成功后，不应把原本已经 completed 的 embedding 无理由标记 pending/failed。

因为正文没有变化，旧 embedding 仍然有效。

--------------------------------------------------
三、regenerate-embedding
--------------------------------------------------

POST /api/v1/articles/{id}/regenerate-embedding

目标：

使用当前 clean_content：

clean_content
→ Token Chunking
→ text-embedding-v4
→ 新 chunks/vectors
→ 原子替换旧 chunks

要求：

- 不重新 Fetch
- 不调用 LLM
- 不修改 clean_content/content_hash
- 不修改 AI summary/key_points/tags
- 只能操作当前 user_id
- clean_content 无效时拒绝

必须复用 Phase 8：

EmbeddingService
TokenChunker
EmbeddingClient

【原子替换】

继续遵循 Phase 8 已实现策略：

新 chunks
→ 所有 Embeddings 完整成功
→ 全部校验通过
→ transaction
→ 删除旧 chunks
→ 插入新 chunks
→ commit

任何失败：

→ 保留旧 chunks/vectors
→ 不保存半套结果
→ embedding_status=failed
→ embedding_error=安全错误

--------------------------------------------------
四、状态一致性
--------------------------------------------------

统一检查：

status
fetch_status
ai_status
embedding_status

以及：

fetch_error
ai_error
embedding_error

三个 endpoint 开始、成功、失败后的状态必须有明确规则。

重点覆盖：

1. completed Article → regenerate-ai → success
2. completed Article → regenerate-ai → failure
3. completed Article → regenerate-embedding → success
4. completed Article → regenerate-embedding → failure
5. completed Article → reprocess → fetch failure
6. completed Article → reprocess → AI failure
7. completed Article → reprocess → embedding failure
8. partial_failed Article → 对失败阶段重新生成 → 恢复 completed

不要出现类似：

AI regeneration 成功
但 embedding 明明有效却被错误改成 pending

这种状态污染。

如果现有 overall status 计算逻辑分散，允许做小范围重构统一计算，但不要扩大 Phase 12 范围。

--------------------------------------------------
五、并发与重复请求
--------------------------------------------------

V1 不要求 Redis / 分布式锁。

但至少考虑：

- processing 状态下再次点击 regenerate/reprocess
- 连续重复请求
- 数据库唯一约束
- 不产生重复 chunks/tags

采用简单可靠方案即可。

如果 V1 暂时选择 processing 时返回 409，请明确实现并测试。

不要引入复杂任务系统。

--------------------------------------------------
六、API Response
--------------------------------------------------

继续使用统一：

{
  "code": ...,
  "message": "...",
  "data": ...
}

成功后返回足够的 Article 状态信息。

失败使用现有统一异常体系。

404：
Article 不存在 / 不属于当前 user_id。

409：
例如当前正在 processing、无法安全重复执行等业务冲突。

不要暴露：

- API Key
- Authorization
- traceback
- Provider 原始敏感错误

--------------------------------------------------
七、只修改对应阶段
--------------------------------------------------

必须测试三个 Endpoint 的副作用边界：

reprocess：
可以重新 Fetch + AI + Embedding。

regenerate-ai：
只能更新 AI fields/tags/status，
不能修改正文/hash/chunks/vectors。

regenerate-embedding：
只能更新 chunks/vectors/status，
不能修改正文/hash/AI/tags。

--------------------------------------------------
八、自动化测试
--------------------------------------------------

外部 Fetch / LLM / Embedding 使用 Mock。

至少覆盖：

【reprocess】

- 成功完整重处理
- Article id 不变
- 新正文成功替换
- hash 更新
- AI/Embedding 更新
- Fetch 失败保留旧全部有效数据
- AI 失败保护旧 AI/Embedding
- Embedding 失败保护旧 chunks
- content_hash 未变化处理
- partial_failed 恢复 completed
- user_id 隔离

【regenerate-ai】

- 成功
- 不调用 Fetch
- 不调用 Embedding
- clean_content/hash 不变
- chunks/vectors 不变
- AI/tags 原子替换
- LLM 失败保留旧 AI/tags
- 状态正确

【regenerate-embedding】

- 成功
- 不调用 Fetch
- 不调用 LLM
- clean_content/hash 不变
- AI/tags 不变
- chunks/vectors 原子替换
- Embedding 失败保留旧 chunks
- 不保存半套 vector
- 状态正确

【通用】

- processing 重复请求处理
- 404
- 错误安全
- Phase 9 Keyword Search 正常
- Phase 10 Semantic Search 正常
- Phase 11 RAG 正常
- Phase 0～11 全量回归

--------------------------------------------------
九、真实 API + PostgreSQL 验收
--------------------------------------------------

使用真实：

HTTP Fetch / Playwright（适合时）
qwen3.7-plus-2026-05-26
text-embedding-v4
PostgreSQL / pgvector

至少真实验证：

A. regenerate-ai

已有 completed Article
→ regenerate-ai
→ LLM 成功
→ AI fields/tags 更新
→ clean_content/hash/chunks/vector 不变

B. regenerate-embedding

已有 completed Article
→ regenerate-embedding
→ text-embedding-v4 成功
→ chunks/vector 原子更新
→ clean_content/hash/AI/tags 不变

C. reprocess

已有 Article
→ reprocess
→ Fetch
→ AI
→ Embedding
→ Article id 不变
→ 最终 completed

如果测试 URL 正文未变化，应验证 content_hash unchanged 分支，不要为了测试人为篡改生产逻辑。

【失败保护】

至少通过 Mock/受控方式验证：

旧数据有效
→ 新处理失败
→ 旧有效数据仍存在

不要故意破坏真实 API Key 或生产配置制造失败。

验收完成后清理临时 Article/chunks/tags/relations。

--------------------------------------------------
十、工程检查
--------------------------------------------------

原则上：

- 不新增依赖
- 不修改数据库结构
- 不新增 migration

如果现有结构确实无法安全实现，先说明原因，不要擅自扩大架构。

最终执行：

- 全量 pytest
- pip check
- alembic current
- alembic check
- git diff --check

--------------------------------------------------
【禁止】
--------------------------------------------------

本阶段不要实现：

- Phase 13 React UI
- BackgroundTasks
- Redis / Celery
- Queue
- WebSocket / SSE
- 定时任务
- Agent
- LangChain / LangGraph
- Conversation History
- 新搜索方案
- HNSW
- 登录系统

不要进入 Phase 13。

--------------------------------------------------
【完成报告】
--------------------------------------------------

完成后停止并报告：

- 修改/新增文件
- 三个 Endpoint
- Service 复用/重构情况
- reprocess 完整流程
- content_hash unchanged 策略
- regenerate-ai 副作用边界
- regenerate-embedding 副作用边界
- 旧数据保护 / 原子替换策略
- 三类状态流转
- processing/重复请求策略
- user_id 隔离
- 错误处理
- 自动化测试及 Phase 0～11 回归
- 真实 regenerate-ai 验收
- 真实 regenerate-embedding 验收
- 真实 reprocess 验收
- 失败保护验证
- 是否新增依赖
- 是否修改数据库/migration
- pip / Alembic / git diff
- Phase 12 checklist
- 明确说明未进入 Phase 13

完成后停止，等待人工验收。
