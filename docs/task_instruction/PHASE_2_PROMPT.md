请继续执行 MVP_IMPLEMENTATION_PLAN.md 中的 Phase 2。
只执行 Phase 2：Article CRUD。
不要进入 Phase 3，不要实现网页抓取、Playwright、AI 摘要、Embedding、RAG 等后续功能。
开始前：
1. 阅读当前项目代码和 MVP_IMPLEMENTATION_PLAN.md。
2. 确认 Phase 1 已完成，并基于现有数据库模型继续开发。
3. 不要破坏 Phase 0 / Phase 1 已经通过的功能和数据库结构。
4. 如果实施计划与当前代码存在小的实现差异，以已经确认的产品设计和现有数据库结构为基础，说明后再处理，不要擅自扩大需求。
【Phase 2 目标】
完成 Article 的基础 CRUD API，为后面的“URL → 抓取 → AI 处理”提供文章数据基础。
本阶段只处理 Article 基础业务，不实现真正的文章抓取和 AI 处理。
一、实现 API
按照现有 /api/v1 版本规范，实现：
1. POST /api/v1/articles
   创建 Article
2. GET /api/v1/articles
   获取 Article 列表
3. GET /api/v1/articles/{id}
   获取 Article 详情
4. PATCH /api/v1/articles/{id}
   修改允许修改的 Article 字段
5. DELETE /api/v1/articles/{id}
   删除 Article
6. GET /api/v1/articles/{id}/status
   获取 Article 当前处理状态
二、POST /articles 创建规则
V1 暂时没有登录系统：
user_id 固定使用默认用户 1，但代码结构不要写成未来完全无法扩展用户体系的形式。
创建 Article 时至少支持：
- source_url
- source_type
根据当前数据库模型及实施计划处理其他必要字段。
要求：
1. 后端必须校验 URL。
2. URL 非法时返回明确的 4xx 错误。
3. 同一个 user_id + source_url 不允许重复。
4. 如果 URL 已存在：
   - 返回 HTTP 409
   - 明确告诉调用方 Article 已存在
   - data 中尽可能返回已有 article_id，方便前端未来实现“使用已有文章 / 重新提取”
5. 本阶段创建 Article 后不要真的抓取网页。
6. 不调用 Playwright。
7. 不调用 LLM。
8. 不生成 Embedding。
Article 创建后的初始状态按照现有状态设计正确设置。
三、GET /articles 列表
实现基础文章列表查询。
至少支持：
- 分页
- 按 created_at 倒序
如果实施计划已经明确以下简单过滤条件并且当前模型支持，可以实现：
- favorite
- status
- source_type
不要为了 Phase 2 自行扩展复杂搜索系统。
关键词搜索属于后续 Phase。
重要：
Article 列表接口不要返回完整 clean_content。
列表只返回列表页面真正需要的轻量字段，例如：
- id
- title
- source_url
- source_type
- source_name
- one_sentence_summary
- favorite
- status
- fetch_status
- ai_status
- embedding_status
- created_at
- updated_at
具体字段以现有数据库模型为准。
四、GET /articles/{id} 详情
返回 Article 完整详情。
详情可以包含 clean_content 以及当前数据库中 Article 已存在的其他详情字段。
Article 不存在时返回 HTTP 404。
五、PATCH /articles/{id}
只允许修改合理的用户可编辑字段。
不要允许客户端通过 PATCH 随意修改：
- id
- user_id
- content_hash
- created_at
- 系统内部处理状态
- error 字段
favorite 等合理字段可以修改。
如果当前产品设计中 title 等字段允许用户修改，可以按照实施计划处理。
使用 Pydantic Schema 明确控制允许更新的字段，不要直接接受任意 dict。
六、DELETE /articles/{id}
删除 Article。
要求：
1. Article 不存在返回 404。
2. 删除 Article 时确认数据库外键级联规则正确工作。
3. 与 article_tags 的关系正确清理。
4. article_chunks 应随 Article 删除。
5. 不要手工写一堆可以由数据库 FK cascade 完成的重复逻辑。
七、GET /articles/{id}/status
返回当前 Article 的：
- status
- fetch_status
- ai_status
- embedding_status
- fetch_error
- ai_error
- embedding_error
如果 Article 不存在返回 404。
这个接口后面会用于前端轮询文章处理状态。
八、代码结构要求
继续保持分层。
建议按照当前项目结构合理组织：
router
↓
schema
↓
service
↓
model / database
业务逻辑放 Service 层。
Router 只负责：
- 接收请求
- 参数解析
- 调用 Service
- 返回响应
不要把 Article CRUD 的主要业务逻辑全部堆在 router。
数据库访问方式保持与 Phase 1 当前 SQLAlchemy 2.x 风格一致。
九、统一响应结构
继续遵守项目约定：
{
"code": ...,
"message": "...",
"data": ...
}
同时正确使用 HTTP Status Code。
例如：
200：查询/更新成功
201：创建成功
404：Article 不存在
409：URL 重复
422 或合适的 4xx：参数/URL 校验失败
不要为了统一 code 而把所有 HTTP 状态都返回 200。
十、异常处理
本 Phase 至少实际验证：
1. 正常创建 Article
2. 非法 URL
3. 重复 URL
4. 查询存在的 Article
5. 查询不存在的 Article
6. Article 列表
7. 修改 Article
8. 修改不存在的 Article
9. 删除 Article
10. 删除不存在的 Article
11. 查询 status
12. 数据库异常不会直接把 Python traceback 暴露给 API 用户
十一、测试要求
为 Article CRUD 添加必要的自动化测试。
测试至少覆盖：
- create success
- invalid URL
- duplicate URL -> 409
- list
- detail
- detail 404
- patch
- delete
- status
如果当前项目已经有测试框架，沿用现有测试框架。
如果没有，选择与 FastAPI 项目匹配的轻量测试方式，不要引入复杂测试基础设施。
除了自动化测试，还要实际启动 FastAPI，对核心 API 做一次真实请求验证。
不能只说“代码看起来没问题”。
十二、数据库要求
Phase 1 的数据库结构原则上不要随意修改。
如果 Phase 2 确实发现 Schema/约束存在必须修正的问题：
1. 先说明原因。
2. 必须通过新的 Alembic migration 修改。
3. 不允许直接手改已经执行过的旧 migration 来伪造历史。
4. 修改后重新验证 alembic current/head。
如果不需要修改数据库，则不要为了 Phase 2 无意义生成 migration。
十三、本 Phase 明确禁止
不要实现：
- 网页 HTTP 抓取
- Playwright
- 微信文章特殊处理
- 手动正文兜底
- LLM
- AI 摘要
- AI 标签生成
- Embedding
- Chunk
- Semantic Search
- RAG
- SSE
- WebSocket
- BackgroundTasks
- Redis
- Celery
- RabbitMQ
- Kafka
- Elasticsearch
- Qdrant
- 登录/注册
- n8n
这些属于后续 Phase。
十四、Phase 2 完成后的验收报告
完成后请停止开发，不要进入 Phase 3。
输出：
1. Phase 2 是否完整完成
2. 新增/修改了哪些文件，以及各文件作用
3. 实现了哪些 API
4. 每个 API 的请求/响应示例
5. Article Service 层做了什么
6. URL 校验如何实现
7. 重复 URL 如何处理
8. DELETE 的级联删除如何验证
9. 执行了哪些测试
10. 自动化测试结果
11. 实际 HTTP 请求验证结果
12. 是否修改数据库结构 / 是否新增 Alembic migration
13. alembic 当前状态
14. 是否发现 Phase 1 遗留问题
15. Phase 2 验收 checklist
16. 明确说明“未进入 Phase 3”
完成报告后停止，等待人工验收。