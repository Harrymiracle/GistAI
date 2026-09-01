Phase 8 验收报告
Phase 8 的代码实现、Mock 验收和 Phase 0～7 回归已完成；真实百炼向量入库验收因本机 API Key 格式无效而未完成。因此目前不能严格标记 Phase 8 最终验收全部通过。
修改/新增文件
核心实现：
- [chunker.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\embedding\\chunker.py)：token 切块。
- [client.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\embedding\\client.py)：OpenAI-compatible Embedding Client。
- [service.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\embedding\\service.py)：批量向量生成。
- [schemas.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\embedding\\schemas.py)：TokenChunk、EmbeddedChunk。
- [errors.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\embedding\\errors.py)：安全异常体系。
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\article.py)：接入同步 Embedding pipeline、状态和原子替换。
- [deps.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\deps.py)：Embedding Service 依赖注入。
- [articles.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\articles.py)：创建文章及手动正文链路进入 Embedding。
- [config.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\config.py)：Embedding、batch、400/80 配置。
- [requirements.txt](E:\\practice\\projects\\GistAI\\apps\\server\\requirements.txt)：增加 tiktoken。
- [.env.example](E:\\practice\\projects\\GistAI\\.env.example)：增加非敏感示例配置。
测试：
- [test_embedding_chunker.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_embedding_chunker.py)
- [test_embedding_client.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_embedding_client.py)
- [test_embedding_pipeline.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_embedding_pipeline.py)
- 更新既有测试和 [conftest.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\conftest.py)，统一使用 Mock Embedding。
设计
调用结构：
ArticleService
→ EmbeddingService
├─ TokenChunker
└─ OpenAICompatibleEmbeddingClient
→ PostgreSQL / pgvector
- Router 不包含切块、远程调用或持久化业务。
- Embedding Client 只负责 OpenAI-compatible API 调用、结果校验和安全错误转换。
- Embedding Service 负责切块和 batch。
- ArticleService 负责前置状态、状态流转及数据库原子替换。
- 未引入 LangChain、LangGraph。
Tokenizer 与 400/80 切块
采用 tiktoken 0.14.0 的 cl100k_base：
- 本地可运行，不下载模型权重。
- 按 BPE token 计算，不是字符截断。
- 在 Unicode 字符边界切分，避免中文被破坏。
- 每块最多 400 tokens。
- 相邻块保留最多 80 tokens 重叠。
- chunk_index 从 0 连续递增。
- token_count 保存重新计算后的实际 token 数。
- 短文章至少生成一块。
- 空白内容不生成空 chunk。
本地验收正文结果：
chunk 数：7
chunk_index：0～6
token_count：400, 400, 400, 400, 400, 400, 325
Batch 与 1024 维校验
默认配置：
EMBEDDING_BATCH_SIZE=10
EMBEDDING_DIMENSION=1024
每批最多 10 个 chunk，避免逐块调用。Client 验证：
- 返回数量与输入完全一致。
- API index 必须覆盖连续输入顺序。
- 按 index 恢复输入顺序。
- 每个向量必须恰好 1024 维。
- 拒绝字符串、布尔值、NaN、Infinity 等非法数值。
- 拒绝非 1024 的配置，避免到数据库阶段才失败。
持久化与安全替换
新 chunks 和所有向量先在内存中完整准备。
全部成功后，才在同一数据库事务中：
删除该 Article 的旧 chunks
→ 写入全部新 chunks
→ embedding_status=completed
→ status=completed
→ commit
如果远程调用或结果校验失败：
- 不删除旧 chunks。
- 不保存半套新向量。
- embedding_status=failed
- status=partial_failed
如果数据库替换失败，事务回滚，旧 chunks 得以保留。
数据库现有 (article_id, chunk_index) 唯一约束继续生效。
状态流转
进入条件：
fetch_status=completed
ai_status=completed
clean_content 有效
开始：
embedding_status=processing
embedding_error=null
status=processing
成功：
embedding_status=completed
embedding_error=null
status=completed
失败：
embedding_status=failed
status=partial_failed
AI 失败时不会调用 Embedding。正文、哈希、摘要和标签均保持不变。
错误处理
已覆盖：
- 配置缺失
- API Key 格式无效
- timeout
- 网络连接失败
- HTTP 401
- HTTP 429
- HTTP 5xx
- 空响应
- 返回数量错误
- index 顺序错误
- 向量维度错误
- NaN 等非法向量数值
错误信息不包含 API Key、Authorization 或 traceback。
自动化测试
Phase 8 新增测试：26 个
全量 pytest：110 passed
Phase 0～7 独立回归：84 passed
覆盖 token 切块、400/80、短文章、连续索引、实际 token 数、batch 顺序、1024 维、pgvector 持久化、状态流转、AI 失败跳过、Embedding 失败保护和重新生成安全替换。
唯一警告仍是既有 FastAPI TestClient/httpx2 弃用提示。
真实百炼验证
真实验证未完成。
第一次尝试完整链路时发现：
LLM_API_KEY 未配置
因此状态机正确将 AI 标记为失败并跳过 Embedding。
随后使用一条满足 Phase 8 合法前置条件、已带 AI 摘要和标签的临时 Article 验证真实 Embedding，发现：
EMBEDDING_API_KEY 非空，但包含非 ASCII 字符
HTTP Authorization Header 无法编码，因此请求尚未真正发往百炼。没有猜测或修改 .env，也没有输出该配置值。
需要手动处理：
- 将本机 .env 中 EMBEDDING_API_KEY 替换为真实、ASCII 格式的百炼 API Key。
- 若需要重新验证从真实 AI 开始的完整链路，还需补齐 LLM_API_KEY。
两次验收产生的 Article、chunks、关联和临时标签均已清理。
因此目前没有可报告的真实：
- PostgreSQL chunk 数
- 真实 token_count
- 百炼向量维度
- embedding_status=completed
上述本地 chunk 数和 Mock 1024 维持久化均已通过，但不能替代真实 API 验收。
依赖、Alembic 与 Git
pip check:       No broken requirements found
alembic current: ad5ad692fa18 (head)
alembic check:   No new upgrade operations detected
git diff --check: 通过
- 新增直接依赖：tiktoken 0.14.0
- 未修改数据库结构。
- 未新增 Alembic migration。
- Git 已跟踪文件中的 Secret 匹配数：0。
- 日志中的 Secret 匹配数：0。
- .env 未被 Git 跟踪且已正确忽略。
- 既存的 docs/PHASE_8_PROMPT.md 修改未被本次操作触碰。
Phase 8 Checklist
- Token-based Chunker
- 400/80 滑动窗口
- 连续 chunk_index 和实际 token_count
- OpenAI-compatible Embedding Client
- Batch 请求
- 1024 维及非法向量校验
- PostgreSQL/pgvector Mock 持久化
- 原子替换及旧 chunks 保护
- 状态和安全错误处理
- Phase 0～7 全量回归
- pip、Alembic、Git、Secret 检查
- 真实百炼 text-embedding-v4 入库：等待修正本机 API Key
未进入 Phase 9。



Phase 8 最终真实验收报告
Phase 8 已完整验收通过。
真实完整 Pipeline
实际执行：
Article
→ clean_content
→ 百炼 LLM
→ Token Chunking
→ 百炼 text-embedding-v4
→ PostgreSQL / pgvector
使用模型：
- LLM：qwen3.7-plus-2026-05-26
- Embedding：text-embedding-v4
- 向量维度：1024
- Chunk：400 tokens
- Overlap：80 tokens
真实 LLM 与 Embedding 调用均成功。
AI 结果
实际生成并持久化：
- one_sentence_summary：成功
- key_points：成功，共 10 条
- detailed_summary：成功
- tags：成功，共 10 个
一句话摘要：
文章阐述了构建可靠知识处理流水线的设计原则，涵盖阶段边界、基于 token 的正文切片、批量向量调用与事务替换、状态管理以及组件职责划分。

标签包括：知识处理流水线、正文切片、BPE tokenizer、向量嵌入、事务一致性、状态管理、批量调用、数据验证等。
PostgreSQL / pgvector 二次读取
使用新的独立数据库会话重新读取并验证，不依赖 API 返回。
实际结果：
chunk 数：8
chunk_index：0, 1, 2, 3, 4, 5, 6, 7
token_count：400, 400, 400, 400, 400, 400, 400, 340
向量维度：1024, 1024, 1024, 1024, 1024, 1024, 1024, 1024
确认：
- article_chunks 已实际写入 PostgreSQL。
- chunk_index 从 0 连续递增。
- 数据库内容与本地 TokenChunker 重新切分结果完全一致。
- token_count 与独立重新计算结果一致。
- 每个 chunk 不为空且不超过 400 tokens。
- 每个 pgvector 向量恰好 1024 维。
- 所有向量数值均为有限合法数值。
- metadata 中 tokenizer、400/80 参数正确。
状态和数据完整性
全部符合预期：
fetch_status=completed
fetch_error=null
ai_status=completed
ai_error=null
embedding_status=completed
embedding_error=null
status=completed
同时确认：
- clean_content 未变化。
- content_hash 未变化。
- 独立重新计算 SHA256 与数据库一致。
- AI 一句话摘要、核心观点、详细摘要均保持正确。
- AI 标签及 article_tags 关联保持正确。
验收数据清理
真实验收完成后已清理：
- 临时 Article：已删除
- 临时 article_chunks：已级联删除
- 临时 article_tags：已级联删除
- 本次新增且无其他引用的临时 Tags：已删除
数据库复查确认无验收数据残留。
Secret 检查
- 未修改或输出 .env。
- 未打印、记录或报告任何 API Key。
- Git 已跟踪文件中的 Secret 匹配数：0。
- 项目日志中的 Secret 匹配数：0。
- .env 未被 Git 跟踪。
- .env 已被 .gitignore 正确忽略。
最终测试与验收
pytest:          110 passed
pip check:       No broken requirements found
alembic current: ad5ad692fa18 (head)
alembic check:   No new upgrade operations detected
git diff --check: 通过
唯一警告仍为既存的 FastAPI TestClient/httpx2 弃用提示，不影响功能。
本次仅执行真实 API 验收，没有修改业务代码或数据库结构。Phase 8 最终验收完成，未进入 Phase 9。