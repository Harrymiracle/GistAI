请继续执行 MVP_IMPLEMENTATION_PLAN.md 中的 Phase 3。
只执行 Phase 3：普通 HTTP 网页抓取、正文提取与清洗。
不要进入 Phase 4。
Phase 0～2 已完成、验收并提交 Git。开始前先阅读实施计划和现有代码，并运行现有测试确认基线正常。
本阶段目标：
POST /api/v1/articles
→ 创建 Article
→ 使用 httpx 普通 HTTP 抓取 URL
→ 提取网页正文并清洗
→ 保存 articles.clean_content
→ 基于 clean_content 计算 SHA256 并保存 content_hash
→ 正确更新 status / fetch_status / fetch_error。
要求：
1. 抓取、正文提取/清洗与 Article 业务逻辑合理分层，不把复杂逻辑堆在 Router。
2. 正文提取使用成熟轻量方案，并说明选择原因。
3. 支持 timeout、redirect、合理 User-Agent，并正确处理 ConnectError、Timeout、403、404、500 等情况。
4. 做基础 SSRF 防护：禁止 localhost、loopback、private、link-local 等内部地址，并防止通过 redirect 绕过。
5. 正文为空或明显过短视为提取失败；阈值集中配置，不散落 magic number。
6. 能可靠获取时可保存 title、author、published_at、source_name；获取不到不影响正文成功。
7. 抓取成功：
   - clean_content 持久化到 PostgreSQL
   - content_hash = SHA256(clean_content)
   - fetch_status = completed
   - fetch_error = null
8. 抓取失败：
   - Article 记录必须保留
   - fetch_status = failed
   - fetch_error 记录安全、明确的错误
9. 不要把 ai_status / embedding_status 错误设置为 completed。
10. Phase 2 的非法 URL 422、重复 URL 409、CRUD、status API 必须保持正常。
11. 自动化测试不要依赖公网，HTTP 层使用 mock；覆盖成功抓取、正文提取、hash、timeout、连接失败、403/404/500、过短正文、SSRF、redirect SSRF、失败 Article 保留及状态。
12. 所有 Phase 2 回归测试必须继续通过。
13. 除 mock 测试外，实际启动 FastAPI，用至少一个公开普通网页完成一次真实 HTTP 抓取，确认 clean_content/content_hash 确实入库；如果环境网络限制导致失败，必须如实报告。
14. 原则上不修改 Phase 1 数据库结构；确需修改必须新增 Alembic migration，不能修改历史 migration。
15. 添加依赖后执行 pip check。
本阶段禁止实现：
Playwright、Selenium、手动正文兜底、LLM、AI 摘要、AI 标签、Chunk、Embedding、Semantic Search、RAG、BackgroundTasks、SSE、WebSocket、Redis、Celery、Qdrant、n8n、登录系统。
完成后实际运行测试和验收，并报告：
- 修改文件
- Fetcher / Extractor 设计
- 正文提取方案
- SSRF 方案
- clean_content/content_hash 持久化结果
- 成功/失败状态流转
- 自动化测试结果
- Phase 2 回归结果
- 真实 HTTP 抓取结果
- Alembic 状态
- 新增依赖
- Phase 3 checklist
完成后停止，不要进入 Phase 4，等待人工验收。