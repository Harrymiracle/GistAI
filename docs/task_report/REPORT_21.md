已完成 Phase 21，仅修改 Agent API 请求层与类型定义。
文件变更：
- 新增 [types/api.ts](E:/practice/projects/GistAI/apps/web/src/types/api.ts)：定义 ApiResponse<T>。
- 新增 [types/agent.ts](E:/practice/projects/GistAI/apps/web/src/types/agent.ts)：定义请求、响应状态、来源及聊天数据类型。
- 新增 [api/client.ts](E:/practice/projects/GistAI/apps/web/src/api/client.ts)：统一 axios 实例，基础路径 /api/v1，超时 300 秒。
- 修改 [api/agent.ts](E:/practice/projects/GistAI/apps/web/src/api/agent.ts)：新增 sendAgentMessage()，并保留 agentApi.chat 兼容入口。
- 删除旧的 api/request.ts。
核心调用方式：
const data = await sendAgentMessage({
  message: '用户问题',
  thread_id: currentThreadId,
})
实际请求地址为 POST /api/v1/agent/chat，返回 AgentChatData。thread_id 支持省略或传入 null，来源非对应字段均正确建模为 nullable。
验证结果：
- git diff --check：通过。
- npm run build:web：通过。
- TypeScript 编译：通过。
- Vite 构建：通过，转换 144 个模块。
- /health 调用未修改。
- 未修改 Chat 页面、后端、Store 或下一阶段功能。