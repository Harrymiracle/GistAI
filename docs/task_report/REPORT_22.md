Phase 22 已完成，未继续开发页面或 Phase 23。
新增文件：
- [types/chat.ts](E:/practice/projects/GistAI/apps/web/src/types/chat.ts)：Chat UI Model。
- [hooks/useAgentChat.ts](E:/practice/projects/GistAI/apps/web/src/hooks/useAgentChat.ts)：会话状态和 API 调用编排。
ChatMessage 最终结构：
interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: AgentResponseStatus
  sources?: AgentSource[]
}
useAgentChat 对外暴露：
{
  messages,
  threadId,
  sendMessage,
  isPending,
  error,
}
threadId 流程：
- 第一次请求传递 thread_id: null，由后端生成真实 ID。
- 成功后保存响应中的 thread_id。
- 后续请求自动携带当前 threadId。
错误处理：
- HTTP、网络、超时等请求失败：保留 user message，设置 error；优先采用后端统一响应的 message，否则使用通用文案。
- 成功响应但 status === 'error'：仍追加 assistant message，使用响应的 answer、status 和 sources。
- pending 期间使用同步 in-flight 锁阻止重复请求，避免同一渲染周期的连续调用产生多个线程。
验证结果：
- npm exec -- tsc -b：通过。
- git diff --check：通过。
- 新文件行尾空白检查：通过。
- npm run build:web：通过，Vite 成功构建 144 个模块。
- 独立代码复核：并发问题修正后，无 Critical 或 Important 问题。
未发现现有前端结构阻塞。QueryClientProvider 已存在，Hook 可以在下一阶段由页面直接使用。