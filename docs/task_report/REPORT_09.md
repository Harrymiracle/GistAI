Phase 9 验收报告
Phase 9 Keyword Search 已完整完成并通过验收，未进入 Phase 10。
修改/新增文件
- [search.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\search.py)：Keyword Search Router。
- [search.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\search.py)：PostgreSQL 搜索、排序和分页。
- [search.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\schemas\\search.py)：查询参数和轻量结果 Schema。
- [router.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\router.py)：注册 Search Router。
- [test_keyword_search.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_keyword_search.py)：Phase 9 自动化测试。
既存的 docs/PHASE_9_PROMPT.md 修改未被本次操作触碰。
Keyword Search API
已实现：
GET /api/v1/search/keyword?q=人工智能&page=1&page_size=20
统一响应：
{
  "code": 20000,
  "message": "关键词搜索成功",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  }
}
每条结果包含：
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
不包含 clean_content 或 detailed_summary。
SearchService 设计
调用结构：
Search Router
→ SearchService
→ SQLAlchemy
→ PostgreSQL
Router 只负责：
- Query 参数解析
- 当前用户依赖
- 调用 SearchService
- 响应 Schema 转换
查询、字段匹配、排序和分页全部位于 SearchService。
搜索字段和匹配规则
使用 PostgreSQL 参数化 ILIKE，搜索：
- title
- clean_content
- one_sentence_summary
- detailed_summary
行为：
- q 自动 trim。
- 空字符串和纯空白返回 HTTP 422。
- 最大长度 200。
- 支持中文。
- 英文大小写不敏感。
- 多个字段同时命中时只返回一条 Article。
- 只搜索当前 user_id 的 Article。
- 不搜索 embedding 或 article_chunks。
LIKE 特殊字符
查询词中的控制字符按字面量处理：
\ → \\
% → \%
_ → \_
SQLAlchemy 使用绑定参数和明确的 ESCAPE '\'，没有字符串拼 SQL。
自动化测试已验证包含 %、_ 和反斜杠的关键词不会产生意外通配。
排序、分页和筛选
排序：
1. title 命中优先
2. created_at DESC
3. id DESC
没有实现复杂相关性评分。
分页复用 Article List 风格：
page >= 1
1 <= page_size <= 100
本阶段没有增加 favorite/status/source_type/tag_id 筛选。Phase 9 实施计划只明确关键词接口，因此保持最小范围，没有扩展搜索 DSL。
Search Result / Excerpt
本阶段不返回 excerpt。
原因是当前轻量结果已有标题和一句话摘要，省略 excerpt 可以完全避免搜索接口意外泄露完整正文，也无需在应用层重复处理大小写和 Unicode 关键词定位。
用户隔离与只读性
所有 SQL 查询强制包含：
articles.user_id = current_user_id
实际验证：
- 相同关键词存在于其他 user_id 时不会返回。
- 搜索不会修改 Article 状态。
- 不修改 clean_content、摘要或标签。
- 不修改或删除 article_chunks。
- 不调用 LLM。
- 不调用 Embedding。
- 不执行 pgvector 相似度查询。
自动化测试
Phase 9 新增 15 个测试，覆盖：
- title 命中
- clean_content 命中
- one_sentence_summary 命中
- detailed_summary 命中
- 中文关键词和 trim
- 英文大小写不敏感
- 多字段命中不重复
- 空查询和纯空白
- %、_、反斜杠转义
- user_id 隔离
- title 命中优先
- created_at/id 稳定排序
- 分页
- 标签返回
- 不返回完整正文
- 无匹配空结果
- 搜索只读
- 不调用 AI/Embedding
结果：
Phase 9 tests:       15 passed
Phase 0～8 回归:     110 passed
全量 pytest:         125 passed
唯一警告仍为既存 FastAPI TestClient/httpx2 弃用提示，不影响功能。
真实 PostgreSQL HTTP 验证
实际启动 Uvicorn，并创建标题、正文、摘要、详细摘要、无关内容、其他用户和分页测试 Article。
实际请求全部返回 200：
GET /health
GET /api/v1/search/keyword?q=<中文标题关键词>
GET /api/v1/search/keyword?q=<正文关键词>
GET /api/v1/search/keyword?q=<一句话摘要关键词>
GET /api/v1/search/keyword?q=<详细摘要关键词>
GET /api/v1/search/keyword?q=<分页关键词>&page=1&page_size=2
GET /api/v1/search/keyword?q=<分页关键词>&page=2&page_size=2
GET /api/v1/search/keyword?q=<不存在关键词>
确认：
- 中文搜索成功。
- 标题、正文、一句话摘要、详细摘要均能命中。
- 每类明确关键词只返回目标 Article。
- 无关 Article 不返回。
- 其他用户 Article 不返回。
- 分页总数 3，第一页 2 条、第二页 1 条。
- 标题命中排在较新的正文命中之前。
- 响应不包含 clean_content 或完整正文。
- Article 状态和正文保持不变。
- 既有 chunk 数量保持不变。
- 没有调用 LLM 或 Embedding。
验收完成后已清理所有临时：
- Articles
- article_chunks
- article_tags
- Tag
Uvicorn 已正常停止。
依赖、数据库与 Git
pip check:       No broken requirements found
alembic current: ad5ad692fa18 (head)
alembic check:   No new upgrade operations detected
git diff --check: 通过
- 未增加依赖。
- 未修改数据库结构。
- 未新增索引。
- 未新增 Alembic migration。
Phase 9 Checklist
- GET /api/v1/search/keyword
- PostgreSQL 参数化 ILIKE
- 四个必要字段搜索
- 中文与英文大小写处理
- LIKE 特殊字符转义
- 当前用户数据隔离
- 多字段命中去重
- 标题命中优先
- 稳定分页
- 轻量响应，不返回正文
- 搜索只读
- 不调用 LLM/Embedding
- 自动化测试及 Phase 0～8 回归
- 真实 FastAPI/PostgreSQL 验证
- 验收数据清理
- pip、Alembic、Git 验收
未进入 Phase 10。