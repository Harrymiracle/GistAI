Phase 20 已完成。GistAI Stage 10 Agent V1 开发阶段完成，未进入 Task 9 或其他扩展范围。
1. 修改 / 新增文件
后端核心：
- [checkpoint.py](E:/practice/projects/GistAI/apps/server/app/agent/checkpoint.py)：PostgreSQL Checkpointer、连接池、日志脱敏、setup 串行锁
- [graph.py](E:/practice/projects/GistAI/apps/server/app/agent/graph.py)：支持注入 Checkpointer，测试默认保留 InMemory
- [nodes.py](E:/practice/projects/GistAI/apps/server/app/agent/nodes.py)：避免完整文章和网页正文进入 checkpoint
- [deps.py](E:/practice/projects/GistAI/apps/server/app/api/deps.py)：从应用生命周期获取 Agent Chat Service
- [main.py](E:/practice/projects/GistAI/apps/server/app/main.py)：FastAPI lifespan 管理 pool、Graph 和 Service
- [agent.py](E:/practice/projects/GistAI/apps/server/app/api/v1/agent.py)：异常日志仅记录类型，不记录敏感详情
- [requirements.txt](E:/practice/projects/GistAI/apps/server/requirements.txt)：新增官方 PostgreSQL checkpoint 依赖
测试：
- [test_agent_checkpoint.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_checkpoint.py)
- [test_agent_fulltext_loop.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_fulltext_loop.py)
- [test_agent_graph.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_graph.py)
- [test_agent_api.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_api.py)
配置与文档：
- [.env.example](E:/practice/projects/GistAI/.env.example)
- [README.md](E:/practice/projects/GistAI/README.md)
前端代码没有改动，API Contract 保持 Phase 19 兼容。
2. Checkpoint Architecture
Frontend thread_id
        ↓
POST /api/v1/agent/chat
        ↓
current_user_id + thread_id
        ↓
AgentChatService
        ↓
LangGraph
        ↓
PostgreSQL PostgresSaver
公开 UUID 不变，内部 checkpoint key 仍为：
user_id:thread_id
生产环境不再使用模块级 InMemorySaver。
3. Lifecycle
- FastAPI 启动时建立一个应用级 psycopg 连接池。
- 连接池大小为 1～5，启动等待上限 10 秒。
- Checkpointer、Graph 和 AgentChatService 均按应用级复用，不会每请求或每 Node 创建。
- FastAPI shutdown 时关闭连接池。
- 单元测试调用 create_agent_graph() 时仍可使用 InMemorySaver。
实现遵循官方生产环境使用 PostgresSaver 的方式。LangGraph persistence 文档
4. Schema Setup
启动时调用官方 PostgresSaver.setup()，由官方组件维护：
- checkpoint_migrations
- checkpoints
- checkpoint_blobs
- checkpoint_writes
没有增加业务 Alembic migration，因为这些不是 Article、Chunk 或 Chat 产品表，而是 LangGraph 自己的运行状态表。
为防止多个进程首次启动时同时执行 migration，setup() 被 PostgreSQL advisory lock 串行保护。连接启用了官方要求的 autocommit=True、prepare_threshold=0 和 dict_row。官方 PostgreSQL Checkpointer README
5. User Isolation
相同公开 UUID 在不同用户下会映射为不同 key：
61:thread-uuid
62:thread-uuid
测试确认二者不会共享 messages 或其他 checkpoint 状态。客户端仍不能传入 user_id。
6. Persistence
真实 PostgreSQL 集成测试完成了：
Pool / Saver / Graph A
→ 第一问写入 checkpoint
→ 全部关闭

新 Pool / Saver / Graph B
→ 相同用户和 thread_id
→ 恢复第一问及回答
→ 完成追问
最终 messages 顺序正确，共四条，证明不是依赖原进程对象复用。
7. Run Reset
同一 conversation 的下一轮中：
- messages 跨轮保留
- original_query 和 current_query 更新为新问题
- step_count 从当前 Run 重新计算
- tool_call_counts 重置
- evidence、sources、错误、动作历史、读取记录均重置
- 旧回答来源不会污染新回答
集成测试确认追问后的 step_count == 1。
8. Checkpoint Size
完整 article_contents 和 web_page_contents 不再写入任一 checkpoint：
读取完整正文
→ Node 局部变量
→ FullTextEvidenceSelector
→ 保留有界 selected evidence
→ 丢弃完整正文
知识库与 Web 两条全文路径均检查了完整 state history。运行时 Service、数据库 Session、Crawler、API Key 等也不会进入 AgentState。
9. Failure Behavior
PostgreSQL 不可用时：
- 应用启动明确失败
- 不会静默退回 InMemory
- 对外只提供安全错误
- psycopg pool 日志经过过滤，不记录主机、用户、连接串、SQL 或原始异常
- Agent API 意外异常也只记录异常类型
10. Dependencies
新增或调整：
- langgraph-checkpoint-postgres>=3.1.2,<4.0.0
  - 实际安装：3.1.2
- psycopg[binary,pool]>=3.2.0,<4.0.0
  - psycopg：3.3.4
  - psycopg-pool：3.3.1
严格 MessagePack 反序列化通过显式 Serializer 配置启用，不依赖本机环境变量。
11. Testing
- Agent tests：116 passed
- Agent API tests：6 passed
- Checkpoint integration：5 passed
- Semantic / RAG / Fetch：69 passed
- Full backend：308 passed
- Frontend tests：未配置
- Frontend production build：通过
- Python compileall：通过
- pip check：通过，无损坏依赖
- git diff --check：通过
Checkpoint 集成测试会在本机 PostgreSQL 上创建唯一的：
gistai_checkpoint_test_<uuid>
测试完成后终止相关连接并删除整个临时数据库，不会向业务数据库写入 checkpoint 测试数据。
12. Final E2E Scenarios
- KB-only：通过
- Query Rewrite：通过，最多一次
- Fresh / Web：通过，时效问题要求 Web Evidence
- Web Full-text：通过
- KB Full-text：通过
- Partial：通过
- Insufficient：通过
- Budget Exhaustion：通过，最多 8 步并安全结束
- Tool Error：通过，分类正确且不泄露详情
- Conversation Follow-up：通过
- Process Recreation：通过，跨 Pool/Saver/Graph 恢复
外部服务场景使用可控测试替身验证，没有读取或输出 .env 中的真实密钥。
13. Final Code Review
独立审查发现的三项 Important 问题均已修复并复审：
- setup 多进程竞态：已修复
- 测试数据库隔离不足：已修复
- psycopg pool 原始错误日志风险：已修复
- Web 全文 checkpoint 测试缺口：已补齐
最终结论：
- Critical：无
- Important：无
- Minor：无
- Ready to merge：Yes
14. V1 已实现能力
- Knowledge Ingestion
- 正文提取与清洗
- AI Summary / Tags
- Vector Search
- RAG
- Agent Decision Loop
- Query Rewrite
- Controlled Web Search
- KB / Web Full-text Reading
- Evidence Grounding
- Runtime Policy 与固定 Tool Budget
- Safe Error / Partial / Insufficient
- Persistent PostgreSQL Conversation Checkpoint
- 用户隔离
- Agent HTTP API
- Frontend Chat MVP
15. V1 未实现能力
严格未实现：
- Long-term Memory
- 跨 conversation Memory
- Conversation History/List/Rename/Delete UI
- Streaming、SSE、WebSocket
- save_to_knowledge_base
- 自动保存 Web 内容
- Multi-Agent
- Planner / Reflection
- Reranker
- Task 9 及后续功能