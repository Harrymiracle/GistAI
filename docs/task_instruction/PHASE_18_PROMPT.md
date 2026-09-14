你现在要继续在现有 **GistAI / AI 阅读助手** 项目中完成 Stage 10 Agent V1 的第六批开发任务。

Phase 17 / Task 5 已完成。

当前 Agent 已具备：

* Knowledge Search
* Query Rewrite
* Evidence Evaluation
* Structured Decision
* `allowed_actions`
* Conditional Edge
* Web Search
* KB Article Full-text Read
* Web Page Full-text Fetch
* Temporary Full-text Chunking
* Relevance Selection
* Context Token Budget
* Answer / Partial / Insufficient
* Runtime Context
* InMemory checkpoint
* 多项 Tool-level Budget
* 自动化测试

当前完整后端测试基线：

```text
278 passed
```

当前主要 Graph 能力概念上为：

```text
START
→ initialize
→ initial_decision
→ knowledge_search
→ evaluate_and_decide
   ├─ ANSWER → generate_answer → END
   ├─ REWRITE_QUERY → rewrite_query → knowledge_search
   ├─ WEB_SEARCH → web_search → evaluate_and_decide
   ├─ GET_ARTICLE_CONTENT → get_article_content → evaluate_and_decide
   ├─ FETCH_WEB_PAGE → fetch_web_page → evaluate_and_decide
   └─ INSUFFICIENT → insufficient_answer → END
```

---

# 一、本次任务目标

本次只做：

> **Task 6：统一 Agent Runtime Policy、Budget、Tool Execution、Error Handling 和 Termination。**

目标不是增加新的业务能力，而是把目前分散在各 Node 中的控制规则收口成清晰、可测试、可解释的 Agent Runtime Policy。

本 Task 完成后，Agent 应该明确做到：

```text
哪些 Action 当前允许
哪些预算还剩多少
Tool 是否真的被执行
失败属于哪一类
失败后还能做什么
什么时候必须结束
为什么不会无限循环
```

---

# 二、严格任务边界

本次不要实现：

* 新 Tool
* `save_to_knowledge_base`
* 自动保存 Web 内容
* PostgreSQL checkpoint
* Long-term Memory
* Multi-Agent
* Planner / Executor
* Reflection
* 前端 Agent UI
* 新 Agent API 页面
* 新数据库表
* Alembic migration
* Reranker
* 大型 Workflow Engine
* 第三方通用 Tool Framework
* 全局复杂 Retry Framework

本 Task 是：

> **工程收口，不是功能扩展。**

完成后停止，不继续 Task 7。

---

# 三、首先做一次现状审计

开发前先完整检查：

* `AgentState`
* `AgentContext`
* `AgentAction`
* `EvidenceStatus`
* `allowed_actions`
* `step_count`
* `tool_call_counts`
* `rewrite_count`
* Web Search budget
* Article Read budget
* Web Page Read budget
* Error 处理
* Tool Node
* Decision validation
* Conditional Router
* Answer termination
* Run-level reset

目标是找出：

> 目前哪些 Policy / Budget / Error 判断散落在多个 Node 中。

不要先重构，再理解。

先列出现状和重复逻辑，再做最小收口。

---

# 四、核心设计原则

继续遵守：

> **Program controls boundaries; LLM makes semantic decisions inside those boundaries.**

因此：

LLM 可以决定：

```text
在 allowed_actions 中选择哪个 Action
```

LLM 不可以决定：

```text
增加预算
跳过权限
绕过 Tool validation
修改 max_reads
修改 max_searches
决定非法 URL 可以抓
决定非法 article_id 可以读
```

---

# 五、Runtime Policy

建议新增一个轻量、框架无关的：

```text
AgentPolicy
```

或：

```text
AgentRuntimePolicy
```

具体命名按项目风格决定。

它的职责是：

> 根据当前 Agent State + 固定 Runtime Limits，计算当前合法行为。

不要让它调用：

* LLM
* DB
* HTTP
* Embedding
* Web Search

它应该是：

> Pure / deterministic policy logic

尽量方便单元测试。

---

# 六、Policy 应至少覆盖

当前这些规则：

```text
max_rewrites
max_web_searches
max_article_reads
max_web_page_reads
```

以及：

```text
allow_web
requires_freshness
last_tool_error
kb_results
web_results
read_article_ids
fetched_web_urls
selected_evidence
```

最终统一计算：

```text
allowed_actions
```

---

# 七、Budget 配置统一

目前多个 Budget 可能散落在 Node 常量中。

Task 6 需要统一整理。

至少：

```text
MAX_REWRITES
MAX_WEB_SEARCHES
MAX_ARTICLE_READS
MAX_WEB_PAGE_READS
MAX_STEPS
```

建议形成：

```text
AgentLimits
```

或项目现有 config 结构中的集中配置。

不要把同一个限制：

```text
MAX_WEB_SEARCHES = 1
```

在多个文件重复定义。

---

# 八、增加 MAX_STEPS

Task 6 需要正式增加一个：

```text
MAX_STEPS
```

作为最终兜底预算。

目的：

即使未来出现：

* Policy bug
* Decision bug
* 新 Tool
* 循环组合异常

Graph 仍然有一个全局程序级停止条件。

建议值根据当前 Graph 合理设置，例如：

```text
MAX_STEPS = 8～12
```

请根据当前最坏合法路径实际推导，不要随便选。

完成总结中必须解释：

> 为什么这个值足够覆盖正常流程，又能阻止异常循环。

---

# 九、明确 step_count 语义

Task 6 必须固定：

```text
step_count
```

到底表示什么。

建议定义为：

> 当前 Agent Run 已经执行的“有意义 Agent Action / Tool Action”数量。

不要把：

* initialize
* router
* state merge
* answer formatting

这种内部 Graph Node 全部机械计数。

请统一当前行为。

至少明确：

```text
Knowledge Search
Query Rewrite
Web Search
Article Read
Web Page Fetch
```

哪些计 step。

并写测试固定语义。

---

# 十、tool_call_counts 语义

`tool_call_counts` 只统计：

> 真正执行过的外部/业务 Tool Call。

例如：

```text
knowledge_search
web_search
get_article_content
fetch_web_page
```

Query Rewrite 是内部 reasoning action，不计：

```text
tool_call_counts
```

但可以计：

```text
step_count
```

---

# 十一、Validation Failure 不计真实 Tool Call

如果：

```text
非法 article index
非法 web result index
预算已经耗尽
URL 不属于 web_results
article 已经读过
URL 已经抓过
```

在真正业务 Tool 执行前就被程序拒绝，则：

```text
tool_call_counts
```

不增加。

这必须统一。

---

# 十二、Tool Attempt 的定义

只要真正进入底层业务 Tool，例如：

```text
SearchService.semantic_search
WebSearchService.search
ArticleContentService.get
WebPageFetchService.fetch
```

就算一次 Tool Attempt。

即使最终：

```text
TimeoutError
DB Error
HTTP Error
Empty Result
```

都应该计数一次。

---

# 十三、统一 Tool Execution Result

目前不同 Tool 可能分别直接操作：

```text
last_tool_error
kb_results
web_results
article_contents
web_page_contents
```

Task 6 建议增加一个最小统一概念：

```text
ToolExecutionResult
```

或等价内部结构。

不要做大型通用 Tool Framework。

它只需要帮助表达：

```text
success
empty
validation_error
execution_error
```

以及：

```text
tool_name
error_type
safe_message
```

具体 Schema 根据现有代码选择。

---

# 十四、Error 分类

Task 6 需要统一错误分类。

至少区分：

## 1. Validation / Policy Error

例如：

```text
非法 Action
非法 index
预算耗尽
目标已读取
allow_web=False 却请求 WEB_SEARCH
```

特点：

> Tool 没有真正执行。

不要 Retry。

---

## 2. Empty Result

例如：

```text
KB Search = []
Web Search = []
```

特点：

> Tool 正常执行成功，只是没有结果。

不是 Error。

---

## 3. Execution Error

例如：

```text
DB unavailable
timeout
provider 5xx
HTTP fetch failed
Playwright failed
```

特点：

> Tool 已经真正尝试执行。

---

## 4. Reasoning / Structured Output Error

例如：

```text
LLM structured output malformed
非法 AgentAction
非法 Evidence index
Rewrite 输出为空
Answer service failure
```

与外部 Tool Error 分开。

---

# 十五、last_tool_error

检查当前：

```text
last_tool_error
```

是否已经被混用于：

* Tool Error
* LLM Error
* Policy Error

如果是，请做最小收口。

可以：

```text
last_error
last_error_type
```

也可以保持现有字段，但增加：

```text
AgentErrorType
```

不要为此过度设计复杂 Error Object。

目标：

> 后续 Decision / API / Debug 能知道“发生了哪一类失败”。

---

# 十六、安全错误信息

最终 State / 用户回答中不得出现：

* API Key
* DB Connection String
* 原始 Provider Response
* Stack Trace
* Internal SQL
* 内部网络地址
* Secret Header

错误信息只保留：

```text
安全的类型
+
简短业务描述
```

例如：

```text
WEB_SEARCH_EXECUTION_ERROR
```

而不是完整：

```text
requests.exceptions.... api_key=...
```

---

# 十七、Retry Policy

本 Task 不做复杂 Retry Framework。

但需要正式定义：

> 哪些错误可以由程序自动重试，哪些不可以。

建议：

## Validation / Policy Error

```text
0 retry
```

## Empty Result

```text
0 retry
```

由 Agent 决定下一 Action。

## Structured Output Error

允许：

```text
最多 1 次受控 retry
```

仅当项目现有 LLM structured output 模式适合。

## Transient Execution Error

如果当前底层 Service 已有 retry：

继续复用。

不要在 Agent Runtime 再叠加第二套重复 Retry。

如当前没有 retry，本 Task 可以保持：

```text
0 Agent-level retry
```

然后安全终止。

重点是：

> 规则明确，而不是一定增加 retry。

---

# 十八、Termination Policy

建议新增一个明确：

```text
TerminationPolicy
```

或包含在 `AgentRuntimePolicy` 中。

它负责判断：

```text
什么时候必须停止
```

至少覆盖：

```text
ANSWER ready
INSUFFICIENT
MAX_STEPS reached
no allowed actions
fatal execution error
reasoning failure with no safe recovery
all relevant budgets exhausted
```

---

# 十九、V1 Budget Exhausted 策略保持原计划

继续遵守我们已经确定的规则：

> Budget 用尽时，如果仍有可靠 Partial Evidence，则 Partial Answer；如果没有可靠 Evidence，则 Insufficient。

不要：

```text
用模型自身知识补答案
```

不要改成：

```text
Ask user to continue
```

本 Task 不改变产品策略。

---

# 二十、No Allowed Actions

如果：

```text
allowed_actions == []
```

Graph 不能卡住。

必须进入：

```text
termination
```

规则：

如果：

```text
selected_evidence
```

有可靠内容：

```text
Partial Answer
```

否则：

```text
Insufficient
```

---

# 二十一、Global Step Exhaustion

如果：

```text
step_count >= MAX_STEPS
```

必须从程序层阻止：

```text
REWRITE_QUERY
WEB_SEARCH
GET_ARTICLE_CONTENT
FETCH_WEB_PAGE
```

等进一步动作。

然后进入终止。

不能只依赖 Prompt：

> “请不要超过最大步骤数”。

---

# 二十二、allowed_actions 成为单一事实来源

Task 6 后，希望：

```text
allowed_actions
```

由统一 Policy 计算。

不要在多个 Node 各自复制：

```python
if rewrite_count < 1:
...
if web_count < 1:
...
```

Node 可以保留最后一道防御性校验：

> defense-in-depth

但：

> 主规则应集中在 Policy。

---

# 二十三、Node 的职责收窄

Task 6 后，每个 Tool Node 尽量只负责：

```text
读取 State / Context
↓
验证当前请求
↓
调用业务 Service
↓
标准化 Tool Result
↓
partial State update
```

不要让 Node 同时负责大量：

* Global policy
* Termination planning
* LLM semantic decision
* Router logic

---

# 二十四、Router 继续保持 dumb

Conditional Router 仍然只根据：

```text
next_action
```

路由。

不要让 Router 重新：

```text
计算 allowed_actions
判断 budget
判断 error
```

---

# 二十五、Run-level State Reset 审计

Task 6 再统一检查一遍：

每个新用户问题开始时必须 reset：

```text
original_query
current_query

kb_results
web_results
article_contents
web_page_contents

selected_evidence
fulltext evidence

rewrite_count
step_count
tool_call_counts

allowed_actions
next_action

read_article_ids
fetched_web_urls

last_error / last_tool_error

final_answer
sources
```

而：

```text
messages
```

继续保留。

增加回归测试，避免未来新增字段忘记 reset。

---

# 二十六、Policy 不进入 checkpoint？

注意区别：

Policy 配置：

```text
MAX_STEPS
MAX_WEB_SEARCHES
...
```

属于 Runtime / App Config。

不要作为业务 State 长期保存。

但：

```text
step_count
rewrite_count
tool_call_counts
read_article_ids
```

属于当前 Run State，可以进入 checkpoint。

---

# 二十七、Debug / Trace 最小可观测性

Task 6 可以增加一个轻量可观测字段，如果当前代码合适，例如：

```text
decision_history
```

或：

```text
action_history
```

只记录：

```text
Action 名称
step number
简单 outcome
```

例如：

```text
knowledge_search: success
rewrite_query: success
knowledge_search: empty
web_search: success
fetch_web_page: success
answer
```

不要记录：

* Prompt 全文
* Secret
* Full Content
* LLM 原始隐藏 reasoning
* 大段网页内容

如果当前增加该字段会明显扩大范围，可以不做。

完成总结中说明是否采用。

---

# 二十八、不要保存 Chain of Thought

严禁设计：

```text
reasoning_trace
chain_of_thought
model_internal_reasoning
```

到 State / DB。

可以保存：

```text
decision_reason
evidence_reason
action outcome
```

这种简短、结构化、用户可解释的信息。

---

# 二十九、最终 Agent Loop 应可形式化证明有界

Task 6 完成总结中必须给出一段明确说明：

当前最大：

```text
Rewrite <= ?
KB Searches <= ?
Web Searches <= ?
Article Reads <= ?
Web Page Reads <= ?
Global Steps <= ?
```

并说明：

> 为什么任何 Action 组合都不能形成无限循环。

---

# 三十、建议最终 Budget

不要机械采用下面数字，请根据当前代码推导，但目标大致：

```text
max_rewrites = 1
max_web_searches = 1
max_article_reads = 2
max_web_page_reads = 2
max_steps = 合理全局上限
```

Knowledge Search 次数也需要明确：

因为：

```text
初始 Search
+
Rewrite 后 Search
```

第一版理论上最多：

```text
2 次
```

请考虑是否增加：

```text
MAX_KB_SEARCHES = 2
```

让所有 Tool 都拥有清晰预算。

---

# 三十一、知识库 Search Budget

建议正式增加：

```text
MAX_KB_SEARCHES
```

当前正常路径：

```text
初始 Knowledge Search = 1
Rewrite 后再次 Search = 1
```

所以通常：

```text
MAX_KB_SEARCHES = 2
```

Node 和 Policy 双层校验。

---

# 三十二、Error 后的行为

请明确每类错误后：

```text
allowed_actions
```

如何变化。

例如：

## Knowledge Search Execution Error

通常：

```text
不要伪装成 KB empty
```

可选择安全终止。

---

## Web Search Error

如果已经有可靠 KB Evidence：

可 Partial Answer。

否则 Insufficient。

---

## Article Read Error

如果已有 KB Chunk 足够部分回答：

可 Partial。

---

## Web Fetch Error

如果 Web snippet 仍提供有限可靠信息：

可 Partial。

---

## Reasoning Error

如果程序不能安全判断下一步：

> Fail closed

优先 Partial / Insufficient。

---

# 三十三、Answer Generation Error

如果：

```text
generate_answer
```

本身 LLM 调用失败：

不要：

```text
Graph crash with raw stack trace
```

可以安全生成：

```text
“当前证据已找到，但回答生成失败。”
```

或符合项目现有错误输出方式。

但不要凭程序模板重新编造事实答案。

---

# 三十四、测试要求

至少覆盖以下测试。

## Test 1：Policy 正常计算 allowed_actions

构造不同 State：

* rewrite 可用
* Web 可用
* article read 可用
* web fetch 可用

验证结果准确。

---

## Test 2：Budget Exhausted

分别达到：

```text
MAX_REWRITES
MAX_KB_SEARCHES
MAX_WEB_SEARCHES
MAX_ARTICLE_READS
MAX_WEB_PAGE_READS
```

验证对应 Action 被移除。

---

## Test 3：Global MAX_STEPS

达到全局上限。

验证所有继续执行类 Action 被禁止。

Graph 安全终止。

---

## Test 4：Validation Failure 不计 Tool Call

非法：

```text
article index
web index
budget exhausted
重复 article
重复 URL
```

验证：

```text
tool_call_counts
step_count
```

按定义不增加。

---

## Test 5：Execution Error 计 Tool Attempt

Tool 真正被调用后抛：

```text
TimeoutError
```

验证调用计数增加一次。

---

## Test 6：Empty Result 不是 Error

KB / Web Search：

```text
[]
```

验证：

```text
last_error
```

为空或明确非错误状态。

---

## Test 7：Error Type

分别触发：

```text
Policy Error
Tool Execution Error
Reasoning Error
```

验证可以区分。

---

## Test 8：No Allowed Actions

构造：

```text
allowed_actions=[]
```

有 Partial Evidence：

→ Partial Answer

无 Evidence：

→ Insufficient

---

## Test 9：MAX_STEPS + Partial Evidence

验证：

> Budget exhausted 不会丢掉已有可靠证据。

---

## Test 10：MAX_STEPS + No Evidence

验证：

```text
Insufficient
```

不调用 LLM自由知识。

---

## Test 11：New Run Reset

同 thread：

第一轮产生：

* 多项 count
* errors
* read ids
* sources

第二轮新问题：

Run-level 全部 reset。

messages 保留。

---

## Test 12：Knowledge Search Max 2

验证：

```text
initial search
rewrite
second search
```

以后不能第三次 Knowledge Search。

---

## Test 13：非法 LLM Action

LLM 返回不在：

```text
allowed_actions
```

中的 Action。

程序拒绝，并安全终止。

---

## Test 14：Structured Output Failure

验证受控 retry / safe failure 符合最终 Policy。

---

## Test 15：Answer Generation Failure

验证 Graph 不暴露内部异常。

---

## Test 16：Worst-case Legal Path

构造一条接近最大预算路径，例如：

```text
KB Search
→ Rewrite
→ KB Search
→ Web Search
→ Read Article
→ Read Article
→ Fetch Page
→ Fetch Page
→ Terminate
```

确保：

* 不超过 max_steps
* Graph 一定结束
* 计数正确

---

# 三十五、测试风格

优先：

* Unit test AgentPolicy
* Fake Tool Services
* Fake Reasoning Service
* Stub Runtime Context

不要让 Policy 单元测试依赖：

* DB
* Internet
* LLM
* Tavily
* Playwright

---

# 三十六、回归范围

至少运行：

```text
Agent tests
Fetch / Extraction tests
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

# 三十七、代码质量要求

Task 6 的重点就是：

> 减少重复和隐式规则。

因此完成后请检查：

* 是否仍有多处定义同一 Budget
* 是否多个 Node 复制 allowed_actions 判断
* Error 类型是否混乱
* Counter 语义是否不一致
* Tool Validation 是否有明显重复

但不要为了追求 DRY 过度抽象。

---

# 三十八、开发顺序

请按：

1. 审计 Phase 17 当前 Budget / Policy / Error 分布。
2. 写出当前重复规则清单。
3. 给出最小重构计划。
4. 集中 Agent Limits。
5. 实现 `AgentRuntimePolicy` 或等价纯 Policy 层。
6. 增加 / 明确 `MAX_KB_SEARCHES`。
7. 增加 `MAX_STEPS`。
8. 统一 allowed_actions 计算。
9. 统一 Tool Call / step 计数语义。
10. 统一 Error Classification。
11. 统一 Termination Policy。
12. 收窄各 Tool Node 职责。
13. 保留 Node defense-in-depth。
14. 增加安全终止逻辑。
15. 审计 Run-level reset。
16. 增加测试。
17. 跑 Agent 定向测试。
18. 跑相关回归。
19. 跑完整后端测试。
20. `compileall`
21. `pip check`
22. `git diff --check`
23. 做代码 review。
24. 输出总结。
25. 停止。

---

# 三十九、完成后必须汇报

## 1. 修改 / 新增文件

逐一说明职责。

---

## 2. Policy 架构

明确：

```text
State
+
AgentLimits
↓
AgentRuntimePolicy
↓
allowed_actions / termination
```

---

## 3. Budget

列出最终：

```text
MAX_KB_SEARCHES
MAX_REWRITES
MAX_WEB_SEARCHES
MAX_ARTICLE_READS
MAX_WEB_PAGE_READS
MAX_STEPS
```

以及各值。

---

## 4. step_count

明确：

> 什么行为计 step，什么不计。

---

## 5. tool_call_counts

明确：

> 哪些行为算真实 Tool Call。

---

## 6. Error 分类

说明：

```text
Validation / Policy Error
Empty Result
Execution Error
Reasoning Error
```

如何区分。

---

## 7. Retry

说明：

每类错误当前是否 retry，以及为什么。

---

## 8. Termination

列出所有最终结束路径：

```text
Answer
Partial
Insufficient
Budget Exhausted
No Allowed Actions
Fatal Tool Error
Reasoning Failure
```

---

## 9. 有界性证明

给出当前最大调用次数。

说明：

> 为什么 Graph 不可能无限循环。

---

## 10. Run State Reset

列出关键 Run-level 字段。

确认：

```text
messages
```

仍然是 conversation-level。

---

## 11. 测试结果

明确：

```text
Agent tests: X passed
Fetch tests: X passed
Agent + Semantic Search + RAG: X passed
Full backend: X passed
Frontend build: passed / not run
compileall: passed
pip check: passed
git diff --check: passed
```

---

## 12. Code Review

明确是否发现：

```text
Critical
Important
Minor
```

问题。

---

## 13. 明确未实现

至少列：

```text
save_to_knowledge_base
PostgreSQL checkpoint
Long-term Memory
Multi-Agent
Frontend Agent UI
Task 7+
```

---

# 四十、验收标准

Task 6 只有同时满足以下条件才算完成：

* Budget 配置集中
* `MAX_KB_SEARCHES` 明确
* `MAX_STEPS` 明确
* allowed_actions 主逻辑集中
* Node 仍有必要的防御性校验
* step_count 语义统一
* tool_call_counts 语义统一
* Validation Failure 不计真实 Tool Call
* Execution Error 计真实 Tool Attempt
* Empty Result 不算 Error
* Error 分类明确
* Reasoning Error 与 Tool Error 能区分
* Termination Policy 明确
* Budget Exhausted 能安全终止
* No Allowed Actions 能安全终止
* Partial Evidence 不会在预算耗尽时丢失
* 无 Evidence 时不会用模型知识补答案
* Run-level State reset 完整
* Graph 有全局 Step 上限
* 所有局部 Budget + Global Budget 共同保证有界
* 最坏合法路径有自动化测试
* 完整回归通过
* 没有提前实现 Task 7
* 完成后停止开发

完成以上内容后，请停止，不要继续实现前端 Agent UI、PostgreSQL checkpoint、长期 Memory 或知识库写入。
