Phase 23 已完成，未继续开发 Phase 24。
文件变更
新增：
- [components.json](E:/practice/projects/GistAI/apps/web/components.json)
- [ChatInput.tsx](E:/practice/projects/GistAI/apps/web/src/components/chat/ChatInput.tsx)
- [ChatMessage.tsx](E:/practice/projects/GistAI/apps/web/src/components/chat/ChatMessage.tsx)
- [SourceList.tsx](E:/practice/projects/GistAI/apps/web/src/components/chat/SourceList.tsx)
- [button.tsx](E:/practice/projects/GistAI/apps/web/src/components/ui/button.tsx)
- [textarea.tsx](E:/practice/projects/GistAI/apps/web/src/components/ui/textarea.tsx)
- [badge.tsx](E:/practice/projects/GistAI/apps/web/src/components/ui/badge.tsx)
- [utils.ts](E:/practice/projects/GistAI/apps/web/src/lib/utils.ts)
修改：
- [AgentChatPage.tsx](E:/practice/projects/GistAI/apps/web/src/pages/AgentChatPage.tsx)
- [styles.css](E:/practice/projects/GistAI/apps/web/src/styles.css)
- [App.tsx](E:/practice/projects/GistAI/apps/web/src/App.tsx)
- [vite.config.ts](E:/practice/projects/GistAI/apps/web/vite.config.ts)
- [tsconfig.json](E:/practice/projects/GistAI/apps/web/tsconfig.json)
- [tsconfig.app.json](E:/practice/projects/GistAI/apps/web/tsconfig.app.json)
- [package.json](E:/practice/projects/GistAI/apps/web/package.json)
- package-lock.json
UI 基础
按照官方当前方案，通过 @tailwindcss/vite 接入 Tailwind CSS v4，并配置了 @/* 路径 alias。Tailwind Vite 文档
shadcn 使用当前 Nova/Lucide 预设初始化，生成源码组件而非引入大型 UI Framework。shadcn Vite 文档
实际使用的 shadcn 组件：
- Button
- Textarea
- Badge
主要新增依赖包括：
- tailwindcss
- @tailwindcss/vite
- shadcn
- @base-ui/react
- class-variance-authority
- cn
- tw-animate-css
- lucide-react
- @fontsource-variable/geist
Chat 页面收口
AgentChatPage 现在只调用：
const {
  messages,
  sendMessage,
  isPending,
  error,
} = useAgentChat()
已删除页面内旧有的：
- useMutation
- agentApi 调用
- messages 和 threadId 状态
- Message ID 生成
- 错误状态管理
- 新会话逻辑
- 内嵌 SourceList
- 重复 ChatMessage 类型
useAgentChat 本阶段未修改。第一次请求传递 thread_id: null，成功后保存后端 ID，第二次请求自动携带该 ID；该流程已从代码层确认。由于本地 FastAPI 未启动，没有伪造真实 Agent 调用成功。
交互与状态
- Enter 发送，Shift+Enter 换行。
- 支持中文输入法组合状态。
- 输入 trim、空输入拦截、4000 字限制。
- pending 时禁止重复发送。
- 支持 answer、partial、insufficient、error 四种业务状态。
- HTTP 错误显示在输入区附近，不创建 assistant message。
- 来源链接仅允许 http/https，并设置安全的新窗口属性。
- 长对话会自动跟随新消息，并尊重 reduced-motion 设置。
CSS 清理
删除了所有旧 Chat CSS，包括：
- .chat-shell
- .chat-card
- .chat-header
- .conversation
- .empty-chat
- .message*
- .answer-notice*
- .sources
- .thinking
- .composer*
- .request-error
原全局 button 样式已移除，Home 按钮改为 .health-button，不会再污染 shadcn 组件。
HomePage 健康检查功能和路由保持不变，并已在浏览器中确认页面样式正常。
验证结果
- npm ls --workspace @gistai/web --depth=0：通过。
- npm exec -- tsc -b：通过。
- npm run build:web：通过，转换 2047 个模块。
- git diff --check：通过。
- 新增文件行尾空白检查：通过。
- npm run dev:web：成功启动。
- /：HTTP 200。
- /agent：HTTP 200。
- 浏览器控制台：无警告或错误。
- 独立代码审查：无 Critical 或 Important 问题。
无需用户手动执行额外的 npm 安装命令。唯一未执行的是实际 Agent 对话，因为本地 127.0.0.1:8000 未启动；这不阻塞 Phase 23 前端实现。