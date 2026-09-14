Phase 19 已完成，范围严格限定为 Agent HTTP API 与前端 Chat MVP，没有进入 Task 8。
1. 修改 / 新增文件
后端：
- [Agent Chat 服务](E:/practice/projects/GistAI/apps/server/app/agent/chat.py)
- [Agent API 路由](E:/practice/projects/GistAI/apps/server/app/api/v1/agent.py)
- [Agent API Schema](E:/practice/projects/GistAI/apps/server/app/schemas/agent.py)
- [依赖组装](E:/practice/projects/GistAI/apps/server/app/api/deps.py)
- [API Router](E:/practice/projects/GistAI/apps/server/app/api/v1/router.py)
- [安全异常](E:/practice/projects/GistAI/apps/server/app/core/exceptions.py)
- [Agent API 测试](E:/practice/projects/GistAI/apps/server/tests/test_agent_api.py)
前端：
- [axios 实例](E:/practice/projects/GistAI/apps/web/src/api/request.ts)
- [Agent API 类型与封装](E:/practice/projects/GistAI/apps/web/src/api/agent.ts)
- [知识助手页面](E:/practice/projects/GistAI/apps/web/src/pages/AgentChatPage.tsx)
- [前端路由](E:/practice/projects/GistAI/apps/web/src/App.tsx)
- [Query/Router 初始化](E:/practice/projects/GistAI/apps/web/src/main.tsx)
- [页面样式](E:/practice/projects/GistAI/apps/web/src/styles.css)
- [开发代理配置](E:/practice/projects/GistAI/apps/web/vite.config.ts)
- [README](E:/practice/projects/GistAI/README.md)
2. API Contract
POST /api/v1/agent/chat
请求：
{
  "message": "用户当前问题",
  "thread_id": "可选 UUID"
}
约束：
- message 自动去除首尾空白
- 长度为 1～4000 字符
- thread_id 必须为有效 UUID
- 禁止额外字段，包括 user_id
响应数据：
{
  "thread_id": "UUID",
  "answer": "回答内容",
  "status": "answer | partial | insufficient | error",
  "sources": [
    {
      "source_type": "knowledge_base | web",
      "title": "来源标题",
      "article_id": null,
      "chunk_id": null,
      "url": null,
      "source": null,
      "published_at": null
    }
  ]
}
3. thread_id
- 首次请求由后端生成 UUID。
- 前端保存返回的 thread_id。
- 后续请求只发送新问题和同一个 thread_id，不重复发送完整历史。
- “新对话”只清理前端本地状态。
- 当前仍使用 InMemorySaver：刷新页面开始新对话，服务重启后 checkpoint 丢失。
4. 用户隔离
用户 ID 只来自服务端 get_current_user_id 依赖。
内部 checkpoint key 使用：
用户ID:公开thread_id
因此即使不同用户提交同一个 UUID，也不会共享 Agent 上下文。客户端不能提交 user_id。
5. Agent 调用链
React /agent
→ POST /api/v1/agent/chat
→ 服务端 current_user
→ AgentContext
→ AgentChatService
→ graph.invoke
→ InMemory checkpoint
→ 精简 API Response
接口使用同步 def，符合现有同步 Graph 和数据库服务；FastAPI 会在线程池中执行，不阻塞异步事件循环。
6. Response Mapping
- 证据充分且回答成功：answer
- 有实际依据但覆盖不完整：partial
- 没有足够依据：insufficient
- Graph 安全失败或回答生成失败且没有最终来源：error
- partial 和 insufficient 均返回 HTTP 200。
- 未预期异常返回安全 HTTP 500，不向客户端泄露原始异常或堆栈。
7. Sources
- 知识库来源：article_id、可选 chunk_id、title
- Web 来源：title、url、source、published_at
- 不返回全文、临时切片、相似度、推理过程、Tool 状态或 Provider 原始数据。
- 当前没有稳定文章详情路由，因此未伪造知识库链接。
- Web 来源使用新标签页安全打开。
8. 前端
新增 /agent 知识助手页面，包含：
- 用户与助手消息
- TanStack useMutation
- 本地消息、输入、thread ID、错误状态
- Enter 发送、Shift+Enter 换行
- Loading 和重复提交限制
- Answer、Partial、Insufficient、Error 提示
- KB/Web Sources
- 新对话重置
- 纯文本安全渲染，没有使用 dangerouslySetInnerHTML
9. Timeout
- 前端 Agent 请求：有限的 300 秒超时。
- 后端未增加无限等待。
- 下游仍使用现有有限超时：网页请求默认 15 秒、浏览器导航 30 秒、网络空闲 5 秒、Web Search 15 秒、LLM 与 Embedding 60 秒。
10. 测试
- Agent API tests：6 passed
- Agent backend tests：109 passed
- Agent/Search/RAG/Fetch 定向回归：178 passed
- Full backend：301 passed
- Frontend tests：未配置，未额外引入测试框架
- Frontend production build：通过
- Python compileall：通过
- pip check：通过，无依赖冲突
- git diff --check：通过
11. Demo 验证
由于未读取或输出本机真实密钥，外部能力采用现有可控测试验证：
- KB-only：回答与知识库来源映射通过。
- Fresh/Web：Web Search 流程与 Web 来源映射通过。
- Insufficient：明确返回 insufficient，不生成无依据事实。
- Safe failure：明确返回 error，响应不包含内部异常内容。
12. Code Review
- Critical：无
- Important：无
- Minor：无阻断问题
- 已确认没有前端暴露 Agent 内部运行字段，没有硬编码服务地址或密钥。
13. 明确未实现
未实现：
- PostgreSQL checkpoint
- 长期 Memory
- 会话持久化与会话列表
- Streaming、SSE、WebSocket
- save_to_knowledge_base
- 多 Agent
- Task 8 及后续功能