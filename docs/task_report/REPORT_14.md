Phase 14 Task 2 已完成，未提前扩展 Task 3。
修改与新增文件
- [schemas.py](E:/practice/projects/GistAI/apps/server/app/agent/schemas.py)：新增 KnowledgeSearchInput、KnowledgeSearchResult
- [context.py](E:/practice/projects/GistAI/apps/server/app/agent/context.py)：定义不进入 checkpoint 的运行时依赖
- [knowledge_search.py](E:/practice/projects/GistAI/apps/server/app/agent/knowledge_search.py)：新增 Semantic Search 薄适配服务
- [nodes.py](E:/practice/projects/GistAI/apps/server/app/agent/nodes.py)：实现 knowledge_search Node
- [graph.py](E:/practice/projects/GistAI/apps/server/app/agent/graph.py)：接入新 Node 和运行时 Context
- [test_agent_graph.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_graph.py)：适配新 Graph，并验证跨调用计数
- [test_agent_knowledge_search.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_knowledge_search.py)：覆盖输入、结果、错误、计数与集成
Semantic Search 复用链路
knowledge_search Node
→ KnowledgeSearchService
→ SearchService.semantic_search
→ Query Embedding
→ PostgreSQL pgvector 查询
没有在 Agent 层复制向量检索、阈值过滤、用户隔离或文章去重逻辑。数据库 Session、用户 ID、Embedding Service 和 threshold 均由外部注入，Service 不负责创建、提交或关闭 Session。
当前 Graph
START
→ initialize
→ knowledge_search
→ finish
→ END
仍为普通 Edge，没有条件分支。
输入与结果
query 来自 state["current_query"]。
top_k 通过运行时 AgentContext 传入，默认值为 5，并由 Pydantic 强制限制在 1～10。非法参数在调用 Service 前失败，因此不会计入 Tool Call。
threshold 由程序构建 KnowledgeSearchService 时注入，继续使用现有 settings.rag_similarity_threshold，不允许 Agent 或 LLM 动态指定。
写入 kb_results 的每项包含：
article_id
chunk_id
title
chunk_text
score
空结果与错误
- 正常无命中：kb_results=[]，last_tool_error=None
- 执行异常：清空 kb_results，写入类似 Knowledge Search 执行失败（TimeoutError）
- 不保存底层异常原文，避免连接信息或密钥泄漏
- 异常路径会清除同线程中可能残留的旧候选证据
每次真正调用 Knowledge Search，无论成功、空结果或异常：
step_count += 1
tool_call_counts["knowledge_search"] += 1
计数可通过 In-memory checkpoint 跨同一 thread_id 累积。
验证结果
- Agent 定向测试：9 passed
- Agent + Semantic Search + RAG：51 passed
- 完整后端测试：201 passed
- 前端生产构建：通过
- Agent 模块编译：通过
- git diff --check：无错误
- 独立代码审阅：无 Critical 或 Important 问题
- .env 未被跟踪
- 测试数据库容器已停止，未删除数据卷
本次没有实现 Query Rewrite、Evidence Evaluation、Conditional Edge、Agent Loop、Web Search、fetch_web_page、get_article_content Agent Tool、save_to_knowledge_base 或 PostgreSQL checkpoint。
修改当前保留在 main 工作区，尚未提交或推送。