请继续执行 MVP_IMPLEMENTATION_PLAN.md 中的 Phase 4。
只执行 Phase 4：Playwright 浏览器抓取兜底。
不要进入 Phase 5。
Phase 0～3 已完成、验收并提交 Git。开始前先阅读实施计划和现有 crawler / Article Service 代码，并运行现有测试确认基线正常。
本阶段目标：
POST /api/v1/articles
→ 创建 Article
→ 优先使用 Phase 3 HttpFetcher 普通 HTTP 抓取
→ 普通 HTTP 抓取/正文提取失败时，自动 fallback 到 Playwright
→ 获取浏览器渲染后的 HTML
→ 继续复用现有 Extractor + Cleaner
→ 保存 clean_content / content_hash
→ 正确更新抓取状态
要求：
1. 保留 Phase 3 的 HttpFetcher 作为第一优先级，不要所有 URL 默认直接使用 Playwright。
2. 新增独立 Playwright Fetcher，保持 crawler 分层清晰。理想职责关系类似：
CrawlerService
├─ HttpFetcher
├─ PlaywrightFetcher
├─ ArticleExtractor
└─ Cleaner
不要把 Playwright 逻辑写进 Router，也不要复制一套正文提取/清洗逻辑。
3. fallback 规则：
   - 普通 HTTP 网络请求失败 → 尝试 Playwright
   - HTTP 返回不可用状态导致抓取失败 → 尝试 Playwright
   - HTTP 成功但正文提取为空/明显过短 → 尝试 Playwright
   - HttpFetcher 成功获得有效正文 → 不启动 Playwright
4. Playwright 使用 Chromium。
   - 设置合理 timeout
   - 等待页面达到适合提取正文的状态
   - 获取最终渲染 HTML
   - 不进行无限等待或无限重试
   - 浏览器/page/context 必须正确关闭，异常时也不能泄漏资源
5. Playwright 获取 HTML 后必须继续复用 Phase 3 的：
   - ArticleExtractor
   - Cleaner
   - 最小正文长度规则
   - metadata 提取
   - SHA256 content_hash
6. SSRF 防护不能因为进入 Playwright 而失效。
   - 初始 URL 仍执行现有安全校验
   - 页面最终跳转目标也必须检查
   - 防止通过 redirect / navigation 访问 localhost、loopback、private、link-local 等内部地址
   - 如果 Playwright 会产生页面子资源请求，评估是否需要阻止明显的内部网络请求，采用与当前架构匹配的合理方案
   - 不要为了 SSRF 引入大型安全基础设施
7. 状态流转：
   - 开始抓取：fetch_status=processing
   - HTTP 失败但正在 fallback Playwright 时，不要提前把最终 fetch_status 写成 failed
   - Playwright 成功：fetch_status=completed、fetch_error=null
   - HTTP + Playwright 都失败：fetch_status=failed，并保留安全、明确的 fetch_error
   - Article 失败后仍必须保留
   - ai_status / embedding_status 继续保持 pending
   - 不要实现 Phase 5 的手动正文兜底
8. 错误信息应能够帮助后续排查。
   HTTP 和 Playwright 都失败时，可以保留合理的阶段信息，但不要向 API 用户暴露 traceback、内部路径或敏感信息。
9. Playwright 相关参数集中配置，例如 timeout 等，不要散落 magic number；按需要更新 .env.example。
10. 增加必要的 Playwright Python 依赖，并确保 Chromium 安装方式明确。
    不要提交浏览器二进制文件到 Git。
11. 自动化测试不能依赖真实公网。
    使用 mock / stub 覆盖至少：
    - HTTP 成功 → 不调用 Playwright
    - HTTP 失败 → Playwright fallback 成功
    - HTTP 正文过短 → Playwright fallback 成功
    - HTTP + Playwright 都失败
    - Playwright timeout
    - Playwright 成功后的 clean_content 持久化
    - content_hash 正确
    - 最终状态正确
    - 失败 Article 保留
    - SSRF / redirect/navigation SSRF
    - Phase 3 和 Phase 2 全量回归
12. 除自动化测试外，实际启动 FastAPI 做真实验证：
    A. 至少验证一个普通网页仍然优先走 HttpFetcher，不无意义启动 Playwright。
    B. 如果能够找到适合的公开动态网页，实际验证一次 HTTP 失败/正文无效 → Playwright fallback → 正文入库。
    如果由于目标网站或当前网络环境无法稳定构造真实 fallback 场景，不要伪造结果；明确报告，并以自动化测试证明 fallback 链路。
13. 执行：
    - 全量 pytest
    - pip check
    - alembic current
    - alembic check
    - 必要的真实 HTTP/API 验证
14. 原则上本阶段不修改数据库结构。
    如果确实必须修改，只能新增 Alembic migration，不能修改历史 migration。
本阶段禁止实现：
- 用户手动粘贴正文
- Phase 5 manual-content API
- LLM
- AI 摘要
- AI 标签
- Chunk
- Embedding
- Semantic Search
- RAG
- BackgroundTasks
- SSE
- WebSocket
- Redis
- Celery
- Qdrant
- n8n
- 登录系统
完成后停止开发，不要进入 Phase 5。
请输出完整验收报告，包括：
- 修改/新增文件
- PlaywrightFetcher 设计
- HTTP → Playwright fallback 判断规则
- Playwright 生命周期及资源释放方式
- SSRF / navigation SSRF 处理
- 成功/失败状态流转
- 新增依赖及 Chromium 安装方式
- 自动化测试数量和结果
- Phase 0～3 回归结果
- 真实普通 HTTP 抓取结果
- 真实 Playwright fallback 验证结果
- clean_content/content_hash 持久化验证
- pip check
- Alembic 状态
- 是否修改数据库
- Phase 4 checklist
- 明确说明“未进入 Phase 5”
完成后停止，等待人工验收。