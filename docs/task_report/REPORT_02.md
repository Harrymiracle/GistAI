1. Phase 2 是否完成
Phase 2 已完整完成，并已停止开发。未进入 Phase 3。
2. 新增/修改文件
   - [main.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\main.py)：注册 /api/v1 路由和统一异常处理。
   - [deps.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\deps.py)：数据库 Session 与默认用户 user_id=1 依赖。
   - [articles.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\articles.py)：Article CRUD 路由。
   - [router.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\router.py)：API v1 路由聚合。
   - [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\schemas\\article.py)：创建、更新、列表、详情、状态 Schema。
   - [common.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\schemas\\common.py)：统一响应结构。
   - [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\article.py)：Article Service 业务与数据库访问。
   - [exceptions.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\exceptions.py)：404、409 等业务异常。
   - [handlers.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\handlers.py)：参数校验和数据库异常统一处理。
   - [requirements-dev.txt](E:\\practice\\projects\\GistAI\\apps\\server\\requirements-dev.txt)：pytest、httpx 测试依赖。
   - [conftest.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\conftest.py)：真实 PostgreSQL 测试事务和 TestClient。
   - [test_articles.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_articles.py)：Article CRUD 自动化测试。
3. 已实现 API
   - POST /api/v1/articles
   - GET /api/v1/articles
   - GET /api/v1/articles/{id}
   - PATCH /api/v1/articles/{id}
   - DELETE /api/v1/articles/{id}
   - GET /api/v1/articles/{id}/status
列表支持：
- page
- page_size
- favorite
- status
- source_type
- 按 created_at DESC, id DESC 排序
4. 请求/响应示例
创建：
POST /api/v1/articles
Content-Type: application/json

{
  "source_url": "https://example.com/article/1",
  "source_type": "web",
  "title": "示例文章"
}
{
  "code": 20100,
  "message": "Article 创建成功",
  "data": {
    "id": 9,
    "user_id": 1,
    "source_url": "https://example.com/article/1",
    "source_type": "web",
    "title": "示例文章",
    "status": "pending",
    "fetch_status": "pending",
    "ai_status": "pending",
    "embedding_status": "pending"
  }
}
列表：
GET /api/v1/articles?page=1&page_size=20&favorite=true
{
  "code": 20000,
  "message": "Article 列表查询成功",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  }
}
列表项不包含 clean_content。
详情：
GET /api/v1/articles/9
{
  "code": 20000,
  "message": "Article 查询成功",
  "data": {
    "id": 9,
    "clean_content": null,
    "status": "pending"
  }
}
更新：
PATCH /api/v1/articles/9
Content-Type: application/json

{
  "title": "修改后的标题",
  "favorite": true
}
{
  "code": 20000,
  "message": "Article 更新成功",
  "data": {
    "id": 9,
    "title": "修改后的标题",
    "favorite": true
  }
}
状态：
GET /api/v1/articles/9/status
{
  "code": 20000,
  "message": "Article 状态查询成功",
  "data": {
    "id": 9,
    "status": "pending",
    "fetch_status": "pending",
    "ai_status": "pending",
    "embedding_status": "pending",
    "fetch_error": null,
    "ai_error": null,
    "embedding_error": null
  }
}
删除：
DELETE /api/v1/articles/9
{
  "code": 20000,
  "message": "Article 删除成功",
  "data": {
    "article_id": 9
  }
}
5. Article Service 层职责
Service 层负责：
- 默认用户范围内的创建、查询、更新和删除。
- URL 重复检查。
- 初始化四种处理状态。
- 分页、过滤和排序。
- 404 判断。
- 唯一约束并发冲突处理。
- 事务提交、回滚。
- 依赖数据库外键执行级联删除。
Router 仅负责参数解析、调用 Service 和组装响应。
6. URL 校验
使用 Pydantic HttpUrl：
- 仅接受合法 HTTP/HTTPS URL。
- 非法 URL 返回 HTTP 422。
- 返回统一响应 code=42200，包含具体参数错误信息。
- URL 在保存前经过标准化。
7. 重复 URL 处理
创建前按 user_id + source_url 查询；同时捕获数据库唯一约束的并发冲突。
重复时返回：
{
  "code": 40901,
  "message": "Article 已存在",
  "data": {
    "article_id": 9
  }
}
HTTP 状态为 409 Conflict。
8. DELETE 级联验证
测试中实际创建了：
- Article
- 对应 article_tags
- 对应 article_chunks
调用 DELETE 后查询确认：
- article_tags 对应记录数为 0
- article_chunks 对应记录数为 0
清理由 PostgreSQL ON DELETE CASCADE 完成，没有在 Service 中重复实现手工清理。
9. 执行的测试和检查
python -m compileall -q app
python -m pip install -r requirements-dev.txt -i https://mirrors.aliyun.com/pypi/simple/
python -m pip check
python -m pytest -q
alembic current
alembic check
docker compose ps
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
随后使用 Invoke-WebRequest 对运行中的服务执行真实 HTTP 请求。
10. 自动化测试结果
9 passed in 1.08s
覆盖：
- 创建成功
- 非法 URL
- 重复 URL 409
- 分页列表与轻量字段
- 详情及 404
- 更新及 404
- 删除及 404
- 状态及 404
- 外键级联删除
- 数据库异常响应脱敏
存在一条来自新版 Starlette TestClient 的第三方弃用提示，不影响测试结果或运行。
11. 实际 HTTP 验证结果
    - /health：200
    - 创建：201，初始状态 pending
    - 重复创建：409，返回已有 article_id
    - 列表：200，包含新建 Article，不暴露 clean_content
    - 详情：200
    - PATCH：200，标题和收藏状态正确更新
    - status：200，四种状态均为 pending
    - DELETE：200
    - 删除后再次查询：404
验证产生的 Article 已删除，Uvicorn 已正常停止。
12. 数据库结构及 migration
没有修改数据库结构，没有新增 Alembic migration。
Phase 1 已有字段、唯一约束和级联外键足以支持 Phase 2。
13. Alembic 当前状态
ad5ad692fa18 (head)
No new upgrade operations detected.
数据库处于 head，模型与 migration 没有漂移。
14. Phase 1 遗留问题
未发现阻塞 Phase 2 的 Phase 1 遗留问题。PostgreSQL/pgvector 容器保持 healthy。
15. Phase 2 验收 checklist
    - 六个 Article API
    - Service 分层
    - 默认用户可扩展依赖
    - URL 校验
    - 重复 URL 409 与已有 ID
    - 初始状态正确
    - 分页、倒序及简单过滤
    - 列表不返回完整正文
    - PATCH 白名单字段
    - 404 处理
    - 数据库异常不暴露 traceback
    - 外键级联删除
    - 自动化测试
    - 真实 HTTP 验证
    - Alembic head/漂移检查
    - 未实现抓取、AI、Embedding、RAG 等后续能力
16. 阶段边界
Phase 2 已完成，未进入 Phase 3。