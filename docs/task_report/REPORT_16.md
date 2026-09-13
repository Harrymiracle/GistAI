Phase 16 已完成，范围严格限定为受控只读 Web Search；未提交 Git commit，改动保留在当前 task04 工作区。
1. 修改／新增文件
- [.env.example](E:\\practice\\projects\\GistAI.env.example)：增加通用 Web Search 配置模板，未写入真实密钥。
- [schemas.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\agent\\schemas.py)：新增搜索输入、结果、Intent 和 Web Evidence 索引 Schema。
- [state.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\agent.py)：收紧 Intent 类型，承载 Web 结果与控制状态。
- [context.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\agent\\context.py)：通过 Runtime Context 注入 Web Search Service。
- [web_search.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\agent\\web_search.py)：新增厂商无关 Service、Provider 协议及 Tavily 适配器。
- [reasoning.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\agent\\reasoning.py)：增加结构化 Intent 分类，分别评估 KB 与 Web Evidence，并强化摘要 grounding。
- [nodes.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\agent\\nodes.py)：增加初始意图决策、Web Search 节点、动作策略和单次预算。
- [graph.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\agent\\graph.py)：接入 initial_decision 和 web_search 路由。
- [config.py](E:\\practice\\projects\\GistAI\\apps\\server\\app\\core\\config.py)：增加 Base URL、API Key、超时和结果数配置。
- [deps.py](E:\\practice\\projects\\GistAI\\apps\\server\\Projects\\GistAI\\apps\\server\\app\\api\\deps.py)：集中组装 Tavily Provider 与通用 Service。
- [test_agent_intent.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_agent_intent.py)：覆盖硬规则与结构化分类。
- [test_agent_web_search.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_agent_web_search.py)：覆盖 Service、Tavily 映射、配置和错误处理。
- [test_agent_web_decision_loop.py](E:\\practice\\projects\\GistAI\\apps\\server\\tests\\test_agent_web_decision_loop.py)：覆盖 Phase 16 的 11 条主要路径。
- 既有 Agent graph、knowledge search、reasoning 和 decision-loop 测试已同步适配新协议。
2. Web Search Provider
调用结构为：
Agent Node
→ WebSearchService
→ WebSearchProvider Protocol
→ TavilyWebSearchProvider
业务图不直接依赖 Tavily。以后替换搜索服务，只需实现 WebSearchProvider 并调整依赖组装，不需要修改 Graph、Node 或 Evidence Schema。
配置使用：
WEB_SEARCH_BASE_URL
WEB_SEARCH_API_KEY
WEB_SEARCH_TIMEOUT_SECONDS
WEB_SEARCH_MAX_RESULTS
真实密钥只会在运行时从本机 .env 加载；本次未读取、输出或提交真实密钥。
3. 最终 Graph
START
→ initialize
→ initial_decision
→ knowledge_search
→ evaluate_and_decide
   ├─ ANSWER → generate_answer → END
   ├─ REWRITE_QUERY → rewrite_query → knowledge_search
   ├─ WEB_SEARCH → web_search → evaluate_and_decide
   └─ INSUFFICIENT → insufficient_answer → END
4. Intent
- 明确“只根据我的知识库／我保存的文章”等请求：allow_web=False。
- 明确“最新版本／当前状态／最近进展”等时效语义：requires_freshness=True。
- 普通或含糊请求交给结构化 LLM 分类，不仅依赖关键词。
- 分类失败时安全降级为仅知识库，不擅自联网。
5. allowed_actions
WEB_SEARCH 只在以下条件同时满足时出现：
- allow_web=True
- 没有工具执行错误
- 本轮 Web Search 调用次数小于 1
时效性问题在没有可用 Web Evidence 时不能仅凭旧 KB Evidence 回答。
6. Budget
MAX_WEB_SEARCHES = 1，采用双层硬限制：
- _allowed_actions 在预算耗尽后移除 WEB_SEARCH。
- web_search 节点再次检查权限和调用次数。
即使 LLM 重复要求搜索，也只可能真正调用一次。
7. Evidence
- KB 和 Web Evidence 分别进入 Decision Prompt。
- 分别使用 selected_result_indexes 和 selected_web_result_indexes。
- 内部选中证据带 source_type。
- Web snippet 明确标记为弱／初步证据，禁止假装读取网页全文。
8. Sources
- 原有 KB Source 格式保持不变：article_id、chunk_id、title。
- Web Source 输出真实的 title、url、source、published_at，并带 source_type="web"。
9. Error
- Empty Result：web_results=[]、last_tool_error=None。
- Execution Error：记录安全错误类型，计入调用次数，不泄露响应、密钥或连接信息。
- Illegal WEB_SEARCH：决策校验失败并安全结束，Provider 不调用。
- Budget Exhausted：动作从白名单移除，节点仍有最终防护。
10. 验证结果
- Agent tests：62 passed
- Agent + Semantic Search + RAG：104 passed
- Full backend：254 passed
- Frontend production build：passed
- Python compileall：passed
- pip check：passed，No broken requirements found
- git diff --check：passed，仅有 Windows CRLF 提示
- 最终代码复审：无 Critical、无 Important，批准合入
11. 明确未实现
未提前实现：
- fetch_web_page
- get_article_content Agent Tool
- save_to_knowledge_base
- PostgreSQL checkpoint
- Long-term Memory
- Multi-Agent
- 复杂重试框架
- 全文抓取或 Tavily raw content/answer 功能