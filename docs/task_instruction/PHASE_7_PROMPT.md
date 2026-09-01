请执行 MVP_IMPLEMENTATION_PLAN.md 的 Phase 7，只完成 Tags 管理，不进入 Phase 8。

Phase 0～6 已完成并验收。开始前阅读实施计划和现有 Tag / Article / AI 标签代码，并运行全量测试确认基线。

【目标】

在 Phase 6 已有 tags + article_tags 基础上，实现正式 Tags CRUD：

GET    /api/v1/tags
POST   /api/v1/tags
PATCH  /api/v1/tags/{id}
DELETE /api/v1/tags/{id}

并确保 AI 自动生成标签与人工标签管理使用同一套数据。

【核心规则】

1. Tag 属于 user_id，当前 V1 默认 user_id=1。
2. 同一 user_id 下 tag.name 唯一。
3. Tag 名称必须：
   - trim 首尾空白
   - 非空
   - 符合现有数据库长度限制
4. 创建重复标签返回明确、安全的 409，不产生重复数据。
5. 修改标签名称时同样检查重复。
6. Tag 不存在返回 404。
7. 删除 Tag：
   - 删除对应 article_tags 关联
   - 不删除 Article
   - 不影响 Article 正文、摘要等数据
8. AI Phase 6 创建的标签必须可以通过这些 API 查询、修改和删除。
9. 不允许为了 Tags CRUD 破坏 Phase 6 的 AI 标签复用/去重逻辑。

【GET /tags】

返回当前用户标签列表。

建议至少包含：
- id
- name
- created_at
- updated_at

可以增加 article_count，如果实现简单且无需复杂重构；否则不要提前扩展。

排序保持稳定、合理，并在报告中说明。

【POST /tags】

请求：

{
  "name": "人工智能"
}

成功创建 Tag。

重复名称 → HTTP 409。

【PATCH /tags/{id}】

允许修改 name。

要求：
- trim
- 非空
- 重名冲突 → 409
- 不存在 → 404
- 修改 Tag 名称后现有 article_tags 关联保持不变

【DELETE /tags/{id}】

删除 Tag 及 article_tags 关系。

必须验证：
Tag 删除后 Article 仍存在且其他字段不受影响。

【架构】

保持：

Router
→ TagService
→ SQLAlchemy
→ PostgreSQL

业务逻辑不要全部写在 Router。

复用现有 Model、异常体系、统一 API Response 和 user_id 语义。

原则上不修改数据库结构。

【测试】

自动化测试不要依赖公网或真实百炼 API。

至少覆盖：

- 创建 Tag
- 获取 Tag 列表
- 修改 Tag
- 删除 Tag
- 404
- 空名称
- trim
- 重复创建 → 409
- rename 重名 → 409
- 删除 Tag 后 article_tags 被清除
- 删除 Tag 不删除 Article
- AI 已生成 Tag 可通过 Tags API 管理
- Phase 6 AI 标签去重/复用行为不被破坏
- Phase 0～6 全量回归

测试中继续 Mock AI，不消耗真实 Token。

【验收】

完成后：

- 全量 pytest
- pip check
- alembic current
- alembic check
- git diff --check

再实际启动 FastAPI 做一次真实 HTTP CRUD：

创建 Tag
→ GET 确认存在
→ PATCH 改名
→ 建立/确认 Article 关联
→ DELETE Tag
→ 确认关联删除但 Article 仍存在

清理验收数据。

【禁止】

本阶段不要实现：

- Chunk
- Embedding
- Keyword Search
- Semantic Search
- RAG
- Tag 搜索/复杂统计
- 前端 Tags 页面
- BackgroundTasks
- Redis/Celery
- 登录系统

不要进入 Phase 8。

【完成报告】

完成后停止并报告：

- 修改/新增文件
- Tags API
- TagService 设计
- 名称规范化和重复处理
- Article/Tag 删除关联行为
- 与 Phase 6 AI 标签的兼容性
- 自动化测试及 Phase 0～6 回归结果
- 真实 HTTP CRUD 验证
- pip / Alembic / git diff 状态
- 是否修改数据库
- Phase 7 checklist
- 明确说明未进入 Phase 8

完成后停止，等待人工验收。