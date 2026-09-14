Phase 17 / Task 5 已完成，并已通过完整验收测试。当前改动尚未提交。
1. 修改与新增文件
核心实现：
- [schemas.py](E:/practice/projects/GistAI/apps/server/app/agent/schemas.py)：全文结果、Evidence 和 Decision 索引结构
- [state.py](E:/practice/projects/GistAI/apps/server/app/agent/state.py)：全文、已读取标识和全文 Evidence 状态
- [context.py](E:/practice/projects/GistAI/apps/server/app/agent/context.py)：注入文章读取、网页抓取、全文筛选依赖
- [article_content.py](E:/practice/projects/GistAI/apps/server/app/agent/article_content.py)：当前用户文章全文读取适配器
- [web_page_fetch.py](E:/practice/projects/GistAI/apps/server/app/agent/web_page_fetch.py)：现有 Crawler 的 Agent 适配器
- [fulltext.py](E:/practice/projects/GistAI/apps/server/app/agent/fulltext.py)：临时切片、相关性排序和 token 预算
- [nodes.py](E:/practice/projects/GistAI/apps/server/app/agent/nodes.py)：两个全文 Tool Node、预算、安全校验、Evidence 与 Sources
- [graph.py](E:/practice/projects/GistAI/apps/server/app/agent/graph.py)：接入全文读取循环
- [reasoning.py](E:/practice/projects/GistAI/apps/server/app/agent/reasoning.py)：支持四类证据和新 Decision 字段
- [deps.py](E:/practice/projects/GistAI/apps/server/app/api/deps.py)：构建全文相关服务
- [config.py](E:/practice/projects/GistAI/apps/server/app/core/config.py)、[.env.example](E:/practice/projects/GistAI/.env.example)：8000 token 全文上下文预算
测试：
- [test_agent_fulltext_loop.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_fulltext_loop.py)
- [test_agent_fulltext_services.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_fulltext_services.py)
- 同步更新已有 Agent Graph、Decision 和 Reasoning 测试。
2. Article Read 调用链
get_article_content Node
→ ArticleContentService
→ ArticleService.get_article
→ SQLAlchemy / DB
ArticleService.get_article 使用 article_id + current_user_id 联合查询。不存在和越权统一返回不可用，不泄露文章是否属于其他用户。
LLM 只返回 kb_result_index，程序从本轮 kb_results 映射 article_id，不能自由构造 ID。
3. Web Fetch 调用链
fetch_web_page Node
→ WebPageFetchService
→ CrawlerService.fetch_article
→ URL/SSRF 校验
→ HTTP Fetch
→ Playwright fallback
→ Extract
→ Clean
没有实现第二套抓取器。localhost、私网、metadata 地址、重定向和 Playwright 导航仍使用已有防护。
4. Graph
evaluate_and_decide
├─ ANSWER → generate_answer → END
├─ REWRITE_QUERY → rewrite_query → knowledge_search
├─ WEB_SEARCH → web_search → evaluate_and_decide
├─ GETGET_ARTICLE_CONTENT
│  → get_article_content
│  → 全文筛选
│  → evaluate_and_decide
├─ FETCH_WEB_PAGE
│  → fetch_web_page
│  → 全文筛选
│  → evaluate_and_decide
└─ INSUFFICIENT → insufficient_answer → END
5. 动作与预算
- GET_ARTICLE_CONTENT：存在未读取的 KB 候选且读取次数少于 2 时允许。
- FETCH_WEB_PAGE：存在未抓取的 Web Search URL 且抓取次数少于 2 时允许。
- MAX_ARTICLE_READS = 2
- MAX_WEB_PAGE_READS = 2
- read_article_ids 和 fetched_web_urls 防止同一目标重复读取。
- 非法索引、重复目标和预算耗尽都在 Decision 校验与 Node 两层阻止。
6. 全文上下文
完整 clean_content 会暂存在当前 Run State，但不会直接传给 LLM。
处理流程：
完整正文
→ 复用 TokenChunker 临时切片
→ 根据 current_query 做词法相关性排序
→ 共享 token 预算筛选
→ 全文 Evidence
AGENT_MAX_FULLTEXT_CONTEXT_TOKENS=8000，知识库和 Web 全文共同使用这一个预算公共预算 token 上限。
7. Evidence 与 Sources
支持四类证据：
- KB Search Chunk
- Web Search Snippet
- KB Full-text Selected Chunk
- Web Full-text Selected Chunk
最终 Sources 只从实际选择用于回答的 Evidence 生成：
- KB 全文：article_id + title
- Web 全文：source_type=web + title + url + source + published_at
时效性问题仍必须选择 Web snippet 或 Web 全文证据。
8. 错误与安全
- Article 不存在或越权：统一不可用
- 非法 Article 索引：Service 不执行、不计 Tool Call
- 非 Web Search URL：无法通过候选索引映射
- SSRF：复用 Crawler 安全校验，不执行网络请求、不计真实抓取
- HTTP/Playwright 均失败：安全记录异常类型，计一次调用并终止
- 数据库执行异常：安全记录异常类型，不暴露内部详情
- 预算耗尽或重复读取：程序拒绝，不继续循环
- 新用户问题会清空全文、Evidence、已读列表及预算计数，但保留消息历史
9. 测试结果
- Agent tests：86 passed
- Fetch / Extraction tests：27 passed
- Agent + Semantic Search + RAG：128 passed
- Full backend：278 passed
- Frontend production build：通过
- Python compileall：通过
- pip check：通过
- git diff --check：通过
- .env Git 跟踪检查：未跟踪
- 代码自审：未发现阻断问题
10. 明确未实现
未实现 save_to_knowledge_base、自动保存 Web 文章、PostgreSQL checkpoint、Long-term Memory、Multi-Agent、前端 Agent UI、数据库迁移或任何 Task 6+ 内容。