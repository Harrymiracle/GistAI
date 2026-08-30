请继续执行 MVP_IMPLEMENTATION_PLAN.md 中的 Phase 1。
只执行 Phase 1，不要进入 Phase 2。
目标：
1. 在 FastAPI 后端接入 SQLAlchemy 2.x。
2. 配置 PostgreSQL 数据库连接。
3. 接入 Alembic。
4. 创建以下核心数据表：
   - articles
   - tags
   - article_tags
   - article_chunks
5. 启用 pgvector 扩展。
6. article_chunks.embedding 使用 VECTOR(1024)。
7. 按实施计划创建必要的主键、外键、唯一约束和索引。
8. 生成并执行 Alembic migration。
9. 验证数据库表、索引、外键、pgvector 均正常。
10. 不实现 Article CRUD，不写抓取逻辑，不调用 AI，不进入 Phase 2。
请继续遵守之前约定：
- 业务逻辑放 Service 层，不堆在 router。
- 不引入 Redis、Celery、RabbitMQ、Kafka、Elasticsearch、Qdrant、n8n。
- 不写登录系统。
- 不提交任何真实 API Key。
- 每完成一个阶段必须实际运行和验证。
完成后请输出：
1. 修改/新增了哪些文件
2. 数据库表结构
3. 执行过的命令
4. 测试/验收结果
5. 是否满足 Phase 1 全部验收标准
6. 停止，不要进入 Phase 2