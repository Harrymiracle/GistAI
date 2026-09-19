你现在在 GistAI 项目中开发前端 Chat MVP。

当前本地分支：`dev`。

本次任务范围必须严格控制，只完成 **Agent Chat API 请求层与 API 类型定义**，不要开发 Chat 页面，不要创建 Store，不要创建 Service 层，不要修改后端代码。

项目当前前端技术栈：

* React
* TypeScript
* Vite
* axios
* TanStack Query
* React Router

当前后端已经存在真实接口：

`POST /api/v1/agent/chat`

请求：

```json
{
  "message": "用户问题",
  "thread_id": "可选 UUID，第一次聊天可以不传"
}
```

其中：

* `message`：必填字符串，后端限制 1～4000 字符
* `thread_id`：可选 UUID；第一次不传时由后端生成

成功响应统一结构：

```json
{
  "code": 20000,
  "message": "Agent 回答成功",
  "data": {
    "thread_id": "uuid",
    "answer": "回答内容",
    "status": "answer",
    "sources": []
  }
}
```

`status` 可能是：

```text
answer
partial
insufficient
error
```

`source` 结构：

```json
{
  "source_type": "knowledge_base | web",
  "title": "来源标题",
  "article_id": 1,
  "chunk_id": 2,
  "url": "https://...",
  "source": "来源名称",
  "published_at": "..."
}
```

其中：

* knowledge_base 来源主要使用 `article_id` / `chunk_id`
* web 来源主要使用 `url` / `source` / `published_at`
* 非对应字段可能为 null

失败响应仍然是统一结构：

```json
{
  "code": 50002,
  "message": "Agent 暂时无法完成请求，请稍后重试",
  "data": null
}
```

## 本次需要完成的文件结构

```text
apps/web/src/
├─ api/
│  ├─ client.ts
│  └─ agent.ts
│
└─ types/
   ├─ api.ts
   └─ agent.ts
```

### 1. `types/api.ts`

定义可复用的泛型 API Response 类型：

```text
ApiResponse<T>
```

至少包含：

```text
code
message
data
```

不要加入当前后端不存在的字段。

### 2. `types/agent.ts`

根据真实后端契约定义：

```text
AgentResponseStatus
AgentChatRequest
AgentSource
AgentChatData
```

要求：

* 与当前 FastAPI/Pydantic 契约严格一致
* 正确处理 nullable / optional 字段
* 不要在这里定义前端 `ChatMessage`
* 不要混入 UI 状态

### 3. `api/client.ts`

创建一个项目统一使用的 axios instance。

要求：

* 保持简单
* 可以配置合适的基础 timeout
* 不要提前实现复杂 token / auth / refresh token 逻辑
* 不要加入当前项目没有需求的 interceptor 体系
* 保证现有 Vite dev proxy / 当前接口调用方式可以继续工作
* 不要破坏现有 `/health` 请求

### 4. `api/agent.ts`

封装 Agent Chat API。

提供一个语义清晰的函数，例如：

```text
sendAgentMessage(...)
```

调用：

```text
POST /api/v1/agent/chat
```

输入使用 `AgentChatRequest`。

返回类型应能够让上层直接得到真实的 Agent API 数据，同时保持与统一 `ApiResponse<T>` 契约一致。

不要在这里：

* 管理 thread_id
* 管理 messages
* 管理 loading
* 管理页面状态
* 转换为 ChatMessage

这些会在后面的 `useAgentChat` 中实现。

## 架构约束

当前采用渐进式前端结构：

```text
ChatPage
→ useAgentChat
→ api/agent.ts
→ api/client.ts
→ FastAPI
```

现在不要提前增加：

```text
services/
stores/
entities/
models/
repositories/
```

但代码需要保持边界清晰，方便未来需要时再扩展。

## 修改范围

尽量只新增/修改本任务直接相关文件。

不要：

* 开发 UI
* 改 App.tsx 页面
* 安装新的状态管理库
* 引入 Zustand / Redux
* 修改后端
* 实现 Streaming
* 实现历史会话
* 实现 Article 页面
* 大规模重构现有前端

## 验收

完成后请：

1. 运行 TypeScript / 前端 build 检查。
2. 确认没有新增 TypeScript 错误。
3. 给出：

   * 新增/修改文件列表
   * 每个文件职责
   * 核心类型定义
   * Agent API 调用方式
   * 执行的验证命令和结果
4. 不要继续开发下一阶段。
