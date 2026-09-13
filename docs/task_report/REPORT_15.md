Phase 15 已实现完成，并停在文档规定范围内。独立代码审查结论：Ready to merge。
1. 架构
START
  → initialize
  → knowledge_search
  → evaluate_and_decide
      ├─ ANSWER → generate_answer → END
      ├─ REWRITE_QUERY → rewrite_query → knowledge_search
      └─ INSUFFICIENT → insufficient_answer → END
2. 主要改动
- 新增 [reasoning.py](E:/practice/projects/GistAI/apps/server/app/agent/reasoning.py)，统一处理结构化决策、查询改写和证据回答。
- 扩展 [schemas.py](E:/practice/projects/GistAI/apps/server/app/agent/schemas.py)，加入 PARTIAL、AgentDecision 和严格证据索引。
- 更新 [context.py](E:/practice/projects/GistAI/apps/server/app/agent/context.py)，通过 Runtime Context 注入推理服务。
- 更新 [nodes.py](E:/practice/projects/GistAI/apps/server/app/agent/nodes.py) 和 [graph.py](E:/practice/projects/GistAI/apps/server/app/agent/graph.py)，实现条件路由和有界循环。
- 新增完整决策循环及推理服务测试。
3. 状态生命周期
每次同线程的新问题都会重置所有 Run-level State，包括查询、证据、计数器、动作和错误；messages 继续通过 checkpoint 累积用户与助手消息。
4. Decision 与 Rewrite
- allowed_actions 完全由程序生成。
- LLM 的结构化结果经过 Pydantic 和程序规则双重校验。
- Rewrite 只修改 current_query，保留 original_query。
- 最大改写次数硬编码为一次，并在决策和 Rewrite 节点双重限制。
- Rewrite 计入 step_count，但不计入外部 Tool 的 tool_call_counts。
5. Evidence 与回答
- 模型只选择结果索引，selected_evidence 由程序从 kb_results 构造。
- Answer 只接收选中的证据。
- Partial Answer 自动附加未覆盖内容说明。
- sources 由程序生成，仅包含实际使用证据的 article_id、chunk_id 和 title。
6. 安全终止
以下情况都会安全结束，不会继续循环：
- 改写次数耗尽
- Knowledge Search 异常
- Rewrite 或 Answer 服务异常
- 非法 AgentAction
- 畸形结构化输出
- 无效或越界证据索引
- 无可靠证据
异常详情不会进入最终回答。
7. 验证结果
- Agent tests：26 passed
- Agent + Semantic Search + RAG：68 passed
- Full backend：218 passed
- Frontend build：passed
- Python compileall：passed
- pip check：No broken requirements found
- git diff --check：passed
- 独立代码审查：无 Critical / Important 问题
8. 明确未实现
未实现 Web Search、fetch_web_page、get_article_content Agent Tool、save_to_knowledge_base、PostgreSQL checkpoint、Long-term Memory、Multi-Agent 或后续阶段功能。
代码当前尚未提交 Git。