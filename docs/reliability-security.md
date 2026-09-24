# Reliability & Security

GistAI 需要处理用户提供的 URL、外部网页、LLM、Embedding、Web Search 和数据库，因此可靠性与安全边界不仅存在于 API 层，也贯穿抓取、重处理、Agent Tool 和 Checkpoint。

---

## URL / SSRF Protection

所有外部网页抓取都经过 URL Safety Validation。

基础约束：

- 仅允许 `http` / `https`
- URL 不允许携带 username / password
- 拒绝 `localhost`
- 拒绝非 global IP
- 域名解析后的所有地址都需要通过检查

```text
URL
↓
Parse
↓
Resolve Host
↓
IP Safety Check
↓
Fetch
```

目标是防止用户通过 URL 让服务端访问本机、私网或内部基础设施。

---

## Redirect Validation

HTTP Fetch 不直接开启自动 Redirect。

每一跳 Redirect 都重新执行 URL 安全检查：

```text
Request
↓
3xx Location
↓
Resolve New URL
↓
Safety Validation
↓
Next Request
```

这样可以避免：

```text
public URL
→ redirect
→ private/internal address
```

绕过第一跳验证。

---

## Playwright Safety

Playwright 只作为 HTTP Fetch 失败后的浏览器 fallback。

浏览器模式继续执行安全控制：

- 导航前 URL Validation
- 请求 origin Validation
- 内部地址请求拦截
- WebSocket 关闭
- Service Worker 禁用
- final URL 再次验证
- Page / Context / Browser 生命周期释放

普通 HTTP 和 Browser Fallback 使用相同的 URL Safety 规则，避免安全边界因切换抓取方式而失效。

---

## Failure Protection

文章重处理不是“先删旧数据，再重新生成”。

系统优先保留已有有效结果：

```text
Existing Valid Data
↓
Prepare New Result
↓
All Required Steps Succeed
↓
Transaction / Atomic Replacement
↓
New Valid Data
```

如果 AI 或 Embedding 等步骤失败，旧的有效正文、标签、Chunk 或向量应尽可能继续保留。

这可以避免一次失败的重新处理把原本可用的数据破坏掉。

---

## Processing Status

文章处理维护独立阶段状态，例如：

```text
fetch_status
ai_status
embedding_status
```

这样可以区分抓取失败、AI 失败、Embedding 失败、部分失败和完整成功。

恢复操作可以针对具体失败阶段执行，而不是每次都从头重复整个 Pipeline。

---

## Content Hash

正文清洗后生成 `content_hash`。

重新抓取时，如果内容没有变化，可以避免无意义地重复执行 AI 和 Embedding。

```text
new content
↓
SHA256
↓
compare old hash
↓
unchanged → reuse valid downstream data
```

这既降低外部 API 消耗，也减少重复数据变化。

---

## Concurrency Guard

当 Article 正处于 processing 状态时，重新处理类操作不会允许无条件并发进入。

目标是避免同一资源同时发生多个互相覆盖的更新任务。

---

## User Isolation

业务查询都需要结合当前用户身份。

例如 Article / Search 等数据访问不会只依据裸 `article_id`，而是同时考虑 user boundary。

Agent Chat 的公开 `thread_id` 也不会直接成为跨用户共享的会话身份。

这样可以避免不同用户之间共享 Article、Search Result 或 Conversation State。

---

## Safe Error Mapping

外部 Provider、数据库和运行时异常不会原样返回给客户端。

API 输出不会直接暴露：

- raw provider response
- stack trace
- database exception detail
- Authorization Header
- API Key
- connection string
- internal network detail

外部异常会被映射为稳定的业务错误。

---

## Structured Output Validation

模型输出不作为可信输入直接使用。

```text
LLM Output
↓
Structured Output / JSON Schema
↓
Pydantic Validation
↓
Runtime Business Validation
↓
Application State
```

静态 Schema 只能保证数据结构。

像“Evidence Index 是否存在”“Action 当前是否允许”这类依赖运行状态的规则，还需要程序在 Runtime 再次校验。

---

## Agent Runtime Policy

Agent 的能力由 Runtime Policy 约束。

默认预算：

```text
max_kb_searches    = 2
max_rewrites       = 1
max_web_searches   = 1
max_article_reads  = 2
max_web_page_reads = 2
max_steps          = 8
```

Policy 的作用不是帮助模型推理，而是限制模型可以造成的行为。

```text
State
↓
Runtime Policy
↓
Allowed Actions
↓
LLM Decision
↓
Program Validation
↓
Tool Execution
```

---

## Tool Error vs Empty Result

系统区分：

```text
Tool executed successfully but returned no result
```

和：

```text
Tool execution failed
```

前者通常仍然允许 Agent 选择其他检索路径；后者可能触发错误终止策略。

这种分类避免“没有搜到东西”和“系统坏了”被当成同一种状态。

---

## Bounded Loop

Agent 具备 Local Tool Budget 和 Global Step Limit。

因此即使 Decision Model 持续要求 Search / Rewrite / Full-text，也无法无限循环。

达到边界后：

- 有可靠 Evidence → Partial / Answer
- 无可靠 Evidence → Insufficient

---

## Checkpoint Safety

生产环境使用 PostgreSQL Checkpoint。

Checkpoint 的设计边界包括：

- Runtime Service 不进入 State
- DB Session 不作为持久化对象
- API Key 不写入 Agent State
- Authorization Header 不写入 Agent State
- 大块 Article / Web raw content 不长期持久化
- Serializer 允许类型采用明确 allowlist

连接池日志还会避免直接输出潜在连接信息。

---

## Secret Management

仓库只应提交可公开的配置模板，例如 `.env.example`。

以下内容不应进入 Git：

```text
.env
real API keys
access tokens
private credentials
production database passwords
private connection strings
```

任何已经暴露过的真实 Secret 都应该视为已泄露并进行 rotate，而不是只从最新提交中删除。
