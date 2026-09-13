你现在要继续在现有 **GistAI / AI 阅读助手** 项目中完成 Stage 10 Agent V1 的第二批开发任务。

Task 1 已经完成：

* `AgentState`
* `AgentAction`
* `EvidenceStatus`
* LangGraph 最小 StateGraph
* `initialize`
* `finish`
* `InMemorySaver`
* `thread_id`
* 基础测试

当前 Graph：

```text
START
→ initialize
→ finish
→ END
```

当前完整后端测试：

```text
195 passed
```

本次只做：

> **Task 2：把现有 Semantic Search 能力包装成 Agent 的 Knowledge Search 能力，并接入 Graph。**

---

# 一、任务目标

本次目标不是实现完整 Agent Loop。

只需要让 Graph 能够完成：

```text
START
→ initialize
→ knowledge_search
→ finish
→ END
```

其中：

```text
knowledge_search
```

调用项目当前已经存在的 Semantic Search / Knowledge Base Search 业务能力。

最终验证：

> Agent State 中的 `current_query` 可以传入现有知识库检索能力，检索结果可以结构化写入 `kb_results`，然后继续流转到下一个 Node。

---

# 二、非常重要：任务边界

本次不要实现：

* Query Rewrite
* Evidence Evaluation
* EvaluateAndDecide
* Conditional Edge
* Agent Loop
* Web Search
* fetch_web_page
* get_article_content Agent Tool
* save_to_knowledge_base
* PostgreSQL checkpoint
* 长期 Memory
* 前端 Agent 页面
* 自动 Tool Calling
* LLM 自主选择 next_action
* Partial Answer 真实生成逻辑

这些属于后续 Task 3 或后续 Phase。

本次仍然保持固定 Graph：

```text
START
→ initialize
→ knowledge_search
→ finish
→ END
```

完成后停止，不继续实现下一阶段。

---

# 三、核心架构原则

必须继续遵守：

> **核心业务能力保持 LangGraph 无关，LangGraph 只负责 orchestration。**

因此不要：

```text
在 knowledge_search Node 中重新实现一套 pgvector 检索逻辑
```

而应该：

```text
knowledge_search Node
↓
调用已有 Semantic Search / Service
↓
拿到结构化结果
↓
写入 AgentState
```

现有 Stage 1～9 已经实现并测试过的 Semantic Search 主链路不要重写。

---

# 四、开发前先检查现有代码

请先找到当前项目已有的：

* Semantic Search Service
* RAG Retrieval Service
* pgvector 查询逻辑
* SemanticSearchHit 或对应 Schema
* threshold / top_k 的现有实现
* Router / Service 对 Semantic Search 的调用方式

先确认：

> 现有代码中哪一层最适合被 Agent 复用。

优先复用 Service 层，而不是让 Agent Node 调用 HTTP API Router。

如果当前 Semantic Search Service 已经足够复用，直接调用。

如果需要增加一个很薄的框架无关 wrapper，可以增加，但不要复制核心检索逻辑。

---

# 五、Knowledge Search 的职责

Agent 的 Knowledge Search 能力只负责：

> 接收检索 Query，返回知识库中的候选 Evidence。

它不负责：

* 判断证据是否足够
* 生成 Answer
* Query Rewrite
* 决定是否 Web Search
* 读取文章全文

Knowledge Search 的职责边界保持单一。

---

# 六、Knowledge Search 输入

第一版至少需要：

```text
query
top_k
```

其中：

```text
query
```

来自：

```text
state["current_query"]
```

`top_k` 第一版允许配置，但必须有程序范围限制。

建议范围：

```text
1 <= top_k <= 10
```

默认值：

```text
5
```

如果当前项目已有统一配置，请优先复用现有配置方式。

## threshold

不要让 Agent / LLM 自由传 `threshold`。

继续使用现有 Semantic Search 的 threshold 配置或默认值。

---

# 七、建议增加 Knowledge Search Input Schema

请根据当前项目代码风格选择 Pydantic 或现有 Schema 风格。

概念上类似：

```python
class KnowledgeSearchInput(...):
    query: str
    top_k: int = ...
```

要求：

* query 不能为空字符串
* top_k 有最小值 / 最大值约束
* 不接受任意未声明字段（如果现有项目 Schema 风格允许）

重点：

> Tool / Service 参数约束应该在程序层真实执行，而不是只靠 Prompt。

---

# 八、Knowledge Search 返回结果

不要只返回一大段字符串。

请尽量保持结构化。

至少包含后续 Agent 所需要的：

```text
article_id
chunk_id
title
chunk_text
score
```

如果现有 `SemanticSearchHit` Schema 已经包含这些或类似字段，请优先复用。

不要为了 Agent 重复定义一份几乎相同的业务 Schema，除非确实存在 Agent 层需要隔离的理由。

最终写入：

```text
state["kb_results"]
```

的数据应该是结构化、可序列化、方便测试和后续 Evidence Evaluation 的形式。

---

# 九、Empty Result 与 Error 必须分开

这是本 Task 的重要要求。

如果 Semantic Search 正常执行，只是没有命中：

```text
results = []
```

这是：

> 正常成功结果。

不能把它当作 Tool Error。

应该：

```text
kb_results = []
last_tool_error = None
```

---

如果发生真正的执行错误，比如：

```text
数据库连接异常
Embedding Service 异常
内部检索异常
```

则需要：

```text
last_tool_error
```

记录结构化或至少明确的错误信息。

本次不要求完成复杂 Retry Loop。

但要保证：

> Empty Result 与 Execution Error 在 State 上可以明确区分。

---

# 十、Retry 范围

本 Task 暂时不要实现完整 Agent Retry 策略。

如果现有 Semantic Search Service 本身已有 Retry，可以继续复用。

如果没有，不要为了 Task 2 新增复杂 Retry Framework。

后续 Task 会统一处理：

```text
Retryable Error
Non-retryable Error
Tool Retry Count
```

本次重点只是：

> Error 能被捕获并正确反映到 Agent State，不让 Graph 无信息崩溃。

如果你判断异常应该继续抛出以符合项目当前风格，也请在完成总结中说明原因。

---

# 十一、knowledge_search Node

新增或实现：

```text
knowledge_search
```

Node 输入主要读取：

```text
current_query
```

必要时读取配置中的默认：

```text
top_k
```

然后：

```text
调用已有 Semantic Search Service
```

Node 返回只需要更新必要字段，例如：

```text
kb_results
tool_call_counts
step_count
last_tool_error
```

不要返回完整 AgentState。

继续使用 LangGraph partial state update 模式。

---

# 十二、计数器

本次开始让：

```text
step_count
tool_call_counts
```

有真实意义。

例如成功或尝试调用 Knowledge Search 后：

```text
step_count += 1
tool_call_counts["knowledge_search"] += 1
```

具体“异常情况下是否也计数”请根据一致性原则选择，并写测试明确行为。

建议：

> 只要真正尝试执行了一次 Tool，就计为一次 Tool Call，即使最终发生 Execution Error。

---

# 十三、Graph 修改

Task 1 当前：

```text
START
→ initialize
→ finish
→ END
```

Task 2 修改为：

```text
START
→ initialize
→ knowledge_search
→ finish
→ END
```

本次仍然只使用普通 Edge。

不要增加 Conditional Edge。

不要根据 Search Result 做分支。

这些属于 Task 3。

---

# 十四、finish Node

Task 2 暂时可以继续保留现有 smoke-test placeholder：

```text
Agent graph initialized successfully.
```

不要求生成真实 RAG Answer。

如果你认为这个 placeholder 名称已经明显不准确，可以轻微调整成更通用的测试占位文本，但不要引入 LLM Answer Generation。

重点仍然是验证：

```text
State
→ Knowledge Search
→ State
```

已经跑通。

---

# 十五、测试要求

必须增加自动化测试。

至少覆盖以下场景。

## Test 1：Knowledge Search Node 能写入结果

使用 Stub / Mock 替代真实 Embedding / Database 外部依赖。

输入：

```text
current_query = "Agent Memory"
```

模拟 Search 返回至少一个结果。

验证：

```text
kb_results
```

正确写入 State。

同时验证：

```text
step_count
tool_call_counts["knowledge_search"]
last_tool_error
```

符合预期。

---

## Test 2：Empty Result 是正常结果

模拟 Semantic Search：

```text
[]
```

验证：

```text
kb_results == []
last_tool_error is None
```

不要把空结果视为失败。

---

## Test 3：Execution Error

模拟 Search Service 抛出异常，例如：

```text
TimeoutError
```

或者符合项目现有错误类型的异常。

验证：

```text
last_tool_error
```

被正确记录或异常按预期处理。

必须让测试明确表达：

> Execution Error 与 Empty Result 不同。

---

## Test 4：Graph 集成

完整 invoke：

```text
START
→ initialize
→ knowledge_search
→ finish
→ END
```

验证：

* Graph 可以运行完成
* Search Node 被调用
* kb_results 进入最终 State
* checkpoint 仍正常工作

---

## Test 5：top_k 参数约束

至少测试：

```text
合法 top_k
```

以及一个超出范围的值。

验证 Schema / 参数约束真正生效。

不要只写 Prompt 说明。

---

# 十六、测试实现要求

测试尽量使用：

* Stub
* Mock
* Dependency Injection
* 项目现有 Test Double 风格

不要让 Agent 单元测试依赖：

* 真实 LLM API
* 真实 Embedding API
* 外网
* 不稳定的第三方服务

如果现有项目已有 Fake / Stub 模式，请优先沿用。

---

# 十七、兼容性要求

不能破坏现有 Stage 1～9 功能。

完成后至少运行：

1. Agent Task 2 新增测试
2. Semantic Search / RAG 相关已有测试
3. 完整后端测试
4. `git diff --check`

如果环境允许，也继续验证前端生产构建未受影响。

不得为了新 Agent 测试而修改现有 Semantic Search 的正确业务行为。

---

# 十八、禁止过度设计

本次不要增加：

* 通用 Tool Registry
* BaseTool 大型继承体系
* Tool Plugin Framework
* Dynamic Tool Discovery
* 多 Agent
* Planner / Executor
* Reflection
* Reranker
* Query Expansion
* 新 Vector Database
* 新数据库表
* 新 Alembic migration

只完成：

> **已有 Knowledge Search 能力 → Agent 可复用能力 → LangGraph Node → State**

---

# 十九、实现顺序

请按以下顺序执行：

1. 阅读当前 Semantic Search / RAG Service。
2. 确认最合适的复用入口。
3. 给出简短实现计划。
4. 增加最小 Knowledge Search Input / Result Schema（如果确实需要）。
5. 实现框架无关 Knowledge Search wrapper（如果现有 Service 不适合直接复用）。
6. 实现 `knowledge_search` Node。
7. 更新 Graph Edge。
8. 增加测试。
9. 运行定向测试。
10. 运行相关回归。
11. 运行完整后端测试。
12. 总结实现结果。
13. 停止开发。

---

# 二十、完成后请输出

完成后请明确给出：

## 1. 修改 / 新增文件

逐个列出职责。

## 2. 现有 Semantic Search 是如何复用的

说明：

```text
Agent Node
→ 哪个 Service / Function
→ pgvector / Retrieval
```

不要只说“已复用”。

## 3. 当前 Graph 调用链

应该类似：

```text
START
→ initialize
→ knowledge_search
→ finish
→ END
```

## 4. Knowledge Search Input / Result

说明：

* query 从哪里来
* top_k 怎么限制
* threshold 谁控制
* 返回结果有哪些核心字段

## 5. Empty Result / Error 如何区分

给出当前实际行为。

## 6. step_count / tool_call_counts

说明具体什么时候递增。

## 7. 测试结果

明确给：

```text
X passed
```

并说明：

* Agent 定向测试
* Semantic Search / RAG 相关测试
* 完整后端测试

## 8. 本次明确没有实现的内容

再次列出至少：

```text
Query Rewrite
Evidence Evaluation
Conditional Edge
Agent Loop
Web Search
fetch_web_page
get_article_content Agent Tool
save_to_knowledge_base
PostgreSQL checkpoint
```

---

# 二十一、验收标准

只有同时满足以下条件才算 Task 2 完成：

* 复用了已有 Semantic Search 核心逻辑
* 没有在 Node 中重新实现 pgvector 检索
* `knowledge_search` Node 已存在
* `current_query` 能进入知识库检索
* 结构化结果进入 `kb_results`
* Empty Result 与 Execution Error 能区分
* top_k 有真实程序约束
* step_count / tool_call_counts 有明确行为
* Graph 已变成 `initialize → knowledge_search → finish`
* 自动化测试覆盖正常、空结果、错误、集成
* 完整回归没有被破坏
* 没有提前实现 Task 3
* 完成后停止开发

完成上述内容后，请停止，不要继续实现 Query Rewrite、Evidence Evaluation 或 Agent Loop。

