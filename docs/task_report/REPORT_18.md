Phase 18 已完成，范围严格限定为 Agent Runtime Policy、预算、执行结果、错误分类和终止策略收口；未进入 Task 7，也未提交或推送代码。
核心实现
运行策略现在统一为：
AgentState + AgentLimits
        ↓
AgentRuntimePolicy
        ↓
allowed_actions / termination
新增 [policy.py](E:/practice/projects/GistAI/apps/server/app/agent/policy.py)，集中定义：
MAX_KB_SEARCHES       = 2
MAX_REWRITES          = 1
MAX_WEB_SEARCHES      = 1
MAX_ARTICLE_READS     = 2
MAX_WEB_PAGE_READS    = 2
MAX_STEPS             = 8
allowed_actions 的主要计算已经从 Node 移入纯 Policy；Node 仅保留防御性校验、业务调用、标准化结果和状态更新。Router 仍只根据 next_action 路由。
计数语义
step_count 统计：
- Knowledge Search
- Query Rewrite
- Web Search
- Article Read
- Web Page Fetch
不统计 initialize、Router、状态合并、回答格式化和被程序提前拒绝的请求。
tool_call_counts 只统计真正进入业务 Service 的调用：
- knowledge_search
- web_search
- get_article_content
- fetch_web_page
Query Rewrite 不属于 Tool Call。空结果、超时和执行异常只要实际调用过 Service，均计一次；预算耗尽、非法索引、重复目标和安全校验拒绝不计。
错误与执行结果
在 [schemas.py](E:/practice/projects/GistAI/apps/server/app/agent/schemas.py) 增加了：
- AgentErrorType
- ToolExecutionStatus
- ToolExecutionResult
明确区分：
- Policy/Validation Error：未执行 Tool，不重试、不计数。
- Empty Result：正常调用但无结果，不视为错误。
- Execution Error：Tool 已执行并失败，计一次 Attempt。
- Reasoning Error：结构化决策、改写或回答生成失败，与 Tool Error 分离。
错误状态只保存安全类型和简短描述，不包含原始 Provider 响应、连接串、密钥、堆栈或内部网络信息。
当前不增加 Agent 层重试：
- Policy Error：0 次。
- Empty Result：0 次，由 Agent 决定下一动作。
- Structured Output Error：0 次，Fail Closed。
- Execution Error：不叠加第二套重试；继续复用底层已有策略和 HTTP→Playwright 兜底。
终止与有界性
结束路径覆盖 Answer、Partial、Insufficient、MAX_STEPS、无合法动作、不可恢复 Tool Error、Reasoning Failure 和 Answer Generation Failure。
预算耗尽时：
- 已有可靠选中证据：Partial Answer。
- 没有可靠证据：Insufficient。
- 不使用模型自身知识补充事实。
最坏合法路径为：
KB Search × 2
Query Rewrite × 1
Web Search × 1
Article Read × 2
Web Page Fetch × 2
= 8 steps
所有继续执行类动作都会消耗全局 step，且同时受局部预算限制。达到 8 步后，Policy 只允许回答或终止；提前校验失败则立即进入安全终止。因此任何动作组合都无法无限循环。
采用了轻量 action_history，只记录动作名、step 和结果状态，不保存 Prompt、全文或 Chain of Thought。
Run Reset
每轮新问题会重置查询、证据、全文结果、计数器、预算状态、候选索引、已读 ID、已抓 URL、错误、Tool 结果、动作历史、最终回答和来源。messages 继续作为 conversation-level 状态保留。
文件
新增：
- [policy.py](E:/practice/projects/GistAI/apps/server/app/agent/policy.py)
- [test_agent_runtime_policy.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_runtime_policy.py)
修改：
- [context.py](E:/practice/projects/GistAI/apps/server/app/agent/context.py)
- [graph.py](E:/practice/projects/GistAI/apps/server/app/agent/graph.py)
- [nodes.py](E:/practice/projects/GistAI/apps/server/app/agent/nodes.py)
- [schemas.py](E:/practice/projects/GistAI/apps/server/app/agent/schemas.py)
- [state.py](E:/practice/projects/GistAI/apps/server/app/agent/state.py)
- [test_agent_decision_loop.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_decision_loop.py)
- [test_agent_fulltext_loop.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_fulltext_loop.py)
- [test_agent_web_decision_loop.py](E:/practice/projects/GistAI/apps/server/tests/test_agent_web_decision_loop.py)
验证结果
基线后端：                    278 passed
Agent tests：                 103 passed
Fetch / Extraction：          27 passed
Agent + Semantic + RAG：      145 passed
完整后端：                    295 passed
Frontend production build：   passed
compileall：                  passed
pip check：                   passed
git diff --check：            passed
.env tracked check：          passed（未被跟踪）
最终自审没有剩余 Critical、Important 或 Minor 问题。审查期间发现的 Partial Answer 错误分类丢失问题已经修复并添加回归测试。