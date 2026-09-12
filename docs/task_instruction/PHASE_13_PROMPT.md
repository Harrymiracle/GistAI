你现在要在现有 **GistAI / AI 阅读助手** 项目中实现 Stage 10 Agent V1 的第一批开发任务。

## 一、任务目标

本次只完成：

> **Agent 基础骨架**

目标是把 LangGraph 的最小工程骨架搭起来，让项目具备：

* AgentState
* 基础 Enum / Schema
* LangGraph StateGraph
* 最小 Node
* 基础 Edge
* In-memory Checkpoint
* 最小 Smoke Test

本次重点不是实现完整 Agent 功能，而是验证：

> State 能否进入 Graph → Node 能否读取/更新 State → Edge 能否正确流转 → Graph 能否结束 → 同一个 thread_id 能否使用 checkpoint。

---

## 二、非常重要：任务边界

本次 **不要实现** 以下功能：

* 不接 Web Search
* 不实现 fetch_web_page
* 不实现 save_to_knowledge_base
* 不接 PostgreSQL checkpoint
* 不实现完整 Query Rewrite
* 不实现完整 Evidence Evaluation
* 不实现 Agent Loop
* 不接真实 Knowledge Base Semantic Search
* 不修改现有 RAG 主链路
* 不重构现有 Stage 1～9 已经稳定的业务代码
* 不为了 LangGraph 大范围调整项目目录结构
* 不增加不必要的框架或复杂抽象

这些属于后续 Task 2 / Task 3。

本次原则：

> **只搭骨架，不提前开发后续功能。**

---

## 三、项目现状

当前项目已经有较完整的 AI 阅读助手后端能力，包括：

* FastAPI
* Pydantic
* SQLAlchemy
* PostgreSQL + pgvector
* Semantic Search
* Basic RAG
* Article / Chunk / Embedding
* AI Summary / Tags
* HTTP + Playwright 抓取
* SSRF 防护
* Service Layer
* 测试体系

Stage 10 开始做 Agent 化。

Agent 的定位：

> 核心业务能力保持框架无关，LangGraph 只负责编排 Agent 流程。

因此不要把业务逻辑硬编码到 LangGraph Node 中。

---

## 四、Agent V1 当前架构原则

确定性流程继续保持 Workflow。

Agent 主要负责知识使用侧的动态决策。

核心原则：

1. 程序控制边界。
2. LLM 以后只在允许范围内做决策。
3. Agent Framework 是 orchestration layer，不是 business logic layer。
4. State 只保存后续节点真正需要的数据。
5. Graph 不要拆成大量无意义的小 Node。
6. 第一阶段先用 In-memory checkpoint。
7. API / Graph 层提前保留 thread_id 概念，后续可切 PostgreSQL checkpoint。
8. 当前只支持 conversation context，不做 long-term memory。

---

## 五、本次需要实现的 AgentState

请根据项目现有代码风格，使用合适的 Python 类型定义 AgentState。

第一版至少考虑这些字段：

```python
messages

original_query
current_query

intent
allow_web
requires_freshness

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

但是注意：

### 本次 Task 1 不要求所有字段都有真实业务逻辑。

可以：

* 给出合理默认值
* 使用 Optional / list / dict 等合适类型
* 暂时为空
* 为后续 Task 2 / Task 3 留接口

不要为了填满字段而实现后续业务。

---

## 六、建议增加基础 Enum / Schema

请根据现有项目代码风格判断文件位置和命名。

建议至少有：

### AgentAction

例如：

```python
KNOWLEDGE_SEARCH
REWRITE_QUERY
WEB_SEARCH
GET_ARTICLE_CONTENT
FETCH_WEB_PAGE
ANSWER
PARTIAL_ANSWER
INSUFFICIENT
```

### EvidenceStatus

第一版可以简单：

```python
UNKNOWN
SUFFICIENT
INSUFFICIENT
```

如果你认为现有项目命名风格不适合，可以调整命名，但不要扩大范围。

---

## 七、本次 Graph 只需要最小闭环

本次不要实现真实 Agent Loop。

只需要搭一个最小 StateGraph，例如概念上：

```text
START
↓
initialize
↓
finish
↓
END
```

或者类似最小结构。

### initialize Node

负责：

* 从 State 读取用户当前输入
* 如果 original_query 尚未设置，则进行基础初始化
* 初始化 current_query
* 初始化必要的计数器
* 不调用真实 LLM
* 不调用真实 Knowledge Search

### finish Node

负责：

* 写入一个简单、可测试的占位 final_answer
* 用于证明 State 能正确流转到 END

例如可以是类似：

```text
Agent graph initialized successfully.
```

但请根据项目风格选择合适实现。

这个回答只是 smoke-test placeholder，不是正式产品逻辑。

---

## 八、Checkpoint

第一阶段使用：

> In-memory checkpoint

要求：

* Graph 编译时挂载 in-memory checkpointer
* 支持 config 中传 thread_id
* 测试中验证同一个 thread_id 可以正常运行

暂时不要：

* PostgreSQL checkpoint
* 新建 conversation 数据库表
* 新建 Alembic migration

这些后续再做。

---

## 九、目录和架构要求

请先阅读项目现有目录结构和代码风格。

优先遵循现有：

* router
* service
* schema
* model
* core
* tests

等组织方式。

如果需要增加 agent 模块，建议保持集中，例如：

```text
app/
  agent/
    state.py
    schemas.py
    graph.py
    nodes.py
```

这里只是参考。

如果项目现有目录结构有更合理的位置，请遵循现有结构，不要为了匹配这个示例而强行调整整个项目。

---

## 十、依赖处理

先检查项目是否已经安装 LangGraph。

如果没有：

* 增加最小必要依赖
* 不升级与任务无关的包
* 不随意修改已有核心依赖版本

如果 LangGraph API 与当前项目版本存在差异，以当前实际安装版本的官方 API 为准。

---

## 十一、测试要求

必须写最小测试。

至少覆盖：

### Test 1：Graph 可以运行

输入一个用户问题。

验证：

* Graph 可以 invoke 成功
* 不抛异常
* State 正常经过 initialize / finish
* final_answer 存在

### Test 2：State 初始化正确

例如输入：

```text
What is Agent Memory?
```

验证：

```text
original_query
current_query
```

被正确初始化。

验证：

```text
rewrite_count == 0
step_count
```

等基础控制字段符合预期。

### Test 3：thread_id / checkpoint

使用同一个 thread_id 执行 Graph。

验证：

* checkpointer 可以正常工作
* config 格式正确
* 不出现 checkpoint 相关异常

本次不要求测试复杂 conversation memory 行为，只验证基础 checkpoint 集成。

---

## 十二、兼容性要求

非常重要：

本次修改不能破坏已有 Stage 1～9 功能。

完成后至少运行：

1. 新增 Agent 测试
2. 与本次改动相关的已有测试
3. 如果成本允许，运行完整后端测试

如果已有完整测试很多，可以先运行 Agent 相关测试和核心后端测试，再报告完整测试是否执行。

不要为了让新测试通过而修改与 Agent 无关的已有业务行为。

---

## 十三、不要做过度设计

本次请避免：

* Generic Tool Registry
* 复杂 Agent Plugin System
* 多 Agent
* Planner / Executor 架构
* Reflection
* Long-term Memory
* 自定义复杂 Middleware
* Event Bus
* 自建 Workflow Engine
* 大量 BaseAgent / AbstractAgent 类
* 提前设计未来几十个 Tool

目标只是：

> **建立一个干净、能运行、能测试、方便下一步扩展的 LangGraph 基础骨架。**

---

## 十四、实现方式

请按以下顺序工作：

1. 阅读当前项目结构和与 RAG / Service / Schema / Test 相关代码。
2. 给出简短的实现计划。
3. 实现 AgentState 和基础 Schema / Enum。
4. 实现最小 Node。
5. 创建并编译 StateGraph。
6. 接入 In-memory checkpoint。
7. 编写测试。
8. 运行测试。
9. 如果测试失败，定位并修复。
10. 最后总结改动。

---

## 十五、完成后请输出

完成后不要只说“Done”。

请明确告诉我：

### 1. 修改 / 新增了哪些文件

逐个列出，并说明职责。

### 2. Graph 当前调用链

例如：

```text
START
→ initialize
→ finish
→ END
```

### 3. AgentState 当前有哪些关键字段

不用重复所有代码，但说明主要分类。

### 4. Checkpoint 怎么接入的

说明：

* 使用什么 in-memory checkpointer
* thread_id 从哪里进入

### 5. 测试结果

明确给出：

```text
X passed
```

如果有失败，不能隐藏。

### 6. 本次明确没有实现什么

至少再次说明：

```text
Web Search
Knowledge Search
Query Rewrite
Agent Loop
PostgreSQL checkpoint
save_to_knowledge_base
```

仍然没有实现。

---

## 十六、验收标准

只有同时满足以下条件，本 Task 才算完成：

* AgentState 已存在
* 基础 Action / Evidence Schema 已存在
* LangGraph 能 compile
* 最小 Graph 能 invoke
* State 能正确流转
* In-memory checkpoint 能使用 thread_id
* 有自动化测试
* 新增测试通过
* 没有破坏现有核心功能
* 没有提前实现 Task 2 / Task 3
* 核心 Service 层没有绑死在 LangGraph 上

完成上述内容后停止开发，不要继续实现下一阶段。

