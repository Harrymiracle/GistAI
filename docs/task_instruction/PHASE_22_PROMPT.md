你现在在 GistAI 项目中继续开发前端 Chat MVP。

当前本地分支：`dev`。

上一阶段 Phase 21 已完成：

* `apps/web/src/types/api.ts`
* `apps/web/src/types/agent.ts`
* `apps/web/src/api/client.ts`
* `apps/web/src/api/agent.ts`

当前已经存在：

```text
sendAgentMessage(payload)
→ POST /api/v1/agent/chat
→ 返回 AgentChatData
```

`AgentChatData` 结构：

```ts
{
  thread_id: string
  answer: string
  status: 'answer' | 'partial' | 'insufficient' | 'error'
  sources: AgentSource[]
}
```

本阶段只完成：

> **Chat UI Model + useAgentChat Hook**

不要开发页面 UI，不要安装新状态管理库，不要修改后端。

---

## 一、本阶段新增文件

```text
apps/web/src/
├─ types/
│  └─ chat.ts
└─ hooks/
   └─ useAgentChat.ts
```

如目录不存在可创建。

---

## 二、`types/chat.ts`

定义前端聊天页面自己的 UI Model。

推荐结构：

```ts
type ChatRole = 'user' | 'assistant'

interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  status?: AgentResponseStatus
  sources?: AgentSource[]
}
```

要求：

* `AgentResponseStatus` 和 `AgentSource` 必须复用已有 `types/agent.ts`
* 不重复定义后端 DTO
* `status` / `sources` 主要给 assistant message 使用，但第一版可以保持 optional
* 不要加入当前 MVP 不需要的字段

本阶段不要加入：

```text
createdAt
retryCount
toolCalls
conversationTitle
metadata
```

---

## 三、`useAgentChat.ts`

实现一个专门负责 Chat 会话状态和发送逻辑的 Hook。

Hook 第一版至少负责：

```text
messages
threadId
sendMessage
isPending
error
```

### 1. messages

使用：

```ts
ChatMessage[]
```

初始为空数组。

---

### 2. threadId

类型：

```ts
string | null
```

初始为 `null`。

第一次发送消息时，不要求主动生成 UUID。

后端会在第一次 Agent Chat 后返回真实 `thread_id`。

收到成功响应以后：

```text
保存 response.thread_id
```

以后继续发送消息时，将该 `threadId` 作为请求参数传给后端。

---

### 3. sendMessage

提供类似：

```ts
sendMessage(message: string)
```

的调用方式。

需要处理以下流程：

```text
sendMessage(message)
↓
校验/清理输入
↓
立即追加 user message
↓
调用 sendAgentMessage({
  message,
  thread_id: 当前 threadId
})
↓
成功
├─ 保存后端返回 thread_id
├─ 创建 assistant ChatMessage
└─ 追加到 messages
```

第一版要求：

* 对输入执行 `trim`
* trim 后为空字符串时不要发送
* user message 立即进入 messages
* assistant message 使用后端：

  * `answer`
  * `status`
  * `sources`
* 每条前端 Message 需要稳定且唯一的 `id`

可使用浏览器原生能力生成 ID，例如：

```ts
crypto.randomUUID()
```

如果考虑兼容性需要简单 fallback，可以做轻量处理，但不要引入第三方 ID 库。

---

## 四、TanStack Query

项目已安装：

```text
@tanstack/react-query
```

本阶段优先使用：

```text
useMutation
```

来管理 Agent Chat 请求。

不要额外创建：

```text
const [isLoading, setIsLoading]
```

优先直接复用 mutation 提供的请求状态，例如：

```text
isPending
```

Hook 对外可以暴露：

```text
isPending
```

---

## 五、Error 处理

需要区分两种情况。

### 情况 A：HTTP / 网络 / API 请求直接失败

例如：

* timeout
* HTTP 500
* 网络失败
* Axios reject

这种情况：

```text
设置/暴露 error
```

不要把它伪装成一个成功的 assistant message。

同时：

* 已发送的 user message保留在 messages 中
* 不删除用户问题

---

### 情况 B：HTTP 请求成功，但后端返回：

```ts
status: 'error'
```

这仍然属于一次成功返回的 `AgentChatData`。

应该：

```text
创建 assistant message
status = 'error'
content = response.answer
```

不要把它当成 Axios 请求异常。

---

## 六、错误文案

如果 Axios 错误中存在后端统一响应：

```json
{
  "code": 50002,
  "message": "Agent 暂时无法完成请求，请稍后重试",
  "data": null
}
```

尽量优先使用后端 `message` 作为用户可展示错误。

如果无法获得安全后端 message，再 fallback 为简洁通用错误，例如：

```text
请求失败，请稍后重试
```

不要把原始异常堆栈、敏感信息直接暴露给 UI。

---

## 七、Concurrency / 重复发送

第一版保持简单。

当 mutation 正在 pending 时：

* `sendMessage` 不应重复发起新的 Agent 请求
* 可以直接忽略新的发送调用

不用实现：

* 请求队列
* 并发多消息
* Abort
* Cancel
* 乐观回滚

这些后续再加。

---

## 八、当前不要做的内容

本阶段严格不要：

* 修改 `App.tsx`
* 创建 `ChatPage`
* 创建聊天组件
* 创建 Store
* 引入 Zustand / Redux
* 创建 Service 层
* localStorage 持久化 threadId
* 历史会话
* 新建会话按钮
* Streaming
* SSE
* WebSocket
* Retry UI
* Source 点击逻辑
* Article 页面
* Tool Trace
* Agent Steps 展示
* 修改后端 API

---

## 九、架构边界

保持：

```text
ChatPage              # 下一阶段
↓
useAgentChat
↓
sendAgentMessage
↓
apiClient
↓
FastAPI
```

其中：

### `types/agent.ts`

表示：

```text
后端 API DTO
```

### `types/chat.ts`

表示：

```text
前端 Chat UI Model
```

两者不要混淆。

### `useAgentChat`

负责：

```text
聊天业务状态和 API 调用编排
```

但不负责页面展示。

---

## 十、验证要求

完成后至少执行：

```text
TypeScript 编译
前端 build
git diff --check
```

如果仓库已有适合当前 Hook 的测试基础，可以补充少量测试；如果当前前端还没有测试体系，不要为了 Phase 22 临时引入整套测试框架。

---

## 十一、完成后汇报

请给出：

1. 新增 / 修改文件列表
2. `ChatMessage` 最终结构
3. `useAgentChat` 暴露了哪些值和方法
4. 第一次请求和第二次请求的 threadId 流程
5. HTTP Error 和 `status='error'` 的处理区别
6. 执行的验证命令
7. 验证结果
8. 是否发现现有前端结构存在阻塞问题

完成后停止。

不要继续开发 Chat 页面或 Phase 23。
