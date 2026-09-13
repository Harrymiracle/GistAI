你现在要继续在现有 **GistAI / AI 阅读助手** 项目中完成 Stage 10 Agent V1 的第三批开发任务。

Phase 14 / Task 2 已完成。

当前已有：

* `AgentState`
* `AgentAction`
* `EvidenceStatus`
* LangGraph `StateGraph`
* `initialize`
* `finish`
* `InMemorySaver`
* `thread_id`
* `AgentContext`
* `KnowledgeSearchInput`
* `KnowledgeSearchResult`
* `KnowledgeSearchService`
* `knowledge_search` Node
* 已复用现有 Semantic Search
* `step_count`
* `tool_call_counts`
* Knowledge Search 正常结果 / Empty Result / Execution Error 区分
* 自动化测试

当前 Graph：

```text
START
→ initialize
→ knowledge_search
→ finish
→ END
```

当前完整后端测试基线：

```text
201 passed
```

---

# 一、本次任务目标

本次实现：

> **Task 3：第一个 KB-only Agent Decision Loop**

即：

```text
用户问题
↓
initialize
↓
knowledge_search
↓
evaluate_and_decide
   ├─ ANSWER
   ├─ REWRITE_QUERY
   └─ INSUFFICIENT
```

如果需要 Query Rewrite：

```text
evaluate_and_decide
↓
rewrite_query
↓
knowledge_search
↓
evaluate_and_decide
↓
answer / insufficient
```

第一版最多允许：

```text
1 次 Query Rewrite
```

最终 Graph 需要首次具备：

* LLM 语义判断
* Conditional Edge
* 有界 Agent Loop
* Query Rewrite
* Evidence Evaluation
* Next Action Decision
* Answer / Partial / Insufficient 终止

---

# 二、严格任务边界

本次不要实现：

* Web Search
* `fetch_web_page`
* 外部网页全文读取
* `get_article_content` Agent Tool
* `save_to_knowledge_base`
* PostgreSQL checkpoint
* 长期 Memory
* 多 Agent
* Planner / Executor
* Reflection
* 无限循环
* Dynamic Tool Registry
* Tool Calling Framework
* 前端页面
* 后台任务系统
* Reranker
* Query Expansion 多候选
* 自动保存外部文章

本 Task 只允许使用：

> **当前用户自己的本地知识库。**

完成后停止，不要继续 Task 4。

---

# 三、核心设计原则

继续遵守：

> **LangGraph 负责 orchestration，现有业务 Service 负责业务能力。**

不要把：

* Semantic Search
* Embedding
* pgvector
* 数据库查询

重新实现在 Graph Node 中。

另外：

> **Program 控制边界，LLM 在边界内做语义决策。**

LLM 不能自己无限增加步骤、修改预算或发明 Action。

---

# 四、首先处理 AgentState 生命周期问题

Task 1 / Task 2 为了验证 checkpoint，目前部分字段会从旧 State 中继续保留。

但真正进入 Agent Run 后，需要区分：

## Conversation-level State

跨同一 `thread_id` 保留：

```text
messages
```

以及确实属于会话上下文的数据。

---

## Run-level State

每一个新的用户问题开始时必须重新初始化：

```text
original_query
current_query

kb_results
web_results
article_contents
web_page_contents

selected_evidence
evidence_status
evidence_reason

rewrite_count
step_count
tool_call_counts
allowed_actions
next_action

last_tool_error
final_answer
sources
```

根据实际代码判断其中暂时未使用字段是否需要 reset，但原则是：

> 上一轮 Agent Run 的检索结果、计数器、错误、证据和 Action 不得污染新一轮用户问题。

特别注意：

Task 1 当前：

```python
state.get("original_query") or query
```

会导致同一 thread 的第一条问题长期保留。

从 Task 3 开始，请把：

```text
original_query
```

明确改成：

> 当前这一轮 Agent Run 收到的用户原始问题。

而不是整个 conversation 的第一句话。

`messages` 才承担 conversation history。

请增加测试验证该行为。

---

# 五、Task 3 的状态语义

本次至少明确这些字段：

```text
original_query
```

当前这次用户请求的原始问题，整个 Agent Run 中不修改。

---

```text
current_query
```

当前真正用于 Knowledge Search 的 Query。

初始：

```text
current_query = original_query
```

发生 Rewrite 后：

```text
current_query = rewritten_query
```

但：

```text
original_query
```

始终不变。

---

```text
rewrite_count
```

当前 Run 已发生多少次 Rewrite。

第一版：

```text
max_rewrite_count = 1
```

---

```text
evidence_status
```

表示目前本地证据是否足够。

请根据现有 Enum 复用或最小扩展。

概念上至少需要表达：

```text
UNKNOWN
SUFFICIENT
PARTIAL
INSUFFICIENT
```

如果现有 Enum 命名不同，请保持项目风格，不必机械照搬。

---

```text
next_action
```

表示下一步 Graph 要执行什么。

至少需要表达概念：

```text
ANSWER
REWRITE_QUERY
INSUFFICIENT
```

如果现有 `AgentAction` 已经有合适值，请复用。

不要因为 Prompt 中命名不同就制造重复 Enum。

---

# 六、Evidence Evaluation + Next Action

本次实现：

```text
evaluate_and_decide
```

建议把：

* Evidence Evaluation
* Next Action Decision

放在一次结构化 LLM 调用中完成。

不要为了概念纯洁拆成两个 LLM Call。

目的：

* 减少延迟
* 减少 Token
* 避免两个语义判断互相不一致

---

# 七、Programmatic Rules + LLM Semantic Evaluation

我们已经确定：

> Evidence 判断采用“程序硬规则 + LLM 语义充分性判断”。

因此不要把所有决定都交给 LLM。

## 程序层先负责

例如：

* Knowledge Search 是否执行成功
* kb_results 是否为空
* rewrite_count 是否达到上限
* 当前有哪些 Action 仍合法
* 是否发生 Tool Error
* 是否还有预算
* Action 是否属于 Enum
* LLM 返回的 Action 是否在 `allowed_actions` 中

程序先计算：

```text
allowed_actions
```

然后 LLM 只能在允许集合里选。

---

# 八、allowed_actions

`allowed_actions` 是：

> 当前决策轮次由程序动态计算出来的派生状态。

例如第一次 Knowledge Search 后：

如果：

```text
rewrite_count = 0
```

则可能允许：

```text
ANSWER
REWRITE_QUERY
INSUFFICIENT
```

如果：

```text
rewrite_count >= 1
```

则不能再 Rewrite，只允许类似：

```text
ANSWER
INSUFFICIENT
```

具体 Enum 请按项目已有设计。

不要让 LLM 返回：

```text
REWRITE_QUERY
```

然后程序才发现预算已经超限。

最好：

```text
Program
↓
计算 allowed_actions
↓
LLM 只从 allowed_actions 中选择
↓
再次程序校验
```

---

# 九、Empty Result 的处理

如果：

```text
kb_results == []
```

第一次检索时：

如果仍有 Rewrite Budget，可以允许：

```text
REWRITE_QUERY
INSUFFICIENT
```

不应该允许：

```text
ANSWER
```

除非项目明确存在其他可靠 evidence。

如果 Rewrite 后仍为空：

```text
rewrite_count == max
```

则应该：

```text
INSUFFICIENT
```

不要让 LLM 使用模型自身知识补齐答案。

---

# 十、Query Rewrite

实现：

```text
rewrite_query
```

它不是外部 Tool。

它属于 Agent 内部推理 /转换 Node。

输入：

```text
original_query
current_query
messages（必要时）
kb_results / evidence_reason（必要时）
```

输出只更新：

```text
current_query
rewrite_count
```

必要时更新与本轮 decision 有关的字段。

---

# 十一、Rewrite 原则

Rewrite 的目标是：

> 改善本地知识库 Retrieval，而不是改变用户问题。

必须：

```text
original_query 保持不变
```

只修改：

```text
current_query
```

Rewrite 后 Query 应该：

* 更适合向量检索
* 保留用户核心意图
* 不凭空加入用户没表达的事实
* 不把问题回答掉
* 不输出解释性长文本
* 不同时生成多个 Query

第一版只产生：

```text
一个 rewritten query
```

---

# 十二、Rewrite 次数硬限制

必须有程序级限制：

```text
max_rewrites = 1
```

不能只在 Prompt 写：

> “最多改写一次。”

即使 LLM 一直请求 Rewrite，Graph 也不能无限循环。

程序必须保证：

```text
knowledge_search
→ evaluate
→ rewrite
→ knowledge_search
→ evaluate
```

最多发生一次 Rewrite。

---

# 十三、结构化 LLM 输出

Evidence Evaluation / Decision 必须使用结构化输出。

不要解析自由文本字符串，例如：

```text
"The evidence seems enough, so answer..."
```

建议定义 Pydantic Schema，例如概念上：

```python
class AgentDecision(BaseModel):
    evidence_status: EvidenceStatus
    reason: str
    next_action: AgentAction
```

可以根据实际需要增加：

```text
selected_evidence
```

但第一版不要让 LLM 返回大段 chunk 原文。

如果需要选 Evidence，优先：

```text
chunk_id
article_id
result index
```

这样的引用标识。

---

# 十四、selected_evidence

第一版可以有两种实现：

## 推荐方案

LLM Decision 返回需要使用的：

```text
result_indexes
```

或：

```text
chunk_ids
```

程序根据这些引用，从：

```text
kb_results
```

构造：

```text
selected_evidence
```

这样避免结构化输出复制大量原文。

如果当前实现复杂度明显增加，也允许第一版暂时使用全部满足阈值的 `kb_results` 作为 answer context，但必须在完成总结中说明。

不要为了本 Task 引入复杂 Evidence Ranking Framework。

---

# 十五、LLM Runtime Dependency

LLM Client / Service 不应放进 checkpoint。

继续沿用 Task 2 的：

```text
AgentContext
```

或合适的 runtime dependency 机制。

也就是说：

```text
LLM Service
KnowledgeSearchService
DB Session
Embedding Service
```

属于运行时依赖，不属于持久化 AgentState。

---

# 十六、Conditional Edge

Task 3 开始正式使用 LangGraph Conditional Edge。

原则：

> Conditional Edge 尽量“笨”。

不要在 Router 函数中重新写一遍业务判断。

应该：

```text
evaluate_and_decide Node
↓
写 next_action
↓
Conditional Edge
只读取 next_action
↓
路由到对应 Node
```

例如概念：

```text
ANSWER
→ generate_answer

REWRITE_QUERY
→ rewrite_query

INSUFFICIENT
→ generate_insufficient_answer
```

Router 本身不要：

* 再调用 LLM
* 再判断 Evidence
* 再读取数据库
* 再重新计算业务规则

---

# 十七、Graph 目标结构

最终建议类似：

```text
START
↓
initialize
↓
knowledge_search
↓
evaluate_and_decide
   │
   ├── ANSWER
   │      ↓
   │   generate_answer
   │      ↓
   │     END
   │
   ├── REWRITE_QUERY
   │      ↓
   │   rewrite_query
   │      ↓
   │   knowledge_search
   │      ↓
   │   evaluate_and_decide
   │
   └── INSUFFICIENT
          ↓
      insufficient_answer
          ↓
         END
```

不要添加 Web 分支。

---

# 十八、Answer Generation

本次可以开始替换 Task 2 的 placeholder `finish()`。

实现一个最小：

```text
generate_answer
```

要求：

* 回答用户 `original_query`
* 只能基于 `selected_evidence` / KB Evidence
* 不允许模型用自身知识填补缺失事实
* 必须明确给 Sources
* 证据不足的部分不要伪造

Prompt 中明确要求：

> Answer only from supplied evidence.

---

# 十九、Partial Answer

我们已经确定 V1 的终止策略：

> 有可靠的部分证据时，可以回答已有部分，并明确指出缺失部分。

因此如果：

```text
EvidenceStatus = PARTIAL
```

且程序判定已有可靠 Evidence：

可以生成：

```text
Partial Answer
```

要求：

* 只回答证据支持的部分
* 清楚说明哪些部分当前知识库没有足够依据
* 不用模型常识补空白

---

# 二十、Insufficient Answer

如果：

```text
没有可靠 Evidence
```

或者：

```text
Rewrite 已耗尽
仍然无法支持答案
```

则生成明确不足提示。

例如语义上：

```text
当前知识库中没有找到足够证据回答这个问题。
```

不要让 LLM 自由补充答案。

这个结果可以程序模板生成，不一定必须再调用 LLM。

---

# 二十一、Sources

`generate_answer` 最终写入：

```text
sources
```

来源只能来自实际使用过的 KB Evidence。

至少尽量包含：

```text
article_id
chunk_id
title
```

如果项目已有可用 source schema，请复用。

不要生成不存在的 URL / article / title。

---

# 二十二、step_count 的语义

Task 2 已经让：

```text
knowledge_search
```

真正调用一次 Tool 时：

```text
step_count += 1
tool_call_counts["knowledge_search"] += 1
```

Task 3 请明确：

`step_count` 到底表示：

A. 所有 Graph Node 数量

还是：

B. 有意义的 Agent Action / Tool Step 数量

优先建议：

> 不要把每个内部 Node 都机械计数。

保持它表示 Agent 执行预算相关的“有意义步骤”。

至少 Knowledge Search 应继续计数。

Rewrite 是否计入 step_count，请根据一致语义决定，并写测试固定行为。

不要无意识改变 Task 2 已有计数语义。

---

# 二十三、Budget / Termination

Task 3 必须保证 Graph 一定能结束。

至少：

```text
max_rewrites = 1
```

建议预留：

```text
max_steps
```

但不要为了未来过度设计复杂 Budget Framework。

如果增加：

```text
max_steps
```

请提供明确默认值并程序级校验。

当预算耗尽：

* 有可靠 Partial Evidence → Partial Answer
* 没有可靠 Evidence → Insufficient Answer

不要无限循环。

---

# 二十四、Tool Error 情况

Task 2 已经区分：

```text
Empty Result
```

和：

```text
Execution Error
```

Task 3 继续保持。

如果 Knowledge Search 真正执行失败：

```text
last_tool_error != None
```

Decision Node 不能把它当作：

```text
kb_results == []
```

的普通无命中情况。

第一版不用实现复杂 Retry Agent。

可以直接进入安全终止：

```text
Insufficient / Error-safe response
```

或者项目认为合理的受控路径。

但不能让 LLM把 Tool Error 当成“知识库没有这个知识”。

---

# 二十五、Conversation Context

同一 `thread_id` 下：

```text
messages
```

继续通过 checkpoint 保留。

但是本 Task 不做长期 Memory。

也不要构建独立 Memory Store。

对于 follow-up question：

LLM Decision / Rewrite 可以合理使用近期 conversation messages 理解：

```text
它
这个
上面那个方案
```

但需要限制输入上下文规模，不要无脑把无限历史全部塞给 LLM。

第一版可以先使用当前已有 messages，如果尚未达到实际规模问题，但请避免建立“长期 Memory”概念。

---

# 二十六、测试要求

必须新增或更新自动化测试。

至少覆盖以下情况。

## Test 1：新一轮 Run State Reset

同一个：

```text
thread_id
```

先跑第一个问题。

第二次再输入完全不同的问题。

验证：

```text
messages
```

保留跨轮历史。

但是：

```text
original_query
current_query
rewrite_count
step_count
kb_results
selected_evidence
last_tool_error
final_answer
```

等 Run-level State 根据新 Run 设计正确 reset。

特别验证：

```text
original_query
```

不是整个 thread 的第一句话，而是当前用户问题。

---

## Test 2：Evidence 足够 → Answer

模拟 Knowledge Search 返回足够 Evidence。

模拟 Decision LLM：

```text
SUFFICIENT
ANSWER
```

验证：

```text
knowledge_search
→ evaluate_and_decide
→ generate_answer
→ END
```

不得经过 Rewrite。

---

## Test 3：第一次不足 → Rewrite → 再检索 → Answer

第一次 Search：

```text
Evidence 不足
```

Decision：

```text
REWRITE_QUERY
```

Rewrite：

```text
current_query 变化
rewrite_count = 1
```

第二次 Search 返回足够 Evidence。

然后：

```text
ANSWER
```

验证：

* `original_query` 不变
* `current_query` 已改变
* Search 调用两次
* rewrite 只发生一次
* 最终正常 END

---

## Test 4：Rewrite 后仍不足

第一次：

```text
REWRITE_QUERY
```

第二次仍没有足够 Evidence。

由于：

```text
rewrite_count == 1
```

验证：

```text
REWRITE_QUERY
```

已不再属于 `allowed_actions`。

最终：

```text
INSUFFICIENT
→ END
```

Graph 不得再次 Rewrite。

---

## Test 5：Empty Search Result

第一次返回：

```text
[]
```

如果有 Rewrite Budget：

可进入 Rewrite。

Rewrite 后仍为空：

必须安全终止。

不得生成事实性答案。

---

## Test 6：Knowledge Search Execution Error

模拟：

```text
TimeoutError
```

验证：

* Error 与 Empty Result 区分
* 不让 Decision LLM把错误当“无证据”
* Graph 可以安全终止
* 不无限重试

---

## Test 7：非法 LLM Action

模拟 LLM 返回：

```text
REWRITE_QUERY
```

但：

```text
allowed_actions
```

中已经没有该 Action。

程序必须拒绝或安全 fallback。

不能直接照做。

---

## Test 8：Structured Output Validation

模拟 malformed / invalid structured output。

验证：

* Pydantic / Schema Validation 能拦截
* Graph 不进入非法状态
* 有明确安全失败行为

---

## Test 9：Partial Answer

模拟：

```text
EvidenceStatus = PARTIAL
```

有可靠 Evidence，但不够覆盖全部问题。

验证最终答案：

* 使用已有 Evidence
* 明确说明缺失
* 不用模型知识填补

---

## Test 10：同一 thread checkpoint

验证：

* messages 可以跨轮继续
* Run-level State 不污染下一轮
* Graph checkpoint 仍正常工作

---

# 二十七、测试不得依赖真实外部服务

Agent 单元 / 集成测试优先：

* Fake LLM
* Stub Decision Service
* Stub Knowledge Search
* Dependency Injection

不得依赖：

* 真实百炼 / OpenAI API
* 外网
* 不稳定的数据库
* 真正 Embedding API

现有 Semantic Search 的真实逻辑已经有自己的测试。

Agent Graph 测试应该重点验证 orchestration。

---

# 二十八、建议模块职责

请根据现有目录结构自行判断，不强制文件名，但职责建议保持：

```text
agent/
├─ schemas.py
├─ state.py
├─ context.py
├─ nodes.py
├─ graph.py
├─ knowledge_search.py
├─ decision.py        # 如确实有必要
└─ prompting / prompts.py  # 如项目现有风格需要
```

不要为了“整洁”拆太多小文件。

---

# 二十九、开发前要求

先阅读：

* Task 1 Agent skeleton
* Task 2 Knowledge Search
* 当前 `AgentAction`
* 当前 `EvidenceStatus`
* 当前 `AgentState`
* 当前 `AgentContext`
* 当前 LLM Service / structured output 实现
* Stage 9 已有 LLM JSON / Pydantic 约束方式

优先复用已有 LLM Client / structured-output 机制。

不要新建第二套 AI Client。

---

# 三十、实现顺序

请按以下顺序：

1. 阅读 Task 1 / Task 2 当前代码。
2. 找出现有 LLM structured output 最合适的复用入口。
3. 给出简短实现计划。
4. 修正 Run-level / Conversation-level State 生命周期。
5. 定义最小 Agent Decision Schema。
6. 实现 allowed_actions 程序计算。
7. 实现 `evaluate_and_decide`。
8. 实现 bounded `rewrite_query`。
9. 实现 `generate_answer` / insufficient termination。
10. 添加 Conditional Edge。
11. 建立最多一次 Rewrite 的有界 Loop。
12. 增加测试。
13. 跑 Agent 定向测试。
14. 跑 Semantic Search / RAG 回归。
15. 跑完整后端测试。
16. 如环境允许跑前端生产构建。
17. `git diff --check`。
18. 总结。
19. 停止。

---

# 三十一、完成后必须汇报

## 1. 修改 / 新增文件

逐一说明职责。

## 2. 最终 Graph

用文本画出实际 Graph，例如：

```text
START
→ initialize
→ knowledge_search
→ evaluate_and_decide
   ├→ rewrite_query → knowledge_search → ...
   ├→ generate_answer → END
   └→ insufficient_answer → END
```

---

## 3. State 生命周期

明确说明：

哪些字段：

```text
Conversation-level
```

哪些：

```text
Run-level
```

以及新用户问题进入时具体 reset 了什么。

---

## 4. Decision 结构

说明：

* EvidenceStatus
* AgentAction
* allowed_actions
* Structured Output Schema
* 程序校验

---

## 5. Rewrite

说明：

* Rewrite Prompt / Service 如何工作
* 为什么只改 `current_query`
* `original_query` 如何保持
* Rewrite 硬限制如何保证

---

## 6. Evidence

说明：

* kb_results 如何进入评估
* selected_evidence 如何产生
* Partial / Insufficient 如何区分

---

## 7. Answer Grounding

说明：

最终 Answer 如何确保：

```text
只基于 Evidence
```

而不是模型自由知识。

---

## 8. Termination

说明所有能够结束 Graph 的路径。

特别说明：

> 为什么不可能无限 Rewrite。

---

## 9. Error

说明：

* Empty Result
* Tool Error
* Invalid LLM Output
* Illegal AgentAction

分别怎么处理。

---

## 10. 测试结果

明确给：

```text
Agent tests: X passed
Agent + Semantic Search + RAG: X passed
Full backend: X passed
Frontend build: passed / not run
git diff --check: passed
```

---

## 11. 明确没有做的内容

至少列：

```text
Web Search
fetch_web_page
get_article_content Agent Tool
save_to_knowledge_base
PostgreSQL checkpoint
Long-term Memory
Multi-Agent
```

---

# 三十二、验收标准

Task 3 只有同时满足以下条件才算完成：

* Knowledge Search 后有真实 Evidence Evaluation
* Decision 使用结构化输出
* allowed_actions 由程序控制
* LLM 只能在合法 Action 中决策
* 有 Conditional Edge
* Query Rewrite 已实现
* `original_query` 不被 Rewrite 修改
* `current_query` 可以被 Rewrite
* Rewrite 最多一次，并由程序硬限制
* Graph 存在真实有界 Loop
* Evidence 足够可 Answer
* Partial Evidence 可 Partial Answer
* 无可靠 Evidence 可 Insufficient
* Answer 不允许使用模型自身知识补齐
* Tool Error 与 Empty Result 区分
* 新一轮 Run-level State 会 reset
* messages 可以继续跨 thread checkpoint 保留
* 自动化测试覆盖主要路径
* 完整回归通过
* 没有提前实现 Web / Task 4
* 完成后停止开发

完成以上内容后，请停止，不要继续 Web Search 或其他 Agent Tool 开发。

