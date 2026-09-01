Phase 12 验收报告
Phase 12 已完整完成并通过验收。未进入 Phase 13。
修改/新增文件
修改：
- [articles.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\api\\v1\\articles.py)：新增三个重处理端点
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\services\\article.py)：实现安全重处理和统一状态计算
- [article.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\schemas\\article.py)：新增 reprocess 响应 Schema
- [exceptions.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\exceptions.py)：新增 409、正文无效及 URL 无效异常
新增：
- [test_reprocessing.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_reprocessing.py)：Phase 12 自动化测试
用户已有的 docs/PHASE_12_PROMPT.md 及其他 Phase Prompt 文件未修改。
三个 Endpoint
POST /api/v1/articles/{id}/reprocess
POST /api/v1/articles/{id}/regenerate-ai
POST /api/v1/articles/{id}/regenerate-embedding
均：
- 只操作当前 user_id
- 不创建新 Article
- 保持 Article ID
- 同步执行
- processing 重复请求返回 409
- 404/422 使用统一响应
- Provider 错误不暴露 traceback 或敏感信息
Reprocess 策略
Fetch
→ 计算新 hash
→ AI 结果在内存准备
→ Chunks/Vectors 全部在内存准备
→ 单事务替换正文、AI、Tags、Chunks
开始处理时只修改状态，不清空旧业务数据。
失败保护：
- Fetch 失败：旧正文、AI、Tags、Chunks 全部保留
- AI 失败：新正文不落库，旧 AI、Tags、Embedding 保留
- Embedding 失败：旧正文、AI、Tags、Chunks/Vectors 全部保留
- 数据库保存失败：事务回滚，旧数据保留
content_hash 未变化
当新正文 SHA256 与旧值相同：
- fetch_status=completed
- 跳过 AI
- 跳过 Embedding
- 保留原摘要、标签、Chunks/Vectors
- 返回 content_unchanged=true
- 响应说明正文未变化
Regenerate AI 边界
只执行：
clean_content → LLM → AI fields + Tags
- 不 Fetch
- 不修改 clean_content/content_hash
- 不调用 Embedding
- 不修改 chunks/vectors
- 新 AI 结果和 Tags 在同一事务原子替换
- 失败保留旧摘要、观点、详细摘要和 Tags
- 原有 completed Embedding 保持 completed
Regenerate Embedding 边界
只执行：
clean_content → Token Chunking → Embedding → 原子替换 chunks
- 不 Fetch
- 不调用 LLM
- 不修改正文/hash
- 不修改 AI fields/Tags
- 全部新 vectors 成功后才删除旧 chunks
- 失败时旧 chunks/vectors 完整保留
- 不保存半套结果
状态规则
- 全部阶段 completed：status=completed
- 有有效正文但任一阶段 failed：status=partial_failed
- Fetch 失败且没有有效正文：status=failed
- 任一阶段 processing：status=processing
- partial_failed 阶段重新生成成功后可恢复 completed
- reprocess Embedding 失败时恢复旧 AI 状态，避免把未落库的新 AI 误标 completed
并发与重复请求
使用：
SELECT ... FOR UPDATE
→ 检查 processing
→ 标记当前阶段 processing
→ commit
若 Article 或任一子阶段正在 processing：
HTTP 409
code=40903
没有引入 Redis、分布式锁或任务队列。
自动化测试
Phase 12 新增 25 项测试，覆盖：
- 完整 reprocess
- ID 不变、正文/hash/AI/Embedding 更新
- Fetch、AI、Embedding 失败保护
- hash 未变化跳过处理
- partial_failed 恢复
- regenerate-ai 原子替换和副作用边界
- regenerate-embedding 原子替换和副作用边界
- 旧 vectors 保留及无半套数据
- processing 409
- 404/user_id 隔离
- 无效正文/URL
- 未预期错误安全响应
结果：
- Phase 0～11 基线：167 passed
- 最终全量：192 passed, 1 warning
唯一警告为既有 TestClient/httpx2 弃用提示。
真实 API 验收
测试来源：IANA Example Domains 公开页面。
初始真实 Pipeline：
- HTTP 抓取成功
- 正文长度：700 字符
- LLM 成功
- Embedding 成功
- Chunks：1
- Vector：1024 维
- 最终状态：completed
A. regenerate-ai
结果：
- HTTP 200
- ai_status=completed
- embedding_status=completed
- clean_content/content_hash 不变
- chunks/vector 完全不变
- 新摘要与标签成功持久化
实际摘要：
本文说明了example.com等示例域名的用途、维护依据及使用限制，强调其仅供文档示例使用，不可注册或用于生产环境。

B. regenerate-embedding
结果：
- HTTP 200
- embedding_status=completed
- 旧 Chunk ID 被替换
- 新 Chunk 数量：1
- Vector 维度：1024
- clean_content/content_hash 不变
- AI 摘要、观点和 Tags 不变
C. reprocess
同一稳定 URL 正文 hash 未变化：
- HTTP 200
- content_unchanged=true
- AI/Embedding 被跳过
- Article ID 不变
- 正文/hash/AI/Tags/Chunks/Vectors 均保持不变
- 最终状态仍为 completed
真实 API Key 未输出或记录。
清理与工程检查
临时验收数据：
- Article：已删除
- Chunks：已级联删除
- article_tags：已删除
- 本次新建且未共享的 Tags：已删除
- 残留 Phase 12 Article：0
工程检查：
- pytest：192 passed
- pip check：通过
- alembic current：ad5ad692fa18 (head)
- alembic check：无待生成 migration
- git diff --check：通过
- 新增依赖：无
- 数据库结构/migration：未修改
Phase 12 checklist 全部满足。明确未进入 Phase 13。