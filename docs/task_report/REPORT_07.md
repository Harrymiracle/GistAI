Phase 7 验收报告
Phase 7 本次明确要求的 Tags CRUD 已完整完成，未进入 Phase 8。
修改/新增文件
- [tags.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\tags.py)：四个 Tags API。
- [tag.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\tag.py)：TagService CRUD 业务逻辑。
- [tag.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\schemas\\tag.py)：创建、修改和响应 Schema。
- [exceptions.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\exceptions.py)：Tag 404、409 业务异常。
- [router.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\router.py)：注册 Tags Router。
- [test_tags.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_tags.py)：Phase 7 自动化测试。
没有修改现有 Tag、Article 或 article_tags 数据库结构。
Tags API
已实现：
GET    /api/v1/tags
POST   /api/v1/tags
PATCH  /api/v1/tags/{id}
DELETE /api/v1/tags/{id}
统一返回：
{
  "code": 20000,
  "message": "...",
  "data": {}
}
HTTP 状态：
- 创建成功：201
- 查询、修改、删除成功：200
- Tag 不存在：404，业务码 40402
- Tag 重复：409，业务码 40902
- 名称无效：422
列表按 name ASC, id ASC 稳定排序。没有增加复杂统计或 article_count。
TagService 设计
调用结构：
Router
→ Pydantic Schema
→ TagService
→ SQLAlchemy
→ PostgreSQL
Router 只负责参数、依赖注入、调用 Service 和包装响应。
TagService 负责：
- 当前 user_id 范围内查询。
- 标签创建和重复检查。
- 标签修改和重名检查。
- 标签删除。
- 数据库并发唯一约束冲突转换为安全的 409。
- 数据库异常时回滚事务。
名称规范化与重复处理
名称通过 Pydantic Schema 统一处理：
- 自动 trim 首尾空白。
- 禁止空字符串和纯空白。
- 最大长度 100，与数据库 VARCHAR(100) 一致。
- 同一 user_id + name 不允许重复。
- 创建重复或改名冲突均返回 409，并返回已存在的 tag_id。
- 保持现有数据库的精确名称匹配语义，没有擅自改成大小写不敏感。
Article / Tag 删除行为
删除 Tag 依赖现有数据库外键：
article_tags.tag_id → tags.id ON DELETE CASCADE
实际验证：
- Tag 删除成功。
- 对应 article_tags 自动删除。
- Article 记录仍存在。
- Article 的正文、摘要、状态等数据没有变化。
- Article Detail 仍可正常访问。
- 删除后 Article 的标签列表正确清空。
修改 Tag 名称时，Tag 主键不变，现有 article_tags 关联保持不变。
与 Phase 6 AI 标签兼容性
已验证：
- AI 创建的 Tag 可以通过 GET 查询。
- 可以通过 PATCH 改名。
- 可以通过 DELETE 删除。
- 人工先创建的同名 Tag 会被 AI 复用。
- AI 返回重复标签不会创建重复 Tag 或重复关联。
- Phase 6 原有标签替换、复用和去重逻辑未被修改。
按照本次明确范围，没有提前实现 PUT /articles/{id}/tags、标签筛选或复杂 Tag 搜索。
自动化测试
Phase 7 新增测试：12 个，覆盖：
- 创建 Tag
- 获取列表及稳定排序
- 修改 Tag
- 删除 Tag
- trim
- 空名称、纯空白、超长名称
- 重复创建 409
- rename 重名 409
- PATCH/DELETE 404
- 删除 Tag 级联清除 article_tags
- 删除 Tag 不删除或修改 Article
- AI Tag 通过 CRUD 管理
- 人工标签与 AI 标签复用
结果：
Phase 7 tests: 12 passed
Full pytest:    84 passed
Phase 0～6 的原有 72 个测试全部继续通过。仍只有既存的 FastAPI TestClient/httpx2 弃用提示，不影响功能。
真实 HTTP CRUD 验证
实际启动 Uvicorn，并完成：
GET /health                         → 200
POST /api/v1/tags                   → 201
GET /api/v1/tags                    → 200
PATCH /api/v1/tags/{id}             → 200
GET /api/v1/articles/{id}           → 200
DELETE /api/v1/tags/{id}            → 200
GET /api/v1/articles/{id}           → 200
确认：
- POST 名称成功 trim。
- GET 可以查询到创建的 Tag。
- PATCH 成功改名。
- 改名后 Article 关联仍存在。
- DELETE 后 Tag 和关联均删除。
- Article、正文和摘要保持不变。
- 临时 Article 和 Tag 已全部清理。
- Uvicorn 已正常停止。
依赖、Alembic 与 Git
pip check:       No broken requirements found
alembic current: ad5ad692fa18 (head)
alembic check:   No new upgrade operations detected
git diff --check: 通过
- 未增加依赖。
- 未修改数据库结构。
- 未新增 Alembic migration。
- 工作区中另有既存的 docs/PHASE_7_PROMPT.md 修改，本次未触碰。
Phase 7 Checklist
- GET Tags
- POST Tag
- PATCH Tag
- DELETE Tag
- 当前用户数据隔离
- 名称 trim、空值和长度校验
- 重复名称 409
- Tag 404
- 删除关联但保留 Article
- AI 标签与人工标签共用数据
- Phase 6 AI 标签去重/复用回归
- 全量自动化测试
- 真实 FastAPI HTTP CRUD
- 验收数据清理
- pip、Alembic、Git 验收
未进入 Phase 8。