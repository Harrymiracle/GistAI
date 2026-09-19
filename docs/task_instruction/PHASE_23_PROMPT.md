你现在在 GistAI 项目中继续开发前端 Chat MVP。

当前分支：`dev`。

本阶段为：

# Phase 23 — Agent Chat 页面收口 + Tailwind / shadcn UI 基础

目标：

> 在不扩展产品范围的前提下，把现有 `/agent` Chat 页面改造成真正使用 Phase 22 `useAgentChat` 的 MVP 页面，并建立 Tailwind CSS + shadcn/ui 的前端 UI 基础。

重点是：

```text
先把核心聊天主链跑通
+
形成后续可继续迭代的 UI 基础
```

不要扩展历史会话、Streaming、Store 等功能。

---

# 一、先检查当前真实代码

当前仓库已经存在：

```text
apps/web/src/pages/AgentChatPage.tsx
apps/web/src/styles.css
apps/web/src/App.tsx
apps/web/src/hooks/useAgentChat.ts
apps/web/src/types/chat.ts
apps/web/src/api/*
```

注意：

现有 `AgentChatPage.tsx` 是旧实现，目前自己重复维护了：

```text
messages
threadId
useMutation
Agent API 调用
error
```

Phase 22 已经新增：

```text
useAgentChat()
```

它已经统一负责：

```text
messages
threadId
sendMessage
isPending
error
```

因此 Phase 23 必须：

> 删除 `AgentChatPage` 内重复的 Chat 请求和会话状态逻辑，改为直接消费 `useAgentChat`。

不要保留两套 Chat 状态实现。

---

# 二、Tailwind / shadcn 当前状态

当前项目：

```text
React 19
TypeScript
Vite 7
React Router
TanStack Query
axios
```

当前尚未安装：

```text
Tailwind CSS
shadcn/ui
Lucide React
```

请先检查当前生态下与现有 Vite / React 版本兼容的稳定配置方式，然后完成必要的最小初始化。

目标技术组合：

```text
设计指导：
已有确认过的 GistAI Chat UI 方案
+ ui-ux-pro-max 的设计原则（如果当前环境可用）

实现：
Tailwind CSS
+ shadcn/ui
+ Lucide React
```

重要：

> ui-ux-pro-max 只是设计指导，不要把它当成另一个 UI Framework。

真正的代码组件体系统一使用：

```text
shadcn/ui + Tailwind CSS
```

---

# 三、依赖处理原则

可以直接安装完成本阶段所需的必要依赖。

但必须保持最小范围。

只安装 Tailwind / shadcn 当前标准实现以及本页面实际需要的依赖，例如：

```text
Tailwind CSS 的 Vite 集成依赖
shadcn/ui 所需基础依赖
lucide-react
```

不要安装：

```text
Redux
Zustand
Framer Motion
Markdown 编辑器
大型 UI Framework
Ant Design
Material UI
额外状态管理库
```

如果自动 npm install 因本地环境问题失败：

1. 不要通过奇怪 workaround 修改项目；
2. 把需要用户手动执行的 npm 命令明确列出来；
3. 继续完成能够安全完成的代码配置；
4. 在最终报告中明确说明未完成的依赖安装步骤。

---

# 四、shadcn 初始化原则

只初始化当前 Chat MVP 真正需要的能力。

优先只增加类似：

```text
Button
Textarea
Badge
```

必要时可以增加一个简单容器类组件，但不要一次生成大量 shadcn 组件。

如果标准 shadcn 初始化需要：

```text
components.json
src/lib/utils.ts
路径 alias
Vite alias
tsconfig alias
```

可以按当前官方/稳定方式正确配置。

但是不要做与当前 Chat MVP 无关的大规模工程改造。

---

# 五、页面结构

保持当前已有路由：

```text
/          HomePage
/agent     AgentChatPage
```

不要新建 `/chat` 路由。

不要修改后端 API。

`App.tsx` 的 Home 健康检查功能需要保留。

---

# 六、Chat 页面组件拆分

建议把现有单文件 `AgentChatPage.tsx` 适当拆成：

```text
apps/web/src/
├─ pages/
│  └─ AgentChatPage.tsx
│
└─ components/
   └─ chat/
      ├─ ChatMessage.tsx
      ├─ ChatInput.tsx
      └─ SourceList.tsx
```

不要继续拆更多小组件。

---

# 七、AgentChatPage 职责

`AgentChatPage` 只负责：

```text
页面 Layout
调用 useAgentChat
把数据传给子组件
组合 Empty / Conversation / Loading / Error
```

必须使用：

```ts
const {
  messages,
  sendMessage,
  isPending,
  error,
} = useAgentChat()
```

不要：

```text
直接调用 axios
直接调用 agentApi
自己创建 useMutation
自己保存 threadId
自己维护 messages
```

`threadId` 可以留在 Hook 内管理，页面第一版不需要展示它。

---

# 八、ChatInput

`ChatInput` 管理自己的：

```text
input value
```

第一版交互：

```text
Enter
→ 发送

Shift + Enter
→ 换行

空输入
→ 不发送

isPending
→ 禁止重复发送
```

发送成功触发后：

```text
清空输入框
```

调用父组件传入的：

```text
onSend(message)
```

不要在 ChatInput 内直接调 API。

输入长度与后端保持一致：

```text
maxLength = 4000
```

---

# 九、ChatMessage

必须直接使用现有：

```text
types/chat.ts
ChatMessage
```

不要重新定义 `ChatMessage`。

展示逻辑：

```text
role === user
→ 用户消息

role === assistant
→ Agent 回答
```

Assistant 根据：

```text
status
```

支持：

```text
answer
partial
insufficient
error
```

UI 第一版：

### answer

正常正文展示。

### partial

显示轻量状态 Badge / Notice：

```text
部分回答
```

并提示：

```text
当前证据只能支持部分结论
```

### insufficient

显示：

```text
证据不足
```

不要用很严重的红色错误视觉。

### error

这是 Agent 成功响应中的业务错误状态。

显示：

```text
处理失败
```

可以使用轻量错误色。

不要和 HTTP 请求失败混为一谈。

---

# 十、SourceList

Assistant Message 有：

```text
sources
```

有来源时显示：

```text
Sources / 资料来源
```

支持两类：

## knowledge_base

显示：

```text
title
个人知识库
```

当前不强制跳 Article Detail。

如果项目当前没有 Article Detail 前端路由：

> 不要为了 Phase 23 临时实现。

## web

如果：

```text
url != null
```

则允许点击打开：

```text
target="_blank"
rel="noopener noreferrer"
```

可以展示：

```text
source
published_at
```

如果没有就简单显示：

```text
外部网页
```

---

# 十一、页面状态

第一版需要处理：

## Empty

没有消息时：

```text
GistAI 知识助手

基于个人知识库和允许访问的外部资料回答问题。

可以放 2～3 条静态示例文案，但不要实现复杂快捷提问系统。
```

## Conversation

正常展示：

```text
User Message
Assistant Message
Sources
```

## Loading

`isPending === true` 时：

显示简单状态：

```text
正在思考并查找资料…
```

可以使用 Lucide 的 Loader 图标。

不要做复杂 Agent Step / Tool Trace。

## HTTP Error

`useAgentChat.error` 有值时：

在输入区附近显示轻量错误提示。

不要制造 assistant message。

---

# 十二、UI 视觉方向

遵循已经确认过的 GistAI Chat MVP UI：

整体：

```text
浅色
简洁
现代
留白充足
PC 优先，同时保证基本移动端可用
```

结构：

```text
Header

Conversation / Empty State

底部 Chat Input
```

Assistant Message：

> 更接近 AI 阅读/知识助手正文，不要做成非常重的微信式聊天气泡。

User Message：

> 可以用浅背景气泡，与 Assistant 明显区分。

Sources：

> 放在 Assistant Answer 下方，视觉层级低于正文。

状态色：

```text
answer
→ 默认

partial
→ 温和 warning

insufficient
→ 中性 / warning

error
→ muted destructive
```

不要做：

```text
大面积渐变
玻璃拟态
过度动画
复杂 Dashboard
侧边栏
历史会话列表
Agent Debug Panel
```

---

# 十三、styles.css 处理

当前 `styles.css` 已经有大量旧 Chat CSS，例如：

```text
.chat-shell
.chat-card
.message
.composer
.sources
...
```

接入 Tailwind 后：

1. Chat 页面尽量迁移到 Tailwind / shadcn；
2. 删除确认已经不再使用的旧 Chat CSS；
3. HomePage 当前健康检查相关样式可以继续保留；
4. 注意当前全局：

```css
button { ... }
```

这类样式可能会污染 shadcn Button。

需要调整为不会破坏 shadcn 组件的方式。

不要为了 Tailwind 把 HomePage 也全部重写。

目标：

> Chat 使用 Tailwind/shadcn，Home 现有功能稳定保留。

---

# 十四、现有 Hook 不要随意修改

`useAgentChat.ts` 已经通过 Phase 22 Review。

除非接页面时发现明确 bug，否则不要重写它。

现有职责：

```text
messages
threadId
sendMessage
isPending
error
```

必须复用。

如果确实发现必须修改：

* 仅做最小修改；
* 最终报告中说明原因。

---

# 十五、本阶段暂不做

严格不要实现：

```text
Conversation History
历史会话 Sidebar
新建/删除/重命名会话管理
Store
Service 层
Zustand / Redux
localStorage thread persistence
Streaming
SSE
WebSocket
Markdown 高级渲染
Retry 按钮
Abort / Cancel
Agent Tool Trace
Agent Steps
模型选择
Web Search 开关
Knowledge Base 筛选器
Article Detail 页面
```

第一目标：

> 把基础 Chat MVP 真正跑通。

---

# 十六、需要验证的真实主链

至少人工/代码层确认：

### 第一次问题

```text
用户输入
↓
ChatInput
↓
AgentChatPage
↓
useAgentChat.sendMessage
↓
POST /api/v1/agent/chat
↓
thread_id = null
↓
后端生成 thread_id
↓
返回 Answer
↓
页面展示
```

### 第二次问题

```text
继续输入追问
↓
useAgentChat
↓
自动携带已有 threadId
↓
后端恢复同一 Agent Thread
↓
返回第二轮 Answer
↓
页面追加消息
```

---

# 十七、验证要求

完成后至少执行：

```text
npm / TypeScript dependency consistency check
tsc -b
Vite production build
git diff --check
```

如果依赖安装成功，还需要确保：

```text
npm run dev
```

能够正常启动。

如果后端本地可用，可以做一次真实 `/agent` 页面验证。

不要因为无法访问 LLM/Tavily 而伪造“真实 Agent 已成功”。

---

# 十八、完成后报告

请明确给出：

1. 新增文件
2. 修改文件
3. 安装的依赖
4. Tailwind 如何配置
5. shadcn 如何初始化
6. 实际使用了哪些 shadcn 组件
7. `AgentChatPage` 如何改为使用 `useAgentChat`
8. 删除了哪些旧重复逻辑
9. 删除了哪些旧 Chat CSS
10. HomePage 是否保持正常
11. TypeScript / Build / git diff 验证结果
12. 是否存在需要用户手动执行的 npm install 命令
13. 是否发现阻塞 Phase 23 的问题

完成后停止。

不要继续开发 Phase 24。
