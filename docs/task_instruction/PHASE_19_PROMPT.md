你现在要继续在现有 **GistAI / AI 阅读助手** 项目中完成 Stage 10 Agent V1 的第七批开发任务。

Phase 18 / Task 6 已完成。

当前 Agent 后端已经具备：

* LangGraph Agent
* Conversation-level / Run-level State
* Runtime Context
* Knowledge Search
* Query Rewrite
* Web Search
* KB Article Full-text Read
* Web Page Full-text Fetch
* Evidence Evaluation
* Structured Decision
* Runtime Policy
* `allowed_actions`
* Tool Budget
* Global `MAX_STEPS`
* Error Classification
* Safe Termination
* Partial / Insufficient
* InMemory checkpoint
* 自动化测试

当前完整后端测试基线：

```text
295 passed
```

本次目标：

> **Task 7：为现有 Agent 增加正式 HTTP API，并实现第一版可实际使用和演示的前端 Agent Chat MVP。**

---

# 一、任务目标

本次需要完成两部分。

## A. 后端 Agent API

让前端可以通过稳定 API 调用现有 Agent Graph：

```text
Frontend
→ Agent API
→ LangGraph Agent
→ Knowledge / Web / Full-text Tools
→ final answer
→ sources
→ frontend
```

## B. 前端 Chat MVP

新增一个最小、可用、可展示的 Agent 页面。

用户可以：

```text
输入问题
→ 提交
→ 等待 Agent
→ 查看回答
→ 查看 Sources
→ 继续追问
```

同一聊天中复用：

```text
thread_id
```

从而保持 conversation context。

---

# 二、本次严格范围

本 Task 只做：

* Agent API
* Frontend Agent Chat MVP
* thread_id 会话延续
* Answer 展示
* Sources 展示
* 基础 Loading / Error / Partial / Insufficient 状态
* 基础测试

不要实现：

* PostgreSQL checkpoint
* 长期 Memory
* 登录系统重构
* Agent History 数据库
* 会话列表持久化
* 多会话管理中心
* 多 Agent
* Planner
* Reflection
* Streaming Token
* SSE Streaming
* WebSocket Streaming
* `save_to_knowledge_base`
* 自动保存 Web 页面
* Tool execution timeline 大型 UI
* Debug Console
* Admin Agent Dashboard
* 富文本编辑器
* Markdown 编辑器
* Voice
* 文件上传问答
* 前端复杂状态管理框架重构

完成后停止，不进入 Task 8。

---

# 三、产品目标

第一版页面重点不是视觉复杂度，而是：

> **能用、能展示、能解释。**

理想演示流程：

```text
1. 用户进入 Agent 页面
2. 输入：“我保存的文章里 Agent Memory 是怎么说的？”
3. Agent 只查知识库
4. 页面显示回答 + KB Sources
5. 用户继续追问
6. 同一个 thread_id 保留上下文
7. 用户问：“最近这方面有什么新变化？”
8. Agent 可以按现有规则使用 Web Search
9. 页面显示 Web Sources
```

这就是本次 MVP 的核心价值。

---

# 四、先审计现有 API / 前端结构

开发前先阅读：

## Backend

* `/api/v1` Router 结构
* FastAPI dependency injection
* auth / current_user dependency
* Agent dependency assembly
* `agent_graph`
* `AgentContext`
* Article / Search API 风格
* Pydantic Response Schema 风格
* Error handling 风格

## Frontend

* React Router
* TanStack Query
* axios client
* API 封装
* 页面 layout
* shadcn/ui
* Tailwind
* 现有 Article / Search 页面
* Loading / Empty / Error UI 风格

优先保持项目现有模式。

不要为 Agent 单独搭第二套网络层或状态架构。

---

# 五、后端 API 路径

建议新增：

```text
POST /api/v1/agent/chat
```

如果项目现有路由命名规范更合适，可以调整。

不要创建 `/v2`，除非现有项目已经明确采用。

---

# 六、Agent Chat Request

定义严格 Schema。

概念上：

```python
class AgentChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
```

要求：

* `message` 必填
* trim 后不能为空
* 有合理最大长度
* `thread_id` 可选
* 禁止未声明字段（按现有项目 Schema 风格）

第一轮：

```text
thread_id = None
```

后端生成新 thread id。

后续：

```text
thread_id = 前一轮返回值
```

继续同一 conversation。

---

# 七、thread_id 生成与边界

后端负责生成：

```text
UUID
```

不要由前端随便生成不受控格式，除非项目已有约定。

前端只负责：

```text
保存后端返回的 thread_id
→ 后续请求继续带上
```

必须保证：

> thread_id 是 conversation id，不是 user id。

---

# 八、用户隔离

当前 Agent 会访问：

* 用户知识库
* Article content

因此 API 必须继续依赖：

```text
current_user
```

或项目当前用户上下文。

AgentContext 中：

```text
current_user_id
```

必须来自服务端认证 / dependency。

不要允许前端 Request 直接传：

```text
user_id
```

避免越权。

---

# 九、Graph 调用

Agent API 应：

```text
构造 AgentContext
↓
准备 graph config
↓
thread_id
↓
graph.invoke / ainvoke
```

优先根据当前 FastAPI / LangGraph 实现选择：

```text
async
```

如果现有所有 service / graph 调用主要同步，也不要为了形式强行重构大量代码。

但不要在 async endpoint 中无意识阻塞 event loop。

请根据当前代码做合理实现并说明。

---

# 十、Graph Input

API 输入应只提供最小必要数据，例如：

```text
messages = [
  user message
]
```

不要让客户端传：

* `allowed_actions`
* `step_count`
* `kb_results`
* `web_results`
* `evidence`
* `next_action`
* Tool counts

这些都是服务端 Agent Runtime State。

---

# 十一、Agent Chat Response

不要把整个：

```text
AgentState
```

原样返回给前端。

定义独立 API Response Schema。

至少：

```text
thread_id
answer
status
sources
```

建议：

```python
class AgentChatResponse(BaseModel):
    thread_id: str
    answer: str
    status: AgentResponseStatus
    sources: list[AgentSourceResponse]
```

---

# 十二、Response Status

前端需要知道回答属于什么类型。

建议提供类似：

```text
answer
partial
insufficient
error
```

具体 Enum 名称按项目风格。

映射原则：

* 正常完整回答 → `answer`
* Partial Answer → `partial`
* Insufficient → `insufficient`
* 安全失败 → `error`

不要让前端从回答文案中猜状态。

---

# 十三、Source API Schema

统一前端友好的 Source Schema。

需要同时兼容：

## KB Source

当前已有：

```text
article_id
chunk_id?
title
```

## Web Source

当前已有：

```text
title
url
source
published_at
```

建议统一 API 输出，例如：

```text
source_type
title
article_id?
chunk_id?
url?
source?
published_at?
```

不要让前端依赖 Agent 内部 Evidence Schema。

---

# 十四、Source 数据安全

只返回前端实际需要的信息。

不要返回：

* clean_content 全文
* temporary chunks
* similarity internal debug data
* Provider raw response
* Prompt
* reasoning
* allowed_actions
* ToolExecutionResult internal details
* API key
* stack trace

---

# 十五、错误处理

API 层至少区分：

## Request Validation

例如：

```text
message empty
invalid thread_id
message too long
```

正常 FastAPI/Pydantic validation。

## Agent Safe Failure

Graph 正常结束，但状态：

```text
error / insufficient
```

仍然可以返回业务 Response。

## Unexpected Internal Error

捕获并使用项目统一 API error pattern。

不要暴露：

```text
raw exception / stack trace / provider response
```

---

# 十六、是否返回 HTTP 200

建议：

对于 Agent 正常运行后得出的：

```text
partial
insufficient
```

仍返回：

```text
HTTP 200
```

因为这是有效业务结果，不是服务器错误。

真正：

```text
unexpected internal failure
```

才进入对应 HTTP error。

请按项目现有错误规范实现。

---

# 十七、InMemory Checkpoint 当前限制

Task 7 暂时继续使用：

```text
InMemorySaver
```

所以必须接受一个已知限制：

> Server 重启后 thread context 丢失。

不要在 Task 7 提前做 PostgreSQL checkpoint。

但 API contract 必须从现在就正式使用：

```text
thread_id
```

这样 Task 8 换持久化 Checkpointer 时：

> 前端 API 无需变化。

---

# 十八、前端路由

新增一个 Agent 页面。

例如：

```text
/agent
```

或：

```text
/chat
```

优先根据现有 Router 风格选择。

页面名称建议用户可理解：

```text
AI 助手
知识助手
Agent Chat
```

不要过度营销式命名。

---

# 十九、Chat MVP 布局

第一版保持简单。

建议：

```text
┌────────────────────────────┐
│ AI Knowledge Assistant     │
│ KB + Web grounded answer   │
├────────────────────────────┤
│                            │
│ User message               │
│                            │
│ Assistant answer           │
│ Sources                    │
│                            │
│ User follow-up             │
│                            │
├────────────────────────────┤
│ Ask something...   [Send]  │
└────────────────────────────┘
```

---

# 二十、消息 UI

至少支持：

```text
User
Assistant
```

两种 Message Bubble / Block。

不要做：

* Avatar upload
* Message reaction
* Edit message
* Branch conversation
* Regenerate
* Copy entire ChatGPT feature set

本 Task 只做最基本聊天体验。

---

# 二十一、前端 State

至少维护：

```text
messages
threadId
input
isSubmitting
error
```

可以使用：

* React local state
* TanStack mutation

不要为了一个页面引入新的大型全局状态库。

---

# 二十二、API Client

复用当前：

```text
axios
```

封装。

例如：

```text
agentApi.chat(...)
```

不要：

```text
fetch()
```

直接散落在组件中，如果项目已经统一用 axios。

---

# 二十三、TanStack Query

Agent Chat 更适合：

```text
useMutation
```

而不是 Query。

每次用户提交：

```text
mutation
```

成功后将：

```text
assistant response
```

append 到本地 messages。

不要滥用 cache 模型保存聊天历史。

---

# 二十四、thread_id 前端生命周期

第一条消息：

```text
threadId = null
```

请求成功：

```text
threadId = response.thread_id
```

以后继续用。

页面刷新后：

Task 7 第一版允许：

> threadId 丢失，开始新对话。

不要提前做：

* localStorage conversation restore
* server conversation history API
* database conversation list

Task 8 / 后续再处理持久化。

---

# 二十五、新对话按钮

建议增加：

```text
New Chat / 新对话
```

行为：

```text
threadId = null
messages = []
error = null
```

这只是前端 reset。

不需要调用后端删除 checkpoint。

---

# 二十六、发送行为

要求：

* trim empty 禁止发送
* loading 时避免重复提交
* Enter 发送
* Shift+Enter 换行（如果 textarea）
* 提交后清空 input
* 请求失败时保留合理恢复能力

---

# 二十七、Loading

Agent 当前可能：

* Search KB
* Rewrite
* Web Search
* Fetch page
* Read article

所以延迟可能比普通 CRUD 高。

第一版至少展示：

```text
正在思考 / 正在查找资料...
```

不要假装提供精确实时 Tool 状态，因为当前 API 不是 streaming。

不要写：

```text
正在 Web Search
```

除非后端真的把实时状态传出来。

---

# 二十八、Answer Rendering

如果项目已经支持 Markdown Renderer：

可以复用。

如果没有：

第一版可以安全显示纯文本。

不要为了本 Task 引入复杂 Markdown 编辑生态。

必须防止：

> 直接使用危险 `dangerouslySetInnerHTML` 渲染不可信模型内容。

---

# 二十九、Partial UI

如果：

```text
status = partial
```

前端应有轻量提示，例如：

```text
部分信息有依据，但现有证据不足以覆盖全部问题。
```

不要把它做成严重错误红屏。

---

# 三十、Insufficient UI

如果：

```text
status = insufficient
```

显示：

```text
当前知识库和允许使用的外部资料中，没有找到足够证据。
```

同时仍保留这条 Assistant Message。

---

# 三十一、Error UI

如果：

```text
status = error
```

或请求失败：

显示安全、用户可理解错误。

不要展示：

```text
TimeoutError(...)
SQLAlchemy...
stack trace
```

---

# 三十二、Sources UI

每条 Assistant Answer 下方增加：

```text
Sources
```

最好默认紧凑展示。

## KB Source

显示：

```text
文章标题
```

如果当前已有文章详情路由，可链接到：

```text
/article/:id
```

或项目现有路径。

如果没有稳定路由，不要硬造。

## Web Source

显示：

```text
title
source/domain
published_at（有则显示）
```

点击：

```text
url
```

新标签页打开：

```text
target="_blank"
rel="noopener noreferrer"
```

---

# 三十三、Source 不要伪造

前端完全使用 API 返回 Sources。

不要前端自行从回答文本：

```text
正则提 URL
```

不要猜来源。

---

# 三十四、Conversation 展示

前端本地 Message Model 建议类似：

```text
id
role
content
status?
sources?
```

不要直接把 LangChain Message 对象暴露到前端。

---

# 三十五、避免发送完整历史

当前后端 checkpoint 已按：

```text
thread_id
```

维护 conversation messages。

因此前端每次请求只需要发送：

```text
当前新 message
+
thread_id
```

不要每次重新上传整个历史：

```text
messages[]
```

否则会：

* 重复消息
* 增大请求
* 与 checkpoint 产生冲突

---

# 三十六、并发提交

第一版一个 thread 同时只允许一个请求。

前端：

```text
isSubmitting
```

时禁止再次 Send。

后端如果容易实现，也可以做轻量防御。

不要为本 Task 做复杂分布式锁。

---

# 三十七、API Timeout

Agent 请求可能明显长于普通 API。

检查当前 axios / backend timeout。

不要因为默认 5s / 10s 导致正常 Agent 被误杀。

根据当前最坏路径设置合理 Agent endpoint timeout 或 client timeout。

不要设置无限 timeout。

完成报告中说明实际值。

---

# 三十八、CORS / API 配置

复用现有项目 API base URL。

不要新增硬编码：

```text
localhost:8000
```

到页面组件。

继续使用现有环境配置。

---

# 三十九、测试：后端

至少覆盖：

## Test 1：首次 Chat

无 `thread_id`：

```text
POST /agent/chat
```

验证：

* 生成 thread_id
* 返回 answer
* 返回 sources
* status 正确

---

## Test 2：Follow-up

第一次拿到：

```text
thread_id=A
```

第二次使用：

```text
thread_id=A
```

验证 Graph 用同一 conversation checkpoint。

---

## Test 3：Different Thread

不同 thread 不共享 messages。

---

## Test 4：Current User

确保 AgentContext：

```text
user_id
```

来自当前认证用户，而不是 request body。

---

## Test 5：Partial

Graph 返回 partial。

API 映射：

```text
status=partial
```

---

## Test 6：Insufficient

API 正确映射。

---

## Test 7：Safe Error

Graph safe failure 不泄露内部错误。

---

## Test 8：Validation

空 message / 超长 message / invalid thread_id。

---

## Test 9：Source Mapping

分别测试：

```text
KB source
Web source
```

到 API response。

---

# 四十、测试：前端

根据当前项目测试体系选择。

如果已有：

* Vitest
* React Testing Library

则至少增加：

## Test 1

输入问题并提交。

验证调用 Agent API。

## Test 2

第一次返回 thread_id。

下一轮请求继续带相同 thread_id。

## Test 3

显示 Assistant Answer。

## Test 4

显示 KB / Web Sources。

## Test 5

Partial / Insufficient 状态展示。

## Test 6

请求失败 UI。

## Test 7

Loading 时防止重复发送。

## Test 8

New Chat 重置 messages 和 threadId。

如果项目当前没有成熟前端测试体系：

> 不要为 Task 7 大规模引入新的测试框架。

至少完成 production build，并在报告中说明。

---

# 四十一、API Contract 测试优先

本 Task 最重要的是：

> Backend Response Schema 与 Frontend Type 完全对齐。

不要出现：

```text
backend: final_answer
frontend: answerText
```

靠猜测映射。

请明确建立：

```text
AgentChatRequest
AgentChatResponse
AgentSource
AgentResponseStatus
```

对应 TypeScript 类型。

---

# 四十二、UI 风格

继续使用项目现有：

* shadcn/ui
* Tailwind
* Layout
* Button
* Card
* Textarea
* Scroll area（如已有）

不要引入另一个 UI Library。

视觉重点：

* 清晰
* 干净
* Sources 易看
* Answer 易读
* 不像后台调试页

---

# 四十三、不要展示内部 Agent 术语

普通用户 UI 不要直接展示：

```text
AgentAction.WEB_SEARCH
step_count=7
MAX_STEPS
EvidenceStatus.PARTIAL
tool_call_counts
```

这些属于内部实现。

用户只需要看到：

```text
回答
部分回答
证据不足
Sources
```

---

# 四十四、可演示性

完成后手动验证至少三种场景。

## Demo A：知识库回答

问题只根据自己的保存内容即可回答。

验证：

```text
KB Answer
+
KB Sources
```

## Demo B：最新信息

问一个需要 current / latest 的问题。

验证：

```text
Web source
```

能正常出现。

## Demo C：证据不足

问一个知识库和 Web 都无足够依据的问题。

验证：

```text
Insufficient
```

而不是模型幻觉。

真实外部 API 如果当前环境没有配置，可以使用可控测试 / mock 完成自动化验收，并在报告中说明实际手动验证状态。

---

# 四十五、README / 文档

Task 7 可以最小更新 README：

说明：

```text
Agent endpoint
Agent page route
thread_id behavior
InMemory checkpoint limitation
```

不要在本次写大型项目文档。

---

# 四十六、代码结构建议

后端可以类似：

```text
app/
├─ agent/
│  └─ ...
├─ api/
│  ├─ routes/
│  │  └─ agent.py
│  └─ deps.py
└─ schemas/
```

实际按当前项目组织。

前端例如：

```text
src/
├─ api/
│  └─ agent.ts
├─ pages/
│  └─ AgentChatPage.tsx
└─ components/
   └─ agent/
```

不要为了一个页面拆十几个文件。

---

# 四十七、不要破坏原 RAG API

如果项目已有普通：

```text
RAG Query
Semantic Search
```

API：

继续保留。

不要为了 Agent 页面删除或重写旧 API。

Agent 是新增入口。

---

# 四十八、回归验证

至少运行：

```text
Agent backend tests
Agent API tests
Semantic Search tests
RAG tests
Fetch / Extraction tests
Full backend tests
```

前端：

```text
existing frontend tests（如有）
production build
```

以及：

```text
Python compileall
pip check
git diff --check
```

---

# 四十九、开发顺序

请按以下顺序：

1. 阅读当前 API Router / dependency / auth 结构。
2. 阅读当前 frontend router / API / query 架构。
3. 给出简短实施计划。
4. 定义 Agent Chat API Request / Response Schema。
5. 实现 Agent API dependency / graph invocation。
6. 增加 Agent API tests。
7. 增加 frontend Agent API client/types。
8. 增加 Agent Chat route/page。
9. 实现 local conversation state。
10. 实现发送 / loading / error。
11. 实现 Answer UI。
12. 实现 Sources UI。
13. 实现 Partial / Insufficient UI。
14. 实现 New Chat。
15. 检查 timeout / concurrency。
16. 如已有测试体系，增加前端 tests。
17. 手动验证核心 demo flow。
18. 跑后端定向测试。
19. 跑完整后端回归。
20. 跑前端 production build。
21. `compileall`
22. `pip check`
23. `git diff --check`
24. 做一次代码 review。
25. 输出完整总结。
26. 停止。

---

# 五十、完成后必须汇报

## 1. 修改 / 新增文件

后端和前端分别列出。

---

## 2. API Contract

明确：

```text
POST /...
Request
Response
```

完整字段。

---

## 3. thread_id

说明：

* 谁生成
* 前端怎么保存
* follow-up 怎么继续
* server restart 后当前限制

---

## 4. User Isolation

说明：

```text
current_user_id
```

从哪里来，以及为什么不能前端传。

---

## 5. Agent 调用链

例如：

```text
Frontend
→ FastAPI
→ AgentContext
→ graph.invoke
→ AgentState
→ API Response
```

---

## 6. Response Mapping

说明：

```text
Answer
Partial
Insufficient
Error
```

如何映射成 API Status。

---

## 7. Sources

说明：

KB / Web Sources 如何统一给前端。

---

## 8. Frontend

说明：

* route
* page structure
* state
* useMutation
* threadId
* New Chat
* Sources
* loading / error

---

## 9. Timeout

说明最终 client / server timeout 策略。

---

## 10. 测试

明确：

```text
Agent API tests: X passed
Agent backend tests: X passed
Full backend: X passed
Frontend tests: X passed / not configured
Frontend build: passed
compileall: passed
pip check: passed
git diff --check: passed
```

---

## 11. Demo 验证

分别说明：

```text
KB-only
Fresh/Web
Insufficient
```

三个演示场景的结果。

---

## 12. Code Review

说明：

```text
Critical
Important
Minor
```

是否存在问题。

---

## 13. 明确未实现

至少：

```text
PostgreSQL checkpoint
Long-term Memory
Conversation persistence
Streaming
save_to_knowledge_base
Multi-Agent
Task 8+
```

---

# 五十一、验收标准

Task 7 只有同时满足以下要求才算完成：

* 有正式 Agent Chat HTTP API
* API 不暴露完整 AgentState
* Request 只接受 message + thread_id 等必要字段
* user_id 不允许客户端传入
* thread_id 可以延续同一 conversation
* 首次调用能创建 thread_id
* Answer / Partial / Insufficient / Error 有明确 API status
* KB / Web Sources 有统一前端 Schema
* 前端有独立 Agent Chat 页面
* 用户可以输入问题并获得真实 Agent 回答
* 用户可以继续追问
* 前端复用同一个 thread_id
* New Chat 可以重置本地会话
* 页面能显示 Sources
* Partial / Insufficient 有清晰 UI
* Loading 状态合理
* 重复提交受到限制
* 不展示内部 Agent Runtime 字段
* InMemory checkpoint 限制被明确保留
* 原有 RAG / Search API 未被破坏
* 后端自动测试通过
* 前端 production build 通过
* 代码 review 无阻断问题
* 没有提前实现 Task 8
* 完成后停止开发

完成以上内容后，请停止，不要继续 PostgreSQL checkpoint、长期 Memory、会话持久化、Streaming 或知识库写入。
