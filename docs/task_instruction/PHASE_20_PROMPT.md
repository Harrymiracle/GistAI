你现在要继续在现有 **GistAI / AI 阅读助手** 项目中完成 Stage 10 Agent V1 的第八批开发任务。

Phase 19 / Task 7 已完成。

当前项目已经具备：

* URL 抓取 / Playwright fallback
* 正文提取与清洗
* AI Summary / Tags
* Token Chunking
* Embedding
* PostgreSQL + pgvector
* Semantic Search / RAG
* LangGraph Agent
* Runtime Context
* Knowledge Search
* Query Rewrite
* Evidence Decision
* Controlled Web Search
* KB Article Full-text Read
* Web Page Full-text Fetch
* Full-text Temporary Chunking
* Context Budget
* Runtime Policy
* Tool Budget
* Global `MAX_STEPS`
* Error Classification
* Safe Termination
* Partial / Insufficient
* Agent HTTP API
* Frontend Agent Chat MVP
* `thread_id`
* KB / Web Sources
* InMemory checkpoint

当前完整后端测试基线：

```text
301 passed
```

当前主要限制：

> Agent checkpoint 仍使用 `InMemorySaver`。

因此：

* 服务重启后 conversation context 丢失。
* 多进程 / 多实例环境无法依赖单进程内存保持会话。
* `thread_id` API 已经存在，但 persistence 还没有真正落到数据库。

---

# 一、本次 Task 总目标

本次只完成：

> **PostgreSQL Checkpoint 持久化 + V1 最终综合验收与收尾。**

核心目标：

```text
当前：
thread_id
→ InMemorySaver
→ 进程内 conversation state

Task 8 后：
thread_id
→ PostgreSQL Checkpointer
→ 持久化 conversation state
```

同时保持：

```text
Frontend API Contract 不变
```

即：

```json
{
  "message": "...",
  "thread_id": "..."
}
```

仍然是前端唯一需要关心的会话接口。

---

# 二、严格范围

本 Task 不实现：

* Long-term Memory
* 用户画像
* Semantic Memory
* 跨 conversation Memory
* `save_to_knowledge_base`
* 自动保存 Web 内容
* Multi-Agent
* Planner
* Reflection
* Streaming
* SSE
* WebSocket
* Conversation rename
* Conversation list UI
* Conversation delete UI
* 历史会话管理中心
* Redis
* Distributed Queue
* Celery
* Reranker
* Agent Analytics Dashboard
* Tool Timeline UI
* 大型前端重构
* 新业务功能

本 Task 是：

> **V1 persistence + final hardening。**

完成后停止开发。

---

# 三、先审计当前 Checkpoint 使用方式

开始前请先检查：

* `create_agent_graph`
* `agent_graph`
* `InMemorySaver`
* API dependency lifecycle
* `thread_id`
* internal checkpoint key
* 当前 `user_id:thread_id` 组合方式
* Agent API service
* FastAPI startup / shutdown
* DB engine
* SQLAlchemy session lifecycle
* 当前 PostgreSQL 配置
* Docker Compose
* Alembic

先明确：

> 当前 checkpointer 是在哪里创建、由谁持有、生命周期多长。

不要直接替换。

---

# 四、Checkpoint 与业务数据库职责必须区分

当前项目已有业务表：

```text
articles
tags
article_tags
article_chunks
...
```

Checkpoint 用于：

> LangGraph conversation / execution state persistence。

它不是：

* Article 数据库
* Chat message 产品数据库
* Long-term Memory
* Knowledge Base

必须在代码和最终总结中明确这个区别。

---

# 五、使用官方 / 当前 LangGraph 推荐 PostgreSQL Checkpointer

优先使用当前安装的 LangGraph / LangGraph Checkpoint PostgreSQL 官方方案。

不要自己手写：

```text
agent_checkpoints
```

然后手工 serialize 整个 State，除非现有官方库确实无法满足。

请首先检查当前 dependency / LangGraph 版本。

如果需要增加官方依赖，例如：

```text
langgraph-checkpoint-postgres
```

请：

* 使用与现有 LangGraph 版本兼容的版本。
* 更新 requirements。
* 运行 pip check。

不要引入未知第三方 checkpoint framework。

---

# 六、数据库复用原则

优先复用当前 PostgreSQL 实例。

但要区分：

```text
业务 SQLAlchemy engine
```

与：

```text
LangGraph checkpointer connection/pool
```

不要强行把 SQLAlchemy Session 塞给 Checkpointer，如果官方 Checkpointer 要求 psycopg connection / pool。

采用官方推荐方式。

---

# 七、Checkpoint 配置

建议增加明确配置，例如：

```text
AGENT_CHECKPOINT_BACKEND=postgres
```

或更简单：

```text
DATABASE_URL
```

直接用于 PostgreSQL checkpointer。

具体按项目现有 config 设计。

不要：

* 写死 localhost
* 写死用户名密码
* 提交 `.env`

更新：

```text
.env.example
```

只提供示例。

---

# 八、环境行为

V1 推荐：

## Production / Normal Runtime

使用：

```text
PostgreSQL Checkpointer
```

## Tests

允许：

```text
InMemorySaver
```

作为单元测试 fake / fast path。

不要让所有单元测试都必须启动真实 PostgreSQL。

---

# 九、Checkpointer Dependency Injection

避免继续：

```python
agent_graph = create_agent_graph()
```

然后内部永远绑定固定 `InMemorySaver`，如果这会阻碍测试 / 生产切换。

Task 8 应让：

```text
Graph
+
Checkpointer
```

生命周期更清晰。

例如概念上：

```text
create_agent_graph(checkpointer)
```

或：

```text
AgentGraphFactory
```

具体采用现有项目最小改动方案。

不要为了 DI 做大型架构重写。

---

# 十、应用生命周期

PostgreSQL checkpointer 如果使用连接池或长期 connection：

必须正确处理：

```text
startup
shutdown
```

避免：

* 每个请求创建一整个数据库连接池
* 每个 Node 创建 Checkpointer
* 连接泄漏

优先一个应用级 Checkpointer / pool。

---

# 十一、Checkpoint 初始化

如果官方 PostgreSQL Checkpointer 需要执行：

```text
setup()
```

或初始化自身表结构：

请按官方推荐流程实现。

注意：

> Checkpointer 自己的内部表不一定应该由项目 Alembic 管理。

如果官方方案自带 setup：

优先使用官方 setup。

不要重复维护同一 schema。

最终总结必须说明：

* Checkpoint 表是谁创建的。
* 是否经过 Alembic。
* 为什么。

---

# 十二、Migration 边界

如果官方 Checkpointer 自带 schema setup：

本 Task 不需要创建业务 Alembic migration。

如果确实必须创建 migration：

仅创建 Checkpoint 必要结构。

不要同时修改 Article / Chunk schema。

---

# 十三、thread_id API 保持完全兼容

Task 7 已经定义：

```text
POST /api/v1/agent/chat
```

请求：

```json
{
  "message": "...",
  "thread_id": "optional UUID"
}
```

Task 8 后：

API contract 不允许因为 checkpoint backend 改变而变化。

前端：

> 不应该知道后端从 InMemory 改成 PostgreSQL。

---

# 十四、用户隔离必须继续保持

Task 7 已实现：

```text
internal checkpoint key
=
user_id : public_thread_id
```

Task 8 必须保持或提供等价的服务器端隔离。

即：

用户 A：

```text
userA:thread123
```

用户 B：

```text
userB:thread123
```

必须是两个不同 conversation。

---

# 十五、不要把 user_id 暴露给客户端

继续禁止：

```json
{
  "user_id": "..."
}
```

用户身份只能来自服务端 auth / dependency。

---

# 十六、服务重启恢复测试

Task 8 最重要的新能力就是：

> 服务 / Graph 实例重建后，同一个用户 + thread_id 还能恢复 conversation。

测试必须覆盖：

```text
Graph instance A
→ first question
→ checkpoint 写 PostgreSQL

销毁 Graph A

Graph instance B
→ same user + same thread_id
→ follow-up
→ 能恢复之前 messages
```

这个测试才真正证明：

> persistence 不是进程内对象复用。

---

# 十七、不同 thread 隔离

验证：

```text
user A + thread 1
user A + thread 2
```

不会共享 conversation。

---

# 十八、不同用户隔离

验证：

```text
user A + thread X
user B + thread X
```

不会共享 checkpoint。

这是安全测试。

---

# 十九、Run-level Reset 仍必须成立

Checkpoint 持久化后尤其要防止：

> 上一轮 Run-level State 被错误带入下一问题。

同一个 thread 新问题开始时：

仍然必须 reset：

```text
original_query
current_query

kb_results
web_results
article_contents
web_page_contents

selected_evidence

rewrite_count
step_count
tool_call_counts

allowed_actions
next_action

read_article_ids
fetched_web_urls

last_error
last_tool_result

action_history
sources
final_answer
```

而：

```text
messages
```

继续从 checkpoint 中恢复。

---

# 二十、Checkpoint 不等于 Run State 永久累积

要特别验证：

```text
messages
```

跨轮次保留。

但是：

```text
step_count
```

不能不断：

```text
8 → 16 → 24
```

累积。

每个新 Run 必须重新：

```text
0
```

---

# 二十一、Checkpoint Failure

如果 PostgreSQL Checkpointer 暂时不可用：

不要：

* 自动退回 InMemory 然后假装 persistence 正常
* 静默忽略
* 泄露 DB exception

正式运行环境应：

> Fail clearly and safely。

具体可以：

* API safe 500
* 应用 startup failure

根据当前架构选择更合理方案。

不要 silently downgrade。

---

# 二十二、Checkpoint 错误信息

不要向前端暴露：

* DB host
* DB user
* connection string
* SQL
* psycopg raw exception
* stack trace

继续使用现有安全异常机制。

---

# 二十三、Conversation Message 增长问题

Task 8 不需要做复杂 Memory Compression。

但是要检查当前：

```text
MessagesState
```

是否会无限增长。

V1 可以接受一定长度的历史。

至少：

* 在 README / final report 记录这是当前限制。
* 不要本 Task 临时实现 Summarization Memory。
* 不要随意 truncate 导致上下文丢失。

---

# 二十四、Checkpoint 数据中禁止写入不可序列化 Runtime Dependency

再次验证：

```text
DB Session
EmbeddingService
WebSearchService
ArticleContentService
CrawlerService
```

仍然只在：

```text
AgentContext
```

不能进入 AgentState/checkpoint。

---

# 二十五、敏感信息审计

检查 Checkpoint State 不应该存：

* API Key
* DB Password
* HTTP Authorization Header
* raw secret
* Runtime Service Object

State 中允许：

* messages
* query
* evidence metadata
* counters
* safe errors
* final answer
* sources

---

# 二十六、Full Content Checkpoint 风险审计

Task 5 当前：

```text
article_contents
web_page_contents
```

可能包含完整 `clean_content`。

现在换 PostgreSQL checkpoint 后，这一点需要认真审计。

目标：

> 避免因为 checkpoint 把大量全文永久复制进 LangGraph checkpoint 数据。

请检查当前 State 生命周期。

如果每一个 intermediate checkpoint 都保存：

```text
完整网页全文
```

可能造成：

* checkpoint 数据膨胀
* DB 存储快速增长
* serialization 成本
* privacy 范围扩大

Task 8 允许做一个**最小必要优化**：

> 将不需要跨 Node / Resume 持久保存的大型全文数据从 checkpoint State 中移出，或在完成 evidence selection 后及时清理。

但不要破坏 Task 5 行为。

---

# 二十七、大对象 State 优化原则

优先目标：

```text
full content
→ 临时读取
→ select relevant evidence
→ State 只长期保留 selected evidence
```

如果 Graph Node 间确实需要完整内容：

允许短暂存在 State。

但在：

```text
selected evidence
```

生成完成后，应考虑清理：

```text
article_contents
web_page_contents
```

中的大正文。

必须有回归测试。

---

# 二十八、不要过度优化 Checkpoint Size

Task 8 只解决明显的大对象问题。

不要做：

* 自定义 blob storage
* S3
* Redis cache
* compressed external store
* custom checkpoint serialization

---

# 二十九、正式 Final E2E 验收

Task 8 除了 Checkpoint，还要做一次 V1 综合验收。

至少覆盖：

## Scenario A：KB-only

用户：

```text
“只根据我的知识库回答……”
```

验证：

* allow_web=False
* KB Search
* 可能读取 KB full text
* answer
* KB sources

---

## Scenario B：Query Rewrite

初始 KB Search 不理想。

验证：

```text
rewrite <= 1
→ second KB search
```

---

## Scenario C：Fresh / Web

用户问：

```text
“最近……”
```

验证：

* requires_freshness=True
* Web Search allowed
* 必须包含 Web evidence 才能满足 freshness
* Web source 正常返回

---

## Scenario D：Web Full-text

Snippet 不足。

验证：

```text
Web Search
→ Fetch Web Page
→ fulltext selected evidence
→ answer
```

---

## Scenario E：KB Full-text

Chunk 不足。

验证：

```text
Knowledge Search
→ Get Article Content
→ temporary chunk
→ evidence
→ answer
```

---

## Scenario F：Partial

有可靠证据但不完整。

验证：

```text
status=partial
```

---

## Scenario G：Insufficient

无可靠证据。

验证：

```text
status=insufficient
```

不允许模型自由补充。

---

## Scenario H：Budget Exhaustion

逼近：

```text
MAX_STEPS
```

验证 Agent 一定结束。

---

## Scenario I：Tool Error

模拟：

```text
Web Search Timeout
Fetch failure
DB failure
```

验证：

* error 分类正确
* 安全终止
* 不泄露内部异常

---

## Scenario J：Conversation Follow-up

第一问：

```text
“Agent Memory 是什么？”
```

第二问：

```text
“那它和长期 Memory 有什么区别？”
```

同一个 `thread_id`。

验证 checkpoint conversation context。

---

## Scenario K：Process Recreation

新的 Graph / Checkpointer 实例继续同一个 thread。

验证 PostgreSQL persistence。

---

# 三十、Frontend 最终验收

不新增复杂 UI。

只检查：

* `/agent` 页面可访问
* 发送问题正常
* follow-up 正常
* New Chat 正常
* loading 正常
* partial 正常
* insufficient 正常
* error 正常
* KB source 正常
* Web source 正常
* 外部 URL 安全打开
* 不展示内部 Runtime 字段

---

# 三十一、README 最终最小更新

更新 README，至少包含：

## Architecture

```text
Ingestion Pipeline
RAG
Agent
Frontend
```

## Agent capabilities

说明：

* KB Search
* Rewrite
* Web Search
* Full-text Read
* Evidence Evaluation
* Runtime Policy
* PostgreSQL Checkpoint

## API

```text
POST /api/v1/agent/chat
```

## thread_id

说明：

* conversation id
* server-side user isolation
* PostgreSQL persistence

## Limitations

明确：

* no long-term memory
* no streaming
* no multi-agent
* no conversation management UI

不要写成大型教程。

---

# 三十二、Architecture 文档一致性

如果仓库里已有：

```text
Stage10 Agent Architecture
```

文档，请最小更新：

```text
InMemory checkpoint
```

为：

```text
PostgreSQL checkpoint
```

并区分：

```text
V1 implemented
Future
```

不要让文档和代码不一致。

---

# 三十三、测试策略

## Unit Tests

仍使用：

```text
InMemorySaver / fake checkpointer
```

测试 Runtime Policy、Decision 等。

## Integration Tests

新增 PostgreSQL checkpoint integration tests。

如果 CI / 本地测试已有 test DB：

复用。

不要让所有 300+ 单元测试都强依赖 Postgres checkpoint。

---

# 三十四、PostgreSQL Integration Test 隔离

测试之间必须使用独立：

```text
thread_id
```

最好也避免共享 checkpoint namespace。

测试结束后：

* 清理测试 checkpoint data
* 或使用隔离 test database/schema

按官方库能力选择最安全方式。

---

# 三十五、不要污染生产数据库

测试绝不能直接使用生产 `DATABASE_URL`。

继续使用项目现有 test DB 策略。

---

# 三十六、依赖验证

如果增加：

```text
psycopg
langgraph-checkpoint-postgres
```

或类似依赖：

运行：

```text
pip check
```

并确认版本与：

```text
langgraph
langchain
```

兼容。

---

# 三十七、Docker 验证

如果当前 Docker Compose PostgreSQL 已能支持：

无需新增数据库容器。

只确认：

```text
PostgreSQL
+
pgvector
+
LangGraph checkpoint tables
```

可以共存。

---

# 三十八、性能最小检查

不用 Benchmark。

只确认：

* Checkpointer 不会每请求创建 pool。
* 不会每 Node 新建连接池。
* 不会把完整 Article DB 复制成长期 checkpoint 数据。
* conversation follow-up 延迟没有异常级退化。

---

# 三十九、项目最终代码审计

Task 8 完成前，对 Stage 10 做一次整体审计。

重点检查：

```text
app/agent/
```

是否存在：

* 重复 Budget 常量
* 已废弃 InMemory-only 逻辑
* 未使用 import
* 未使用 Schema
* 旧 Action
* 死代码
* TODO 和实际实现冲突
* unsafe error
* debug print
* secret logging

仅清理明确安全的内容。

不要趁收尾大规模重构。

---

# 四十、最终有界性再次验证

确认最终仍然：

```text
KB Search       <= 2
Rewrite         <= 1
Web Search      <= 1
Article Read    <= 2
Web Page Fetch  <= 2
MAX_STEPS       = 8
```

Checkpoint persistence 不得破坏：

> 每个 Run 的预算从 0 开始。

---

# 四十一、最终 Source Grounding 验证

再次验证：

最终 Answer：

```text
只使用 selected_evidence
```

Sources：

```text
只从实际用于回答的 Evidence 生成
```

不要因为 checkpoint 恢复旧 Sources 而污染新回答。

---

# 四十二、Final V1 Boundary

Task 8 完成后，请在报告中明确：

> GistAI Agent V1 开发阶段完成。

V1 包含：

```text
Knowledge Ingestion
Vector Search
RAG
Agent Decision Loop
Controlled Web Search
Full-text Reading
Evidence Grounding
Runtime Policy
Persistent Conversation Checkpoint
Agent API
Frontend Chat MVP
```

V1 不包含：

```text
Long-term Memory
Conversation Management
Streaming
Multi-Agent
Auto-save Web Content
Reranker
```

---

# 四十三、开发顺序

请严格按照：

1. 审计当前 InMemory Checkpointer。
2. 检查当前 LangGraph / dependency 版本。
3. 确定官方 PostgreSQL Checkpointer 方案。
4. 输出简短实施计划。
5. 增加必要 dependency。
6. 增加 checkpoint config。
7. 实现 PostgreSQL Checkpointer lifecycle。
8. 调整 Graph factory / dependency injection。
9. 保持 InMemory test path。
10. 保持 `thread_id` API 不变。
11. 验证 user isolation。
12. 增加 persistence integration tests。
13. 测试 Graph recreation 后恢复 conversation。
14. 审计 Run-level reset。
15. 审计 Full Content checkpoint size。
16. 做必要的大对象 State 最小清理。
17. 增加相关回归测试。
18. 跑所有 Agent tests。
19. 跑 Agent API tests。
20. 跑 Semantic Search / RAG / Fetch tests。
21. 跑 PostgreSQL checkpoint integration tests。
22. 跑完整 backend。
23. 跑 frontend production build。
24. `compileall`
25. `pip check`
26. `git diff --check`
27. 做 Stage 10 最终 Code Review。
28. 更新 README / architecture 状态。
29. 输出最终 V1 验收报告。
30. 停止开发。

---

# 四十四、完成后必须汇报

## 1. 修改 / 新增文件

逐一说明。

---

## 2. Checkpoint Architecture

例如：

```text
Frontend thread_id
        ↓
Agent API
        ↓
user_id + thread_id
        ↓
LangGraph
        ↓
PostgreSQL Checkpointer
```

---

## 3. Lifecycle

说明：

* pool / connection 在哪里建立
* 在哪里关闭
* graph 如何获得 checkpointer
* 是否应用级复用

---

## 4. Schema Setup

说明：

* checkpoint tables 如何创建
* 是否由官方 `setup()` 管理
* 是否使用 Alembic
* 原因

---

## 5. User Isolation

说明：

```text
same thread UUID
+
different user
```

为什么不会共享。

---

## 6. Persistence

说明测试结果：

```text
Graph A
→ write checkpoint

Graph B
→ same thread
→ recover history
```

---

## 7. Run Reset

确认：

* messages persist
* counters reset
* evidence reset
* error reset
* sources reset

---

## 8. Checkpoint Size

说明：

* full article/web content 是否进入 checkpoint
* 是否做了清理
* selected evidence 如何保留

---

## 9. Failure Behavior

说明：

Postgres unavailable 时：

```text
startup/API
```

如何安全失败。

---

## 10. Dependencies

列出新增 dependency 和版本。

---

## 11. Testing

必须明确：

```text
Agent tests: X passed
Agent API tests: X passed
Checkpoint integration: X passed
Semantic/RAG/Fetch: X passed
Full backend: X passed
Frontend build: passed
compileall: passed
pip check: passed
git diff --check: passed
```

---

## 12. Final E2E Scenarios

汇报：

```text
KB-only
Rewrite
Fresh/Web
Web Full-text
KB Full-text
Partial
Insufficient
Budget Exhaustion
Tool Error
Conversation Follow-up
Process Recreation
```

分别是否通过。

---

## 13. Final Code Review

列：

```text
Critical
Important
Minor
```

剩余问题。

---

## 14. V1 已实现能力

完整列出。

---

## 15. V1 未实现能力

至少：

```text
Long-term Memory
Conversation History UI
Streaming
save_to_knowledge_base
Multi-Agent
Reranker
```

---

# 四十五、最终验收标准

Task 8 只有同时满足以下要求才算完成：

* PostgreSQL Checkpointer 已接入正式 Runtime
* InMemorySaver 不再是 production 默认
* 测试仍可使用 InMemorySaver
* thread_id API 完全兼容 Task 7
* 同用户同 thread 可跨 Graph 实例恢复
* 不同 thread 隔离
* 不同用户同 UUID 隔离
* 服务重建后 conversation context 可恢复
* Run-level counters 不跨问题累计
* messages 正常跨轮次保留
* Runtime dependencies 不进入 checkpoint
* secrets 不进入 checkpoint
* checkpoint failure 安全处理
* 没有 silent fallback 到 InMemory
* Full Content checkpoint 膨胀风险已审计
* 如必要，正文大对象已做最小清理
* selected evidence / sources 不被旧 Run 污染
* Agent bounded loop 仍成立
* 所有 Agent API 行为不受破坏
* frontend Chat MVP 仍可正常运行
* Full backend regression 通过
* frontend production build 通过
* README / Architecture 状态与实现一致
* Stage 10 最终 Code Review 无阻断问题
* 没有提前实现 V1 之外增强功能
* 完成后停止开发

---

# 四十六、停止条件

完成上述全部内容后：

> 停止开发。

不要继续：

* Task 9
* Streaming
* Long-term Memory
* Multi-Agent
* Conversation Management
* save_to_knowledge_base

请把本次输出视为：

> **GistAI Stage 10 Agent V1 Final Development Report**
