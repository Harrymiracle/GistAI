Phase 10 最终报告
完成状态
Phase 10 功能开发和自动化验收已完成，但真实百炼验收未通过，因此暂不能标记为完整验收完成。
阻塞原因：当前根目录 .env 中读取到的 EMBEDDING_API_KEY 不符合现有 Client 的格式校验。未输出或记录密钥内容。
修改文件
- [search.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\search.py)：新增 POST /api/v1/search/semantic
- [search.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\search.py)：实现 query embedding、pgvector 查询、去重和排序
- [search.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\schemas\\search.py)：新增请求与响应 Schema
- [service.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\embedding\\service.py)：新增 embed_query()，复用现有 Embedding Client
- [config.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\config.py)：接入 RAG_TOP_K 和 RAG_SIMILARITY_THRESHOLD
- [exceptions.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\exceptions.py)：新增安全的语义搜索 Embedding 异常
- [test_semantic_search.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_semantic_search.py)：新增 20 项 Phase 10 测试
用户已有的 docs/PHASE_10_PROMPT.md 修改未触碰。
Semantic Search API
POST /api/v1/search/semantic
Content-Type: application/json

{
  "query": "如何提高知识处理系统的可靠性？",
  "top_k": 3
}
成功响应包含：
- article_id
- title
- chunk_id
- chunk_index
- excerpt
- score
- one_sentence_summary
- source_url
- source_name
不返回 clean_content。
实现策略
调用结构：
Search Router
→ SearchService
→ EmbeddingService.embed_query()
→ 现有 OpenAICompatibleEmbeddingClient
→ PostgreSQL / pgvector
- query trim 后必须非空，最大 1000 字符。
- top_k 默认 3，允许范围 1～50。
- query vector 在进入数据库前再次确认恰好 1024 维。
- 使用 pgvector cosine_distance。
- score = 1 - cosine_distance，分数越大越相关。
- 使用 RAG_SIMILARITY_THRESHOLD=0.35，低于阈值的结果被过滤。
- 无命中正常返回 HTTP 200 和空列表。
- 使用窗口函数按 Article 分组，每篇 Article 只保留最高分 Chunk。
- 最终按 score DESC，再按 Article、Chunk 稳定排序并限制 top_k。
- 仅查询当前 user_id 且 embedding_status=completed 的 Article。
错误处理
已覆盖：
- 空白 query
- top_k 越界
- 配置缺失
- timeout / network
- 401 / 429 / 5xx
- 空响应
- 1024 维错误
- pgvector/数据库异常
Embedding 错误返回安全的 HTTP 502；数据库错误沿用统一 HTTP 500 响应。API 不暴露密钥、Authorization、traceback 或数据库细节。
自动化测试
- Phase 10：20 passed
- Phase 0～9 独立回归：125 passed
- 最终全量：145 passed, 1 warning
唯一警告是已有 FastAPI TestClient/httpx2 弃用提示。
测试确认：
- cosine score 正确
- threshold、top_k 和排序正确
- 同 Article 多 Chunk 去重
- 用户隔离及状态过滤
- pgvector 使用真实 PostgreSQL 执行
- 搜索只读
- 不调用 LLM
- 不修改 Article、Chunk、状态或正文
- Phase 9 Keyword Search 保持正常
真实百炼 + PostgreSQL 验收
真实调用未成功发出。
实际启动 FastAPI 后请求 Semantic Search，返回：
HTTP 502
EMBEDDING_API_KEY 格式无效
安全检查只确认了配置特征，没有输出密钥值。由于 query embedding 未生成：
- 无法报告真实 query vector 维度
- 无法报告真实 similarity score 和返回顺序
- 没有创建临时 Article/Chunk
- 临时验收数据检查结果：0
- PostgreSQL 未发生修改
最终检查
- pytest：145 passed
- pip check：No broken requirements found
- alembic current：ad5ad692fa18 (head)
- alembic check：无待生成 migration
- git diff --check：通过
- .env：已被 .gitignore 忽略且未被 Git 跟踪
- Secret 扫描：未发现可疑密钥模式
- 新增依赖：无
- 数据库结构/migration/index：均未修改
- LLM 调用：无
Phase 10 Checklist
- Semantic Search API
- 复用 EmbeddingService / EmbeddingClient
- 1024 维校验
- pgvector cosine 检索
- similarity threshold
- top_k
- Article 级去重
- 用户隔离
- 只读保证
- 自动化测试和全量回归
- 真实百炼 Embedding + 实际 score 验收：被本机 Key 格式阻塞
未进入 Phase 11。



Phase 10 补充真实验收报告
Phase 10 可以最终验收通过。
真实查询
怎样让知识处理平台更稳定，并在外部服务失败时保护已有数据？
- 模型：text-embedding-v4
- query vector：1024 维
- corpus vectors：7 个，均为 1024 维
- Semantic Search HTTP 状态：200
- pgvector cosine search：执行成功
API 实际返回
请求 top_k=3，阈值过滤后返回：
排名	Article	Chunk	Score
1	可靠的知识处理流水线	chunk_index=0	0.73876369


结果按 score 降序，明显相关内容优先。
完整 pgvector 分数分布
内容	用户/状态	Chunk	Score	处理结果
其他用户的高度相关内容	user_id=2 / completed	0	0.99999893	用户隔离排除
向量状态未完成的高度相关内容	user_id=1 / failed	0	0.99999893	状态过滤排除
可靠的知识处理流水线	user_id=1 / completed	0	0.73876369	返回
可靠的知识处理流水线	user_id=1 / completed	1	0.58960693	Article 去重排除
家庭面包烘焙	user_id=1 / completed	0	0.22174771	低于阈值
古典音乐入门	user_id=1 / completed	0	0.16662448	低于阈值
阳台番茄种植	user_id=1 / completed	0	0.13485574	低于阈值


Threshold / top_k / 去重
- RAG_SIMILARITY_THRESHOLD=0.35 未调整。
- 所有 API 返回项均满足 score >= 0.35。
- 三个明显无关主题均被阈值排除。
- 请求 top_k=3，阈值过滤后只有一个合格 Article，因此返回一项符合预期。
- 补充请求 top_k=1，实际返回一项。
- 同一 Article 的两个相关 Chunk 分别为 0.73876369 和 0.58960693，最终只返回最高分 Chunk。
- 返回 Article ID 无重复。
隔离与只读验证
- user_id=2 的高度相关结果虽然得分 0.99999893，但未返回。
- embedding_status=failed 的高度相关结果虽然得分 0.99999893，但未返回。
- 未调用 LLM。
- 未保存 query embedding。
- PostgreSQL 调用前后对比：
  - Articles 未变化
  - article_chunks 内容、向量和数量未变化
  - status、clean_content、content_hash 未变化
临时数据清理
清理后确认：
- 临时 Articles：0
- 临时 article_chunks：0
- 临时 Tags：0
- 临时 article_tags：0
- 临时验收脚本已删除
最终检查
- 全量测试：145 passed, 1 warning
- pip check：无损坏依赖
- alembic current：ad5ad692fa18 (head)
- alembic check：无待生成 migration
- git diff --check：通过
- 本次未修改业务代码
- API Key 未被输出、记录或提交
Phase 10 最终验收通过。未进入 Phase 11。