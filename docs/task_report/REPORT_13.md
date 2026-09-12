Phase 13 Agent 基础骨架已完成，严格限定在文档范围内。
修改文件
- [requirements.txt](E:/practice/projects/GistAI/apps/server/requirements.txt)：增加 langgraph>=1.2.0,<2.0.0
- [agent/__init__.py](E:/practice/projects/GistAI/apps/server/app/agent/__init__.py)：Agent 模块入口
- [schemas.py](E:/practice/projects/GistAI/apps/server/app/agent/schemas.py)：定义 AgentAction、EvidenceStatus
- [state.py](E:/practice/projects/GistAI/apps/server/app/agent/state.py)：定义完整 AgentState
- [nodes.py](E:/practice/projects/GistAI/apps/server/app/agent/nodes.py)：实现 initialize 和 finish
- [graph.py](E:/practice/projects/GistAI/apps/server/app/agent/graph.py)：创建并编译最小 StateGraph
- [test_agent_graph.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_graph.py)：Graph、State、checkpoint 测试
Graph 调用链
START
→ initialize
→ finish
→ END
initialize 读取最新用户消息，初始化原始查询、当前查询、控制计数器和空结果字段；finish 写入 smoke-test 占位回答，不调用 LLM 或业务服务。
AgentState
目前包含：
- 消息与查询：messages、original_query、current_query
- 意图控制：intent、allow_web、requires_freshness
- 后续结果接口：知识库、Web、文章和网页内容
- 证据状态：选中证据、状态和原因
- 流程控制：rewrite/step/tool 计数、允许动作、下一动作
- 错误、最终回答和来源
Checkpoint
每个 create_agent_graph() 创建独立的 InMemorySaver，在 compile(checkpointer=...) 时接入。调用方通过以下配置传递线程标识：
{"configurable": {"thread_id": "..."}}
测试验证了相同 thread_id 下消息累积、首个 original_query 保留、后续 current_query 更新以及 get_state() 快照读取。
验证结果
- Agent 定向测试：3 passed
- 相关核心回归：40 passed
- 完整后端测试：195 passed in 27.43s
- 前端 TypeScript/Vite 生产构建：通过
- Agent 模块编译检查：通过
- git diff --check：通过
- LangGraph 实际安装版本：1.2.11
- .env 未被跟踪，仅 .env.example 在 Git 中
- 测试用 PostgreSQL 容器已停止，未删除数据卷
本次没有实现 Web Search、Knowledge Search、Query Rewrite、Evidence Evaluation、Agent Loop、PostgreSQL checkpoint、fetch_web_page 或 save_to_knowledge_base，也没有修改现有 RAG、API、数据库及 Service 主链路。
当前修改保留在 main 工作区，尚未提交或推送。