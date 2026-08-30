请执行 MVP_IMPLEMENTATION_PLAN.md 的 Phase 9，只完成 Keyword Search，不进入 Phase 10。

Phase 0～8 已完成并验收。开始前阅读实施计划、Article Model/Schema、现有 Service/API 结构，并运行全量测试确认基线。

【目标】

实现：

GET /api/v1/search/keyword

对当前用户已经保存的 Article 做关键词搜索。

本阶段只做 PostgreSQL 关键词检索，不调用 LLM，不调用 Embedding，不使用 pgvector 相似度搜索。

【API】

建议：

GET /api/v1/search/keyword?q=人工智能&page=1&page_size=20

返回统一 API Response。

搜索结果至少包含：

- article_id
- title
- one_sentence_summary
- source_type
- source_name
- published_at
- tags
- favorite
- status
- created_at

可以返回简短 excerpt/snippet，但不要返回完整 clean_content。

分页格式遵循现有 Article List 风格，避免再设计一套分页结构。

【搜索范围】

关键词至少搜索：

- title
- clean_content
- one_sentence_summary
- detailed_summary

如果实现简单，可以同时匹配 author/source_name。

不要搜索 embedding。

多个字段命中同一 Article 时只能返回一条结果。

【匹配规则】

V1 使用 PostgreSQL 简单、稳定的关键词匹配即可。

优先采用适合当前项目的 ILIKE / contains 方案，不要为了 Phase 9 引入 Elasticsearch、Meilisearch 或复杂全文检索基础设施。

要求：

- q trim 后不能为空
- 支持中文关键词
- 英文搜索保持合理的大小写不敏感行为
- SQLAlchemy 参数化查询，禁止字符串拼 SQL
- `%`、`_` 等 LIKE 特殊字符要明确处理，避免产生意外通配行为
- 只返回当前 user_id 的 Article

【排序】

保持简单、确定。

优先考虑：
1. title 命中优先
2. 其他字段命中
3. created_at DESC / id DESC 作为稳定次序

如果当前 SQLAlchemy/PostgreSQL 实现 title 命中优先会明显增加复杂度，可以使用 created_at DESC + id DESC，并在报告中说明。

不要在 Phase 9 实现复杂相关性评分。

【筛选】

遵循实施计划。

如果计划要求，可支持已有简单筛选，例如：

- favorite
- status
- source_type
- tag_id

尽量复用 Article List 已有过滤逻辑。

不要扩展复杂搜索 DSL、多标签组合规则或高级排序。

【Service】

保持：

Search Router
→ SearchService
→ SQLAlchemy
→ PostgreSQL

关键词查询、过滤、分页等逻辑放 Service，不要堆在 Router。

建立独立 SearchService，为 Phase 10 Semantic Search 和 Phase 11 RAG 保留清晰边界，但不要提前实现它们。

【数据安全】

Article List/Search Result 不返回完整 clean_content。

如果返回 excerpt：
- 只截取有限长度
- 尽量围绕关键词附近
- 不修改数据库内容
- 不直接返回整篇文章

搜索本身不能修改 Article、Chunk、Embedding 或状态。

【测试】

自动化测试不调用公网、LLM 或 Embedding。

至少覆盖：

- title 命中
- clean_content 命中
- one_sentence_summary 命中
- detailed_summary 命中
- 中文关键词
- 英文大小写
- 多字段命中不重复 Article
- q 为空/纯空白
- `%` / `_` 等特殊字符
- user_id 数据隔离
- 分页
- 稳定排序
- 搜索结果不包含完整 clean_content
- 无匹配返回空结果
- 已有筛选条件（如果本阶段实现）
- Phase 0～8 全量回归

【真实 PostgreSQL 验证】

实际启动 FastAPI，创建几篇具有明确不同关键词的测试 Article。

验证：

关键词
→ GET /api/v1/search/keyword
→ PostgreSQL
→ 正确 Article 列表

至少确认：

- 中文搜索成功
- 标题/正文/摘要搜索成功
- 无关 Article 不返回
- 分页正确
- 不返回完整 clean_content
- 不调用 LLM/Embedding
- 搜索不会修改 Article 状态或 chunks

验收完成后清理临时数据。

【依赖与数据库】

原则上：
- 不新增依赖
- 不修改数据库结构
- 不新增索引

如果发现现有数据量下确有必要新增索引，先在报告中说明，不要擅自引入复杂全文搜索方案。

执行：

- 全量 pytest
- pip check
- alembic current
- alembic check
- git diff --check

【禁止】

本阶段不要实现：

- Semantic Search
- pgvector similarity
- query embedding
- similarity threshold
- HNSW
- RAG
- LLM 搜索
- Elasticsearch / Meilisearch
- BackgroundTasks
- 前端搜索页面
- 登录系统

不要进入 Phase 10。

【完成报告】

完成后停止并报告：

- 修改/新增文件
- Keyword Search API
- SearchService 设计
- 搜索字段和匹配规则
- LIKE 特殊字符处理
- 排序/分页/筛选策略
- Search Result / excerpt 设计
- user_id 隔离
- 自动化测试及 Phase 0～8 回归
- 真实 PostgreSQL HTTP 搜索验证
- 是否调用 LLM/Embedding
- pip / Alembic / git diff 状态
- 是否修改数据库
- Phase 9 checklist
- 明确说明未进入 Phase 10

完成后停止，等待人工验收。