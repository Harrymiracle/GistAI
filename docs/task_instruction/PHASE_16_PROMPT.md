你现在要继续在现有 **GistAI / AI 阅读助手** 项目中完成 Stage 10 Agent V1 的第四批开发任务。

Phase 15 / Task 3 已完成。

当前 Agent Graph 已具备：

```text
START
→ initialize
→ knowledge_search
→ evaluate_and_decide
    ├─ ANSWER → generate_answer → END
    ├─ REWRITE_QUERY → rewrite_query → knowledge_search
    └─ INSUFFICIENT → insufficient_answer → END
```

当前已有能力：

* Conversation-level / Run-level State 区分
* Knowledge Search
* Evidence Evaluation
* Structured Decision
* `allowed_actions`
* Conditional Edge
* 最多一次 Query Rewrite
* Answer / Partial / Insufficient
* Safe Termination
* InMemory checkpoint
* Runtime Context
* 自动化测试

当前完整后端测试基线：

```text
218 passed
```

---

# 一、本次任务目标

本次只实现：

> **Task 4：把 Web Search 作为受控只读 Tool 接入现有 Agent Decision Loop。**

目标不是简单增加一个搜索函数，而是让 Agent 能够根据：

```text
用户意图
+
本地知识库证据
+
当前 allowed_actions
+
Web 使用权限
```

决定：

```text
是否需要 Web Search
```

---

# 二、目标 Graph

目标结构建议如下：

```text
START
↓
initialize
↓
knowledge_search
↓
evaluate_and_decide
   │
   ├─ ANSWER
   │    ↓
   │ generate_answer
   │    ↓
   │   END
   │
   ├─ REWRITE_QUERY
   │    ↓
   │ rewrite_query
   │    ↓
   │ knowledge_search
   │    ↓
   │ evaluate_and_decide
   │
   ├─ WEB_SEARCH
   │    ↓
   │ web_search
   │    ↓
   │ evaluate_and_decide
   │
   └─ INSUFFICIENT
        ↓
      insufficient_answer
        ↓
       END
```

本 Task 可以允许：

```text
KB Search
→ Rewrite KB Query
→ KB Search
→ Web Search
→ Evaluate
→ Answer / Partial / Insufficient
```

但必须保持有界。

---

# 三、严格任务边界

本次不要实现：

* `fetch_web_page`
* 外部网页全文抓取
* `get_article_content` Agent Tool
* 保存 Web 结果到知识库
* `save_to_knowledge_base`
* PostgreSQL checkpoint
* Long-term Memory
* Multi-Agent
* Planner / Executor
* Reflection
* Reranker
* Query Expansion 多 Query
* 前端页面
* Agent HTTP API 新页面
* 自动无限 Web 搜索
* 搜索结果正文抓取

本 Task 中：

> **Web Search Result 只包含搜索级结果，不抓正文。**

完成后停止，不继续 Task 5。

---

# 四、核心设计原则

继续遵守：

> Program 控制边界，LLM 在边界内做语义决策。

所以：

```text
是否允许 Web Search
```

不能完全交给 LLM 自己决定。

程序需要先根据用户意图和配置生成：

```text
allow_web
allowed_actions
```

LLM 只能在合法 Action 中选择。

---

# 五、allow_web 语义

Task 4 必须正式让：

```text
allow_web
```

具有业务意义。

至少区分以下用户意图。

---

## 场景 A：明确只查询个人知识库

例如语义：

```text
“我保存的文章里是怎么说的？”
“只根据我的知识库回答”
“我之前收藏的资料里有没有提到……”
```

则：

```text
allow_web = False
```

即使 KB Evidence 不足，也不能擅自 Web Search。

最终只能：

```text
Answer
Partial
Insufficient
```

---

## 场景 B：用户明确需要最新 / 当前信息

例如：

```text
“现在 LangGraph 最新版本有什么变化？”
“最近 Agent Memory 有什么新进展？”
```

这种问题：

```text
requires_freshness = True
allow_web = True
```

程序可以允许：

```text
WEB_SEARCH
```

---

## 场景 C：普通开放式问答

如果用户没有明确限制只看 KB，也没有明确最新要求：

第一版可以采用：

> 先查 KB；如果 KB Evidence 不足，再允许 Agent 判断是否需要 Web Search。

即：

```text
allow_web = True
```

但仍然优先 Knowledge Base。

不要直接跳过 KB。

---

# 六、Intent / Initial Decision

Task 3 可能还没有真正实现：

```text
intent
allow_web
requires_freshness
```

的语义判断。

Task 4 需要补齐一个最小：

```text
initial_decision
```

或在当前 `initialize` / reasoning service 中以清晰方式实现这一职责。

目标是得到：

```text
intent
allow_web
requires_freshness
```

不要为了概念形式主义强制多一次 LLM 调用。

如果现有 structured decision 可以自然承担 intent 识别，可以合并。

但必须保证：

> 在第一次 `evaluate_and_decide` 需要计算 `allowed_actions` 前，程序已经知道 `allow_web`。

---

# 七、Intent 判断要求

建议使用：

> Program hard rules + structured LLM semantic classification

例如：

明确出现：

```text
只根据我的文章
只看知识库
不要联网
不要搜索外部资料
```

可以由程序直接：

```text
allow_web = False
```

明显需要：

```text
最新
最近
今天
现在
目前版本
最新消息
```

可以程序或结构化 LLM 判断：

```text
requires_freshness = True
allow_web = True
```

对于模糊情况，再让 LLM 做语义分类。

不要只靠简单关键词作为最终实现。

---

# 八、Web Search Tool

新增：

```text
web_search(query, max_results)
```

它属于：

> Read-only external Tool

不是：

* 写操作
* Side Effect Tool
* Knowledge Base Save Tool

不需要用户确认。

---

# 九、Web Search Input

至少：

```text
query
max_results
```

其中：

```text
query
```

默认使用：

```text
state["current_query"]
```

但如果实现上合理，也允许 Web Search 使用专门为 Web Search 生成的 Search Query。

本 Task 暂时不要增加复杂 Query Planner。

---

`max_results` 必须有程序级约束。

建议：

```text
1 <= max_results <= 10
```

默认：

```text
5
```

如果当前项目已有统一配置，请复用。

---

# 十、Web Search Provider

优先检查当前项目是否已有：

* Web Search Provider
* 搜索 API
* HTTP Client 基础设施
* 可复用 Search Service

如果没有，请实现一个薄的：

```text
WebSearchService
```

要求：

* 框架无关
* 不依赖 LangGraph
* Runtime 注入
* Node 不直接写第三方 API 细节

结构：

```text
web_search Node
→ WebSearchService
→ External Search Provider
```

不要：

```text
Node
→ 直接拼 HTTP request
```

除非当前项目已有明确统一模式。

---

# 十一、Provider 配置

搜索 Provider：

* API Key
* Base URL
* timeout
* result limit

必须来自现有配置系统 / Environment。

不要硬编码 Secret。

不要提交 `.env`。

如需增加：

```text
.env.example
```

可以只增加变量名和示例占位值。

---

# 十二、Web Search Result Schema

必须使用结构化结果。

至少：

```text
title
url
snippet
source
published_at
```

其中：

```text
published_at
```

允许：

```text
None
```

不要因为没有发布日期就伪造。

如 Provider 有：

```text
domain
```

可考虑保留。

---

最终写入：

```text
state["web_results"]
```

---

# 十三、Web Search Result 的证据等级

这是 Task 4 非常重要的要求。

Web Search 返回的：

```text
title
snippet
```

只能视为：

> preliminary / weak evidence

不要默认把：

```text
search snippet
```

当成和：

```text
知识库完整 chunk
```

完全同等级证据。

原因：

* snippet 可能截断
* snippet 可能缺上下文
* snippet 可能是搜索引擎生成摘要
* snippet 未必完整反映原文

因此 Decision Prompt / Evidence Evaluation 中必须明确区分：

```text
KB Evidence
```

和：

```text
Web Search Evidence
```

---

# 十四、Task 4 Answer 允许使用 Web Snippet 吗？

第一版允许：

> 对低风险、简单事实，如果 Web Search snippet 本身明确支持，可以作为 Evidence 使用。

但 Answer 必须：

* 明确来源
* 不扩展 snippet 没支持的事实
* 不根据模型知识补全

对于明显需要全文确认的复杂问题：

```text
snippet 不足
```

则应该：

```text
Partial / Insufficient
```

而不是假装已经读过网页全文。

Task 5 才会加入：

```text
fetch_web_page
```

来解决这个问题。

---

# 十五、AgentAction

扩展现有：

```text
AgentAction
```

加入：

```text
WEB_SEARCH
```

不要重复创建另一套 Action Enum。

---

# 十六、allowed_actions

程序必须考虑：

```text
allow_web
web_search_count
max_web_searches
evidence_status
last_tool_error
```

例如：

## allow_web = False

绝不能出现：

```text
WEB_SEARCH
```

---

## allow_web = True 且尚未搜索 Web

可能允许：

```text
ANSWER
REWRITE_QUERY
WEB_SEARCH
INSUFFICIENT
```

具体取决于 Evidence。

---

## Web Search 已达到次数上限

必须移除：

```text
WEB_SEARCH
```

---

# 十七、Web Search Budget

第一版必须有程序硬限制。

建议：

```text
max_web_searches = 1
```

也就是：

> 一个 Agent Run 最多执行一次 Web Search。

不要只写进 Prompt。

程序必须保证即使 LLM 一直要求：

```text
WEB_SEARCH
```

也不会继续无限调用。

---

# 十八、tool_call_counts

Task 4 增加：

```text
tool_call_counts["web_search"]
```

规则继续沿用 Task 2：

> 只要真正执行了一次外部 Tool，就计数一次。

无论：

* 成功
* Empty Result
* Execution Error

只要真正发出了 Search Tool Call，就：

```text
tool_call_counts["web_search"] += 1
step_count += 1
```

---

# 十九、Empty Result

正常调用 Web Search，但：

```text
results = []
```

属于：

> Success with no results

应该：

```text
web_results = []
last_tool_error = None
```

不要当异常。

---

# 二十、Execution Error

例如：

```text
timeout
provider 5xx
network error
invalid provider response
```

需要与 Empty Result 区分。

例如：

```text
web_results = []
last_tool_error = "Web Search 执行失败（TimeoutError）"
```

不要把：

* API Key
* Provider 原始 Response
* Secret
* Connection string

写入最终用户回答。

---

# 二十一、Retry

Task 4 不做复杂 Agent Retry Framework。

如果 Web Provider / HTTP Client 已有程序级 Retry：

可以复用。

否则：

> 不新增复杂 Retry。

最多做一个非常轻量、明确的 transient retry，前提是符合项目当前统一网络调用风格。

不要加入无限重试。

---

# 二十二、Evidence Evaluation

扩展 Task 3 的：

```text
evaluate_and_decide
```

让它同时能看到：

```text
kb_results
web_results
```

但必须在 Prompt / Schema 中明确：

```text
KB result
```

和：

```text
Web search result
```

不是同一种 Evidence。

---

# 二十三、Decision 逻辑

典型流程：

```text
KB Evidence 足够
→ ANSWER
```

```text
KB 不足
且 rewrite 仍有预算
→ 可选 REWRITE_QUERY
```

```text
KB Rewrite 后仍不足
且 allow_web = True
且 web_search_count = 0
→ 可选 WEB_SEARCH
```

```text
Web Search 后 Evidence 足够
→ ANSWER
```

```text
Web Search 后只有部分 Evidence
→ PARTIAL / ANSWER
```

```text
Web Search 后仍无可靠 Evidence
→ INSUFFICIENT
```

不要写死成：

```text
KB empty → 必须 Web Search
```

因为：

> “固定 if fallback”不是我们要的 Agent 语义决策。

---

# 二十四、Freshness

如果：

```text
requires_freshness = True
```

则必须谨慎使用纯 KB Evidence。

除非 KB Evidence 本身具备可验证的新鲜时间信息，否则 Decision 应倾向允许：

```text
WEB_SEARCH
```

例如：

```text
“LangGraph 现在最新版本是多少？”
```

即使 KB 中有旧文章，也不能因为检索命中了旧内容就直接回答“最新”。

---

# 二十五、Sources

Web Result 被实际用于最终 Answer 时：

```text
sources
```

应增加对应来源。

Web Source 至少包含：

```text
title
url
source
published_at
```

如果项目已有统一 Source Schema，可扩展。

必须能区分：

```text
KB source
```

和：

```text
Web source
```

建议增加：

```text
source_type
```

例如：

```text
knowledge_base
web
```

但请根据现有 schema 风格决定。

---

# 二十六、Answer Grounding

最终：

```text
generate_answer
```

可以接收：

```text
selected KB evidence
+
selected Web evidence
```

但仍必须：

> Answer only from supplied evidence.

不允许模型：

* 使用自身常识补缺失
* 假装读取网页全文
* 根据 URL 猜内容
* 根据 title 延伸不存在事实

---

# 二十七、selected_evidence

延续 Task 3 原则：

> LLM 只选择 Evidence Reference，不复制大量 Evidence 原文。

如果 KB 使用：

```text
result_indexes
```

Web 也尽量使用相似方式：

```text
kb_indexes
web_indexes
```

或者设计一个统一 Evidence Reference Schema：

```text
source_type
index
```

请选择最小、清晰、易测试的方案。

不要为了本次任务建立大型通用 Evidence Framework。

---

# 二十八、Runtime Context

Web Search Provider / Service 属于：

```text
Runtime Dependency
```

必须通过当前：

```text
AgentContext
```

或同等 runtime context 机制注入。

不要放进：

```text
AgentState
```

不要进入 checkpoint。

---

# 二十九、Run-level Reset

新的用户问题开始时：

```text
web_results
```

必须重置。

同样：

```text
tool_call_counts
step_count
last_tool_error
```

按 Task 3 当前规则重置。

`messages` 继续跨 thread checkpoint 保留。

---

# 三十、Conditional Edge

Router 继续保持“笨”。

只根据：

```text
next_action
```

路由。

例如：

```text
WEB_SEARCH
→ web_search Node
```

不要在 Router 内：

* 判断 allow_web
* 判断次数
* 调 LLM
* 调搜索 API
* 改写 State

这些必须在 Node / Program policy 中完成。

---

# 三十一、安全兜底

必须保证：

```text
WEB_SEARCH
```

不可能形成无限循环。

例如：

```text
max_web_searches = 1
```

并且在：

* allowed_actions
* web_search node

至少两层进行保护。

如果非法 Action 仍进入：

```text
WEB_SEARCH
```

但预算已耗尽，则安全终止，不继续搜索。

---

# 三十二、测试要求

至少覆盖以下测试。

## Test 1：allow_web=False

用户明确：

```text
只根据我的知识库回答
```

KB Evidence 不足。

验证：

```text
WEB_SEARCH
```

永远不出现在 allowed_actions。

Web Search Service 不被调用。

最终：

```text
Partial / Insufficient
```

---

## Test 2：Freshness 允许 Web

用户问题：

```text
“最近 / 当前 / 最新……”
```

验证：

```text
requires_freshness = True
allow_web = True
```

KB 不足时允许：

```text
WEB_SEARCH
```

---

## Test 3：KB 足够，不调用 Web

KB Evidence 足够。

Decision：

```text
ANSWER
```

验证 Web Search：

```text
0 calls
```

---

## Test 4：KB 不足 → Web → Answer

第一次 KB Evidence 不足。

Decision：

```text
WEB_SEARCH
```

Web Search 返回明确结果。

再次 Evaluate。

最终：

```text
ANSWER
```

验证：

```text
tool_call_counts["web_search"] == 1
```

---

## Test 5：Web Empty Result

Web Search 返回：

```text
[]
```

验证：

```text
web_results == []
last_tool_error is None
```

最终安全：

```text
INSUFFICIENT
```

或 Partial。

---

## Test 6：Web Execution Error

模拟：

```text
TimeoutError
```

验证：

* `last_tool_error` 被设置
* 不当成 empty result
* Graph 安全结束
* 不无限 retry

---

## Test 7：Web Budget

第一次 Web Search 已执行。

之后 Decision LLM 再返回：

```text
WEB_SEARCH
```

验证：

```text
WEB_SEARCH
```

已不在 allowed_actions。

程序拒绝第二次搜索。

---

## Test 8：非法 Web Action

```text
allow_web=False
```

但模拟 LLM 返回：

```text
WEB_SEARCH
```

必须被程序规则拒绝。

---

## Test 9：Web Result Source

Web Evidence 被用于答案。

验证：

```text
sources
```

包含真实：

```text
title
url
source
```

不生成虚假来源。

---

## Test 10：Snippet Grounding

模拟 Search Result：

```text
title
snippet
```

只支持事实 A，不支持事实 B。

验证 Answer 不应该凭模型知识加入事实 B。

---

## Test 11：同线程新 Run Reset

第一个问题执行过 Web Search。

同一个 thread 第二个问题开始。

验证：

```text
web_results = []
tool_call_counts 重置
web_search budget 重置
```

但：

```text
messages
```

继续累积。

---

# 三十三、测试隔离

Agent tests 必须使用：

* Fake Web Search Service
* Stub Search Provider
* Fake Reasoning Service

不要依赖：

* 真实搜索 API
* 外网
* 真实 LLM
* 真实第三方搜索服务

如 Web Search Provider 自身需要 Integration Test，可单独标记，但不要影响默认测试稳定性。

---

# 三十四、回归验证

至少运行：

```text
Agent tests
Semantic Search tests
RAG tests
Full backend tests
```

以及：

```text
Python compileall
pip check
git diff --check
```

如环境允许：

```text
Frontend production build
```

---

# 三十五、开发顺序

请严格按：

1. 阅读 Phase 15 当前 Agent 实现。
2. 确认现有 HTTP / Search Provider 能力是否可复用。
3. 给出简短实现计划。
4. 定义 Web Search Schema。
5. 实现框架无关 `WebSearchService`。
6. 将 Web Service 注入 Runtime Context。
7. 实现 `web_search` Node。
8. 实现 / 补齐 intent、allow_web、requires_freshness。
9. 扩展 AgentAction。
10. 扩展 allowed_actions。
11. 扩展 Evidence Evaluation。
12. 增加 WEB_SEARCH Conditional Route。
13. 增加 Web Search Budget。
14. 扩展 sources。
15. 增加测试。
16. 跑定向测试。
17. 跑相关回归。
18. 跑完整后端测试。
19. `git diff --check`。
20. 做一次代码 review。
21. 输出总结。
22. 停止。

---

# 三十六、完成后必须汇报

## 1. 修改 / 新增文件

逐个说明职责。

## 2. Web Search Provider

说明：

```text
Agent Node
→ WebSearchService
→ 哪个 Provider
```

以及配置方式。

## 3. 最终 Graph

明确展示：

```text
KB
→ Decision
→ Rewrite / Web / Answer / Insufficient
```

完整结构。

## 4. Intent

说明：

```text
intent
allow_web
requires_freshness
```

如何产生。

## 5. allowed_actions

说明：

什么情况下：

```text
WEB_SEARCH
```

存在 / 不存在。

## 6. Budget

说明：

```text
max_web_searches
```

如何硬限制。

## 7. Evidence

说明：

KB Evidence 与 Web Search Snippet Evidence 如何区分。

## 8. Sources

说明 KB Source 与 Web Source 如何输出。

## 9. Error

明确：

```text
Empty Result
Execution Error
Illegal WEB_SEARCH
Budget Exhausted
```

分别怎么处理。

## 10. 测试结果

明确：

```text
Agent tests: X passed
Agent + Semantic Search + RAG: X passed
Full backend: X passed
Frontend build: passed / not run
compileall: passed
pip check: passed
git diff --check: passed
```

## 11. 明确未实现

至少：

```text
fetch_web_page
get_article_content Agent Tool
save_to_knowledge_base
PostgreSQL checkpoint
Long-term Memory
Multi-Agent
```

---

# 三十七、验收标准

只有同时满足以下要求，Task 4 才算完成：

* Web Search 已作为框架无关只读 Tool 接入
* Node 不直接复制 Search Provider 核心逻辑
* `allow_web` 有真实业务意义
* `requires_freshness` 有真实作用
* 用户明确只查 KB 时绝不擅自联网
* KB 足够时不调用 Web
* KB 不足且允许 Web 时 Agent 可选择 Web
* Web Search 使用结构化结果
* Web snippet 被视为弱 / 初步 Evidence
* Agent 不假装已读取网页全文
* WEB_SEARCH 受 allowed_actions 控制
* LLM 非法 WEB_SEARCH 会被程序拒绝
* Web Search 最多一次，由程序硬限制
* Empty Result 与 Execution Error 区分
* tool_call_counts 正确计数
* Web Results 新 Run 会 reset
* sources 可包含实际使用的 Web Source
* Answer 仍严格 Evidence-grounded
* Graph 不可能无限 Web Search
* 自动化测试覆盖主要路径
* 完整回归通过
* 没有提前实现 Task 5
* 完成后停止开发

完成后请停止，不要继续实现 `fetch_web_page`、全文读取、保存知识库或 PostgreSQL checkpoint。

