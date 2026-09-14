import { useMutation } from '@tanstack/react-query'
import { FormEvent, KeyboardEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  agentApi,
  AgentResponseStatus,
  AgentSource,
} from '../api/agent'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: AgentResponseStatus
  sources?: AgentSource[]
}

interface ChatVariables {
  message: string
  threadId: string | null
}

const statusNotices: Partial<Record<AgentResponseStatus, string>> = {
  partial: '部分信息有依据，但现有证据不足以覆盖全部问题。',
  insufficient: '当前知识库和允许使用的外部资料中，没有找到足够证据。',
  error: '本次处理未能正常完成，请稍后重试。',
}

function messageId(): string {
  return crypto.randomUUID()
}

function SourceList({ sources }: { sources: AgentSource[] }) {
  if (sources.length === 0) {
    return null
  }

  return (
    <section className="sources" aria-label="回答来源">
      <h3>资料来源</h3>
      <ul>
        {sources.map((source, index) => (
          <li key={`${source.source_type}-${source.article_id ?? source.url}-${index}`}>
            {source.source_type === 'web' && source.url ? (
              <a href={source.url} target="_blank" rel="noopener noreferrer">
                {source.title}
              </a>
            ) : (
              <span>{source.title}</span>
            )}
            <small>
              {source.source_type === 'knowledge_base'
                ? '个人知识库'
                : [source.source, source.published_at].filter(Boolean).join(' · ') ||
                  '外部网页'}
            </small>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function AgentChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: ({ message, threadId: activeThreadId }: ChatVariables) =>
      agentApi.chat({
        message,
        ...(activeThreadId ? { thread_id: activeThreadId } : {}),
      }),
    onSuccess: (response) => {
      setThreadId(response.thread_id)
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: 'assistant',
          content: response.answer,
          status: response.status,
          sources: response.sources,
        },
      ])
    },
    onError: () => {
      setError('暂时无法连接 AI 助手，请稍后重试。')
    },
  })

  const submitMessage = () => {
    const message = input.trim()
    if (!message || mutation.isPending) {
      return
    }

    setError(null)
    setInput('')
    setMessages((current) => [
      ...current,
      { id: messageId(), role: 'user', content: message },
    ])
    mutation.mutate({ message, threadId })
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    submitMessage()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submitMessage()
    }
  }

  const startNewChat = () => {
    setMessages([])
    setThreadId(null)
    setInput('')
    setError(null)
    mutation.reset()
  }

  return (
    <main className="chat-shell">
      <section className="chat-card">
        <header className="chat-header">
          <div>
            <Link className="back-link" to="/">返回首页</Link>
            <p className="eyebrow">AI 阅读助手</p>
            <h1>知识助手</h1>
            <p>基于你的知识库和允许访问的外部资料回答问题。</p>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={startNewChat}
            disabled={mutation.isPending}
          >
            新对话
          </button>
        </header>

        <div className="conversation" aria-live="polite">
          {messages.length === 0 ? (
            <div className="empty-chat">
              <h2>从一个问题开始</h2>
              <p>例如：我保存的文章里，Agent Memory 是怎么说的？</p>
            </div>
          ) : (
            messages.map((message) => (
              <article
                className={`message message--${message.role}`}
                key={message.id}
              >
                <p className="message-role">
                  {message.role === 'user' ? '你' : '知识助手'}
                </p>
                <div className="message-content">{message.content}</div>
                {message.status && statusNotices[message.status] ? (
                  <p className={`answer-notice answer-notice--${message.status}`}>
                    {statusNotices[message.status]}
                  </p>
                ) : null}
                <SourceList sources={message.sources ?? []} />
              </article>
            ))
          )}
          {mutation.isPending ? (
            <div className="thinking" role="status">
              正在思考并查找资料…
            </div>
          ) : null}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          {error ? <p className="request-error">{error}</p> : null}
          <div className="composer-row">
            <textarea
              aria-label="输入问题"
              value={input}
              maxLength={4000}
              placeholder="输入你的问题…"
              rows={3}
              disabled={mutation.isPending}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
            />
            <button
              type="submit"
              disabled={mutation.isPending || input.trim().length === 0}
            >
              {mutation.isPending ? '处理中' : '发送'}
            </button>
          </div>
          <p className="composer-hint">Enter 发送，Shift+Enter 换行</p>
        </form>
      </section>
    </main>
  )
}
