Phase 3 已完整完成，并已停止开发。未进入 Phase 4。
修改文件
新增：
- [crawler/http_fetcher.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\http_fetcher.py)：HTTP 抓取、超时、重定向、状态码处理及 SSRF 校验。
- [crawler/extractor.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\extractor.py)：正文和元数据提取。
- [crawler/cleaner.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\cleaner.py)：正文空白、不可见字符和段落清洗。
- [crawler/service.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\service.py)：编排 Fetcher 与 Extractor。
- [crawler/errors.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\errors.py)：安全的抓取异常类型。
- [test_crawler.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_crawler.py)：Phase 3 自动化测试。
修改：
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\article.py)：创建 Article 后同步抓取、持久化正文与更新状态。
- [articles.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\articles.py)：注入 Crawler Service。
- [deps.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\deps.py)：根据配置构建抓取服务。
- [config.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\config.py)：集中管理抓取参数。
- [.env.example](E:\\practice\\projects\\GistAI\\.env.example)：增加抓取配置示例。
- [requirements.txt](E:\\practice\\projects\\GistAI\\apps\\server\\requirements.txt)：增加生产抓取依赖。
- [requirements-dev.txt](E:\\practice\\projects\\GistAI\\apps\\server\\requirements-dev.txt)：复用生产环境中的 httpx。
- [conftest.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\conftest.py)：CRUD 回归测试使用无公网 Stub。
- [test_articles.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_articles.py)：适配 Phase 3 状态流转。
Fetcher / Extractor 设计
调用链为：
Router
→ ArticleService.create_and_fetch
→ CrawlerService
→ HttpFetcher
→ ArticleExtractor
→ Cleaner
→ PostgreSQL
Router 仍只负责参数、依赖和响应；抓取与持久化状态均位于 Service 层。
Fetcher 支持：
- 15 秒默认超时，可通过环境变量调整。
- 最多 5 次重定向。
- 合理的浏览器风格 User-Agent。
- HTTP/HTTPS。
- 403、404、500 等状态的明确安全错误。
- Timeout、ConnectError、通用 RequestError。
- 非 HTML 内容拒绝。
- 重定向由代码手工跟随，以便每一跳执行安全检查。
正文提取方案
采用 trafilatura 2.2.0。
选择原因：
- 专门面向新闻、博客、文档等网页的主内容提取。
- 能过滤导航、页脚等页面噪声。
- 支持标题、作者、日期、站点名称等元数据。
- 比自行维护 DOM/CSS 规则更可靠。
- 无浏览器依赖，符合 Phase 3 的普通 HTTP 抓取范围。
提取后还会执行：
- HTML 实体还原。
- Unicode NFC 规范化。
- 去除零宽字符和 BOM。
- 统一换行。
- 合并多余空白和空行。
- 保留正文段落结构。
正文最小长度默认是 200 个非空白字符，通过 FETCH_MIN_CONTENT_CHARS 集中配置。
SSRF 防护
初始 URL及每一次重定向都会：
- 只允许 HTTP/HTTPS。
- 禁止 URL 用户凭据。
- 禁止 localhost 和 .localhost。
- 检查直接使用的 IPv4/IPv6 地址。
- DNS 解析域名的全部地址。
- 使用 ipaddress.is_global 拒绝 loopback、private、link-local、reserved、multicast、unspecified 等非公网地址。
- 在发送重定向请求前先验证新目标。
已验证重定向到 127.0.0.1 时，不会向内部地址发出第二次请求。
持久化与状态流转
成功流程：
pending
→ fetch_status=processing, status=processing
→ clean_content 入库
→ SHA256(clean_content) 入库
→ fetch_status=completed
→ fetch_error=null
→ status=processing
总状态保持 processing，因为 AI 和 Embedding 尚未执行；两者仍为 pending。
失败流程：
Article 先持久化
→ fetch_status=processing
→ 抓取或提取失败
→ fetch_status=failed
→ status=failed
→ fetch_error=安全、明确的错误
失败不会删除 Article，也不会设置 AI/Embedding 为 completed。
用户显式提供的标题、作者、来源等字段优先；缺失时才使用可靠提取的网页元数据。
自动化测试
开始前 Phase 2 基线：
9 passed
Phase 3 完成后全量测试：
27 passed in 1.64s
覆盖：
- 普通 HTTP 抓取成功。
- User-Agent。
- 正文提取与噪声过滤。
- 文本清洗。
- clean_content 入库。
- SHA256 计算及数据库一致性。
- 元数据提取。
- Timeout。
- ConnectError。
- HTTP 403、404、500。
- 正文为空或过短。
- 失败 Article 保留。
- 失败状态与安全错误信息。
- localhost、loopback、private、link-local、IPv6 loopback。
- 域名解析到私网地址。
- Redirect SSRF。
- 正常公网重定向。
- Phase 2 非法 URL、重复 URL、CRUD、status 和数据库异常脱敏回归。
有一条来自新版 Starlette TestClient 的第三方弃用警告，不影响测试和运行结果。
真实 HTTP 抓取结果
实际启动 Uvicorn 后，通过以下链路抓取了 Python.org 公开网页：
POST /api/v1/articles
→ https://www.python.org/about/
→ HTTP 201
结果：
- title：Welcome to Python.org
- source_name：Python.org
- clean_content 长度：967
- fetch_status：completed
- status：processing
- fetch_error：null
- ai_status：pending
- embedding_status：pending
- 数据库保存的哈希：fac7f82f408833b33e6fabd34485c539e1c41a8819719ac809fb54f4b4228e7e
- 独立重算哈希：完全一致
验收 Article 随后已删除，避免污染文章库；Uvicorn 已停止。
Alembic 与依赖
未修改数据库结构，未新增 migration。
alembic current
ad5ad692fa18 (head)

alembic check
No new upgrade operations detected.
新增直接依赖：
- httpx>=0.28.0,<1.0.0
- trafilatura>=2.0.0,<3.0.0
依赖检查：
No broken requirements found.
Phase 3 checklist
- httpx 普通 HTTP 抓取
- timeout、redirect、User-Agent
- ConnectError、Timeout、403、404、500
- 成熟正文提取方案
- 正文清洗
- 配置化最小正文长度
- title/source_name/author/published_at 尽力提取
- clean_content 持久化
- SHA256 content_hash
- 成功及失败状态流转
- 失败 Article 保留
- SSRF 及 Redirect SSRF 防护
- Phase 2 全量回归
- 无公网依赖的 mock 测试
- 真实公开网页抓取入库
- Alembic 无漂移
- pip check
- 未实现 Playwright、AI、Embedding、RAG 或后台任务
Phase 3 已完成，未进入 Phase 4。