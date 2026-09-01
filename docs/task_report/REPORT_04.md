Phase 4 已完整完成并通过验收，未进入 Phase 5。
修改/新增文件
新增：
- [browser_fetcher.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\browser_fetcher.py)：独立 Chromium Playwright Fetcher、请求拦截、导航安全检查及资源释放。
- [test_browser_fallback.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_browser_fallback.py)：Phase 4 fallback、状态、SSRF 和资源生命周期测试。
修改：
- [service.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\service.py)：增加 HTTP → Playwright fallback 编排。
- [errors.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\errors.py)：增加双阶段失败异常。
- [extractor.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\extractor.py)：将底层提取异常转换为安全的 ExtractionError，确保能够 fallback。
- [deps.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\deps.py)：按配置注入 PlaywrightFetcher。
- [config.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\config.py)：增加 Playwright 导航和 network-idle 超时。
- [requirements.txt](E:\\practice\\projects\\GistAI\\apps\\server\\requirements.txt)：增加 Playwright Python 依赖。
- [.env.example](E:\\practice\\projects\\GistAI\\.env.example)：增加 Playwright 参数。
- [README.md](E:\\practice\\projects\\GistAI\\README.md)：补充 Chromium 安装命令。
Article Router 和 Article 数据库模型未修改。
PlaywrightFetcher 设计
当前调用关系：
ArticleService
→ CrawlerService
   ├─ HttpFetcher
   ├─ PlaywrightFetcher
   └─ ArticleExtractor
      └─ Cleaner
PlaywrightFetcher 只负责：
- 启动无头 Chromium。
- 加载页面并等待 domcontentloaded。
- 在限定时间内尝试等待 networkidle。
- 获取最终渲染 HTML 和最终 URL。
- 浏览器网络请求 SSRF 防护。
- 关闭 page、context、browser。
渲染后的 HTML 继续交给 Phase 3 的 ArticleExtractor 和 Cleaner，没有复制正文提取逻辑。
HTTP → Playwright fallback 规则
以下情况进入 Playwright：
- HTTP Timeout、ConnectError、RequestError。
- HTTP 403、404、500 等不可用状态。
- 非 HTML 响应。
- HTTP HTML 无法提取正文。
- HTTP 正文低于最小长度。
以下情况不会启动 Playwright：
- HttpFetcher 已成功获得有效正文。
- 初始 URL 或 HTTP 重定向目标触发 SSRF 检查；这种安全错误直接停止，不允许换用浏览器绕过。
双阶段均失败时，错误示例：
普通 HTTP 阶段失败：无法连接目标网页；
Playwright 阶段失败：Playwright 加载网页超时
不包含 traceback、内部文件路径或底层浏览器调试信息。
Playwright 生命周期
执行顺序：
sync_playwright
→ chromium.launch(headless=True)
→ browser.new_context
→ context.new_page
→ page.goto
→ page.content
→ page.close
→ context.close
→ browser.close
→ Playwright driver 退出
page、context、browser 均在 finally 中分别关闭。即使导航超时、SSRF 拦截或正文提取失败也会执行释放。
测试验证三类资源均关闭；真实抓取结束后检查结果：
No running Playwright browser processes.
SSRF / navigation SSRF
浏览器阶段继续复用 Phase 3 的 UrlSafetyValidator：
- 初始 URL 进入浏览器前校验。
- Chromium context 级拦截所有 HTTP/HTTPS 请求。
- 页面重定向和 JavaScript 导航会再次校验。
- 最终 page.url 再校验一次。
- localhost、loopback、private、link-local、reserved 等非公网地址均拒绝。
- 内部子资源会被 blockedbyclient 中止。
- 内部导航会导致整个抓取失败。
- Service Worker 被禁用，防止绕过 context route。
- WebSocket 请求全部阻止，避免浏览器通过 WebSocket 访问内部网络。
- 已通过安全检查的 origin 在单次抓取中缓存，避免同一站点的每个资源重复 DNS 校验。
自动化测试确认导航到 127.0.0.1 时请求被阻止，且浏览器资源正常释放。
状态流转
开始：
status=processing
fetch_status=processing
HTTP 失败、正在 Playwright fallback：
status=processing
fetch_status=processing
不会提前写入 failed。
Playwright 成功：
status=processing
fetch_status=completed
fetch_error=null
ai_status=pending
embedding_status=pending
HTTP 和 Playwright 均失败：
status=failed
fetch_status=failed
fetch_error=包含 HTTP 和 Playwright 阶段信息的安全错误
ai_status=pending
embedding_status=pending
失败 Article 保留在数据库中。
新增依赖与 Chromium
新增直接依赖：
playwright>=1.50.0,<2.0.0
实际安装版本：
Playwright 1.62.0
Chromium 151.0.7922.34
安装命令：
cd apps/server
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
.\.venv\Scripts\python.exe -m playwright install chromium
Chromium 安装在本机用户缓存，不在项目目录中，也不会提交到 Git。
自动化测试
Phase 4 完成后全量测试：
36 passed in 2.21s
Phase 4 新增覆盖：
- HTTP 成功时 Playwright 调用次数为 0。
- HTTP 网络失败 → Playwright 成功。
- HTTP 正文过短 → Playwright 成功。
- HTTP 和 Playwright 均失败。
- Playwright timeout。
- timeout 后 page/context/browser 全部关闭。
- Playwright navigation SSRF。
- SSRF URL 不进入 Playwright。
- Playwright 正文持久化。
- SHA256 正确。
- 成功最终状态。
- 失败 Article 保留。
- AI/Embedding 状态保持 pending。
存在一条 Starlette TestClient 第三方弃用提示，不影响测试结果。
Phase 0～3 回归
单独重新运行原有 Article 和 HTTP Crawler 测试：
27 passed in 1.82s
以下功能保持正常：
- /health
- URL 422
- 重复 URL 409
- Article CRUD
- status API
- HTTP 抓取
- 正文提取、清洗和哈希
- HTTP SSRF、redirect SSRF
- 数据库异常脱敏
- 外键级联删除
真实普通 HTTP 抓取
实际启动 FastAPI 并抓取：
https://www.python.org/about/
结果：
- HTTP 201
- 标题：Welcome to Python.org
- fetch_status=completed
- 正文长度：967
- SHA256：fac7f82f408833b33e6fabd34485c539e1c41a8819719ac809fb54f4b4228e7e
普通 HTTP 已获得有效正文，代码分支不会实例化或调用 Playwright；自动化测试也通过调用次数明确验证为 0。
真实 Playwright fallback
实际验证公开 JavaScript 渲染页面：
https://quotes.toscrape.com/js/
单独使用 HttpFetcher + Extractor 时：
未能从网页中提取正文
通过完整 API 创建后：
HTTP 正文提取失败
→ Playwright Chromium 渲染
→ ArticleExtractor
→ Cleaner
→ PostgreSQL
结果：
- HTTP 201
- 标题：Quotes to Scrape
- 来源：quotes.toscrape.com
- 正文长度：1071
- 正文包含动态渲染的 Albert Einstein
- fetch_status=completed
- fetch_error=null
- status=processing
- ai_status=pending
- embedding_status=pending
- SHA256：7902f591f4f54d41424c2941ecc779ce94137eea54af343c604e2eb7528c0e02
数据库保存的哈希与独立重新计算结果完全一致。
两条真实验收 Article 均已在验证后删除，FastAPI 已停止。
pip check
No broken requirements found.
Alembic
ad5ad692fa18 (head)
No new upgrade operations detected.
没有数据库模型漂移。
数据库修改
未修改数据库结构，未新增 Alembic migration。
Phase 4 checklist
- 保留 HttpFetcher 第一优先级
- 独立 PlaywrightFetcher
- Chromium
- HTTP 网络失败 fallback
- HTTP 状态错误 fallback
- HTTP 正文无效 fallback
- 有效 HTTP 正文不启动 Playwright
- 复用 Extractor、Cleaner 和最小长度规则
- 配置化导航与 network-idle timeout
- page/context/browser 异常安全关闭
- 初始 URL、导航、最终 URL SSRF 校验
- 内部子资源拦截
- Service Worker 和 WebSocket 防护
- 安全的双阶段错误信息
- 失败 Article 保留
- AI/Embedding 保持 pending
- 36 个全量测试通过
- Phase 0～3 回归通过
- 真实普通 HTTP 抓取成功
- 真实 Playwright fallback 成功
- clean_content/content_hash 入库验证
- pip check
- Alembic head/no drift
- 未实现 manual-content 或其他 Phase 5 功能
Phase 4 已完成，未进入 Phase 5。