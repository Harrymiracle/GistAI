请继续执行 MVP_IMPLEMENTATION_PLAN.md 中的 Phase 5。
只执行 Phase 5：手动正文兜底（Manual Content Fallback）。
不要进入 Phase 6。
Phase 0～4 已完成、验收并提交 Git。开始前先阅读实施计划和现有 Article / crawler 代码，并运行现有测试确认基线正常。
本阶段目标：
当普通 HTTP + Playwright 均无法获得有效正文时，Article 保留为抓取失败状态，允许用户通过 API 手动提交文章正文。
流程：
HTTP
→ 失败
→ Playwright
→ 失败
→ Article 保留
→ 用户提交 manual content
→ Cleaner
→ 正文有效性校验
→ clean_content
→ SHA256 content_hash
→ PostgreSQL
→ 更新 Article 状态
一、实现 API
实现：
POST /api/v1/articles/{id}/manual-content
请求至少包含：
{
"content": "用户粘贴的文章正文"
}
可以根据现有 Schema 风格设计具体字段，但不要扩展无关功能。
二、核心规则
1. Article 不存在：
   - HTTP 404。
2. manual content 必须经过后端校验。
   - 空字符串、纯空白内容拒绝。
   - 清洗后正文低于现有 FETCH_MIN_CONTENT_CHARS 最小正文长度时拒绝。
   - 尽量复用 Phase 3 已有 Cleaner 和正文有效性规则，不要重新维护另一套规则。
3. 手动正文必须经过现有 Cleaner。
4. 清洗成功后：
   - 保存 articles.clean_content
   - 基于最终 clean_content 计算 SHA256
   - 保存 articles.content_hash
5. 手动正文成功后，抓取阶段视为已经获得有效正文：
   - fetch_status = completed
   - fetch_error = null
   - ai_status = pending
   - embedding_status = pending
   - overall status 按当前 pipeline 语义保持正确，通常应进入 processing，等待后续 AI / Embedding
6. 手动正文校验失败时：
   - 不要覆盖数据库中已有的有效 clean_content
   - 不要生成错误 content_hash
   - 返回明确、安全的 4xx 错误
   - 不暴露 traceback
7. 如果 Article 原来是：
fetch_status=failed
手动正文成功后应能够恢复为：
fetch_status=completed
status=processing
为 Phase 6 AI 处理做好准备。
8. 如果 Article 已经存在有效 clean_content，再次调用 manual-content：
   - 允许用户使用新的手动正文替换现有正文。
   - 必须先完成“清洗 + 有效性校验 + hash 计算”，全部成功后再覆盖原数据。
   - 如果新正文无效，保留旧的有效 clean_content/content_hash。
   - 不允许先清空旧正文再验证。
9. 用户手动正文只代表正文来源改变，不要重新调用 HttpFetcher 或 Playwright。
10. 如果当前 source_type 设计支持 manual：
    - 请结合既有数据模型和实施计划判断是否需要设置 source_type=manual。
    - 不要为了这个字段修改数据库枚举/结构。
    - 如果现有 source_type 是普通字符串，可按产品语义合理处理，并在报告中说明决定。
三、代码结构
保持现有分层：
Router
→ ArticleService
→ Cleaner / 正文校验
→ PostgreSQL
不要把正文清洗、hash、状态业务逻辑全部写进 Router。
尽量复用 Phase 3/4 已有：
- Cleaner
- 最小正文长度配置
- SHA256 逻辑或公共方法
- Article 状态管理方式
如果发现 hash / 正文校验逻辑目前散落在 crawler 内部，允许做小范围重构以实现复用，但不要扩大 Phase 5 范围。
四、Schema
新增明确的 Manual Content Request Schema。
不要直接接受任意 dict。
对 content 做合理长度/空值校验，但最终有效正文判断仍以后端 Cleaner 清洗后的结果为准。
五、测试
增加自动化测试，至少覆盖：
- failed Article → manual content 成功
- clean_content 正确持久化
- SHA256 正确
- fetch_status 从 failed → completed
- status 恢复到 processing
- fetch_error 被清空
- ai_status / embedding_status 保持 pending
- Article 404
- 空正文
- 纯空白正文
- 清洗后正文过短
- 无效 manual content 不覆盖旧的有效 clean_content/content_hash
- 有效 manual content 可以替换已有正文
- manual-content 不调用 HttpFetcher
- manual-content 不调用 Playwright
- Phase 0～4 全量回归
自动化测试不要依赖公网。
六、真实 API 验证
实际启动 FastAPI，真实验证一次：
创建一个最终 fetch_status=failed 的 Article
→ POST /api/v1/articles/{id}/manual-content
→ 提交足够长度正文
→ API 成功
→ GET Article Detail
→ 确认 clean_content 已入库
→ 独立重新计算 SHA256
→ 与数据库/API content_hash 一致
→ status / fetch_status / fetch_error 正确
验收数据完成后清理。
七、依赖 / 数据库
原则上 Phase 5 不应新增大型依赖，也不应修改数据库结构。
执行：
- 全量 pytest
- pip check
- alembic current
- alembic check
如果确实必须修改数据库：
- 说明原因
- 新增 migration
- 不允许修改历史 migration
八、本阶段禁止实现
不要实现：
- AI 摘要
- LLM
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
不要进入 Phase 6。
九、完成报告
完成后停止开发并输出完整验收报告，包括：
- 修改/新增文件
- manual-content API 请求/响应
- Manual Content Service 设计
- Cleaner / 最小正文长度如何复用
- content_hash 如何生成
- 已有正文的安全替换策略
- source_type 如何处理及原因
- 成功/失败状态流转
- 自动化测试数量及结果
- Phase 0～4 回归结果
- 真实 API 验证结果
- clean_content/content_hash 入库验证
- pip check
- Alembic 状态
- 是否修改数据库
- Phase 5 checklist
- 明确说明“未进入 Phase 6”
完成后停止，等待人工验收。