Phase 5 已完整完成并通过验收，未进入 Phase 6。
修改/新增文件
新增：
- [test_manual_content.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_manual_content.py)：手动正文 API、状态恢复、替换安全性和不调用抓取器测试。
修改：
- [articles.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\articles.py)：新增 manual-content 路由。
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\schemas\\article.py)：新增明确的 ManualContentRequest。
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\article.py)：手动正文清洗、校验、哈希、原子替换和状态恢复。
- [cleaner.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\cleaner.py)：增加网页提取和手动正文共用的有效性校验。
- [extractor.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\crawler\\extractor.py)：改为复用统一正文有效性规则。
- [exceptions.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\exceptions.py)：增加安全的手动正文 422 业务异常。
- [deps.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\deps.py)：提供统一的最小正文长度配置依赖。
manual-content API
POST /api/v1/articles/{id}/manual-content
Content-Type: application/json

{
  "content": "用户粘贴的足够长度文章正文……"
}
成功响应：
{
  "code": 20000,
  "message": "手动正文保存成功",
  "data": {
    "id": 136,
    "source_type": "web",
    "clean_content": "清洗后的最终正文……",
    "content_hash": "d5a286cdcb75b7838c7704a375433f9b47468f8a4293d569b72149688df591cc",
    "status": "processing",
    "fetch_status": "completed",
    "fetch_error": null,
    "ai_status": "pending",
    "embedding_status": "pending"
  }
}
Article 不存在：
{
  "code": 40401,
  "message": "Article 不存在",
  "data": null
}
HTTP 状态为 404。
清洗后正文无效：
{
  "code": 42202,
  "message": "手动正文清洗后过短，至少需要 200 个非空白字符",
  "data": null
}
空字符串由 Pydantic Schema 拒绝，同样返回标准 HTTP 422。
Manual Content Service 设计
调用关系：
Router
→ ManualContentRequest
→ ArticleService.set_manual_content
→ clean_and_validate_content
→ SHA256
→ PostgreSQL
Router 只负责：
- 解析 Article ID。
- 校验请求 Schema。
- 获取统一最小正文长度。
- 调用 Service。
- 返回统一响应。
Router 中没有 Cleaner、哈希或状态逻辑。
Cleaner 和最小正文长度复用
新增统一方法：
clean_and_validate_content(
    content,
    min_content_chars,
    content_label=...
)
网页正文提取和 manual-content 现在共用：
- clean_text
- HTML 实体还原
- Unicode NFC 规范化
- 零宽字符和 BOM 清理
- 不换行空白合并
- 多余空行合并
- 非空判断
- 非空白字符数量计算
- FETCH_MIN_CONTENT_CHARS
没有维护第二套最小长度或散落 magic number。
content_hash
哈希基于最终清洗后的正文：
SHA256(clean_content.encode("utf-8"))
网页抓取和手动正文现在共用 Article Service 的 _content_hash 方法。
已有正文的安全替换策略
执行顺序：
查询 Article
→ 在内存中清洗新正文
→ 校验最小长度
→ 在内存中计算 SHA256
→ 全部成功后才修改 ORM 字段
→ commit
不会先清空旧正文。
如果新正文无效：
- 不修改旧 clean_content
- 不修改旧 content_hash
- 不修改原有成功状态
- 返回 HTTP 422
自动化测试已验证无效正文不会覆盖旧的有效内容；有效正文可以替换旧正文和旧哈希。
source_type 处理
manual-content 不修改 source_type。
原因是当前字段表示 Article 原始 URL 的来源类型，并用于来源筛选；手动正文只是正文获取方式变化，不代表原始文章来源消失。
例如原值为：
source_type=web
手动正文成功后仍保持 web。
当前数据库没有独立的 content_source 字段。本阶段没有为了记录获取方式修改数据库结构。
状态流转
原始失败状态：
status=failed
fetch_status=failed
fetch_error=普通 HTTP 与 Playwright 失败信息
手动正文成功后：
status=processing
fetch_status=completed
fetch_error=null
ai_status=pending
ai_error=null
embedding_status=pending
embedding_error=null
正文已可供后续 Pipeline 使用，但 AI 和 Embedding 尚未执行，因此总状态保持 processing。
手动正文失败时，Article 状态和已有数据均保持不变。
manual-content 路由没有 Crawler 依赖，不调用 HttpFetcher 或 Playwright。
自动化测试
Phase 5 新增 8 个测试场景，覆盖：
- failed Article → manual content 成功
- Cleaner 结果正确
- clean_content 持久化
- SHA256 正确
- failed → completed
- 总状态恢复为 processing
- fetch_error 清空
- AI/Embedding 保持 pending
- Article 404
- 空字符串
- 纯空白正文
- 清洗后正文过短
- 无效正文不覆盖已有正文和哈希
- 有效正文替换已有正文和哈希
- manual-content 不调用 HttpFetcher
- manual-content 不调用 Playwright
- source_type 保持不变
最终全量结果：
44 passed in 2.28s
存在一条 Starlette TestClient 的第三方弃用提示，不影响测试结果。
Phase 0～4 回归
单独运行原有测试：
36 passed in 1.83s
CRUD、HTTP 抓取、Playwright fallback、SSRF、状态接口和级联删除均保持正常。
真实 API 验证
实际启动 FastAPI 后使用不可解析的 .invalid URL 创建 Article。
创建结果：
HTTP 201
status=failed
fetch_status=failed
fetch_error=普通 HTTP 阶段失败：目标域名无法解析；
            Playwright 阶段失败：目标域名无法解析
clean_content=null
content_hash=null
随后调用：
POST /api/v1/articles/136/manual-content
提交足够长度的真实正文，再通过详情接口查询。
结果：
- manual-content：HTTP 200
- Article Detail：HTTP 200
- 清洗后正文长度：724
- 多余空行已清除
- fetch_status=completed
- status=processing
- fetch_error=null
- ai_status=pending
- embedding_status=pending
- source_type=web
数据库保存哈希：
d5a286cdcb75b7838c7704a375433f9b47468f8a4293d569b72149688df591cc
独立重新计算结果完全一致：
hash_matches=true
验收 Article 已删除，再次查询返回 404；FastAPI 已停止。
pip check
No broken requirements found.
本阶段没有新增依赖。
Alembic
ad5ad692fa18 (head)
No new upgrade operations detected.
数据库修改
未修改数据库结构，未新增 Alembic migration。
Phase 5 checklist
- POST /api/v1/articles/{id}/manual-content
- 明确的 Pydantic Request Schema
- Article 404
- 空字符串拒绝
- 纯空白正文拒绝
- 清洗后过短拒绝
- 复用现有 Cleaner
- 复用现有最小正文长度配置
- clean_content 持久化
- SHA256 content_hash
- failed Article 恢复 completed
- 总状态恢复 processing
- fetch_error 清空
- AI/Embedding 保持 pending
- 无效替换保留旧正文和哈希
- 有效替换更新正文和哈希
- 不调用 HttpFetcher
- 不调用 Playwright
- source_type 保持原始来源语义
- 44 个全量测试通过
- Phase 0～4 回归通过
- 真实 API 和数据库验收通过
- pip check
- Alembic head/no drift
- 无数据库修改
- 未实现 AI、LLM、标签、Chunk、Embedding 或 RAG
Phase 5 已完成，未进入 Phase 6。