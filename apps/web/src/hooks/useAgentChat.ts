import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import { useEffect, useRef, useState } from 'react'
import { sendAgentMessage } from '../api/agent'
import type { AgentSource } from '../types/agent'
import type { ApiResponse } from '../types/api'
import type { ChatMessage } from '../types/chat'

const storageKey = 'gistai.agent.currentChat'
const storageVersion = 1
const fallbackErrorMessage = '请求失败，请稍后重试'
const interruptedErrorMessage = '上次提问在刷新时中断，回答结果未确认，请重新发送问题。'

interface ChatState {
  messages: ChatMessage[]
  threadId: string | null
  allowWeb: boolean
  pending: boolean
  interrupted: boolean
  error: string | null
}

function emptyChat(): ChatState {
  return { messages: [], threadId: null, allowWeb: true, pending: false, interrupted: false, error: null }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value))
}

function isAgentSource(value: unknown): value is AgentSource {
  return isRecord(value)
    && (value.source_type === 'knowledge_base' || value.source_type === 'web')
    && typeof value.title === 'string'
    && isNullableNumber(value.article_id)
    && isNullableNumber(value.chunk_id)
    && isNullableString(value.url)
    && isNullableString(value.source)
    && isNullableString(value.published_at)
}

function isChatMessage(value: unknown): value is ChatMessage {
  return isRecord(value)
    && typeof value.id === 'string'
    && (value.role === 'user' || value.role === 'assistant')
    && typeof value.content === 'string'
    && (value.status === undefined
      || value.status === 'answer'
      || value.status === 'partial'
      || value.status === 'insufficient'
      || value.status === 'error')
    && (value.sources === undefined
      || (Array.isArray(value.sources) && value.sources.every(isAgentSource)))
}

function loadChat(): ChatState {
  try {
    const stored = window.localStorage.getItem(storageKey)
    if (stored === null) {
      return emptyChat()
    }

    const value: unknown = JSON.parse(stored)
    if (!isRecord(value)
      || value.version !== storageVersion
      || !Array.isArray(value.messages)
      || !value.messages.every(isChatMessage)
      || !isNullableString(value.threadId)
      || typeof value.allowWeb !== 'boolean'
      || typeof value.pending !== 'boolean'
      || typeof value.interrupted !== 'boolean') {
      window.localStorage.removeItem(storageKey)
      return emptyChat()
    }

    return {
      messages: value.messages,
      threadId: value.threadId,
      allowWeb: value.allowWeb,
      pending: false,
      interrupted: value.pending || value.interrupted,
      error: value.pending || value.interrupted ? interruptedErrorMessage : null,
    }
  } catch {
    // 存储不可用或内容损坏时，仍允许打开空聊天页。
    return emptyChat()
  }
}

function createMessageId(): string {
  return crypto.randomUUID()
}

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiResponse<null>>(error)) {
    const message = error.response?.data?.message

    if (typeof message === 'string' && message.trim()) {
      return message.trim()
    }
  }

  return fallbackErrorMessage
}

export function useAgentChat() {
  const [chat, setChat] = useState<ChatState>(loadChat)
  const isSendingRef = useRef(false)

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({
        version: storageVersion,
        messages: chat.messages,
        threadId: chat.threadId,
        allowWeb: chat.allowWeb,
        pending: chat.pending,
        interrupted: chat.interrupted,
      }))
    } catch {
      // 禁用本地存储或超过配额时，当前页面仍可继续聊天。
    }
  }, [chat])

  const mutation = useMutation({
    mutationFn: sendAgentMessage,
    onSuccess: (response) => {
      setChat((current) => ({
        ...current,
        threadId: response.thread_id,
        pending: false,
        messages: [
          ...current.messages,
          {
            id: createMessageId(),
            role: 'assistant',
            content: response.answer,
            status: response.status,
            sources: response.sources,
          },
        ],
      }))
    },
    onError: (requestError) => {
      setChat((current) => ({
        ...current,
        pending: false,
        error: getErrorMessage(requestError),
      }))
    },
    onSettled: () => {
      isSendingRef.current = false
    },
  })

  const sendMessage = (message: string) => {
    const normalizedMessage = message.trim()

    if (!normalizedMessage || mutation.isPending || isSendingRef.current) {
      return
    }

    isSendingRef.current = true
    setChat((current) => ({
      ...current,
      pending: true,
      interrupted: false,
      error: null,
      messages: [
        ...current.messages,
        {
          id: createMessageId(),
          role: 'user',
          content: normalizedMessage,
        },
      ],
    }))
    mutation.mutate({
      message: normalizedMessage,
      thread_id: chat.threadId,
      allow_web_override: chat.allowWeb,
    })
  }

  const newChat = () => {
    if (mutation.isPending || isSendingRef.current) {
      return
    }

    try {
      window.localStorage.removeItem(storageKey)
    } catch {
      // 本地存储不可用时，仍清空当前页面的会话。
    }
    setChat(emptyChat())
    mutation.reset()
  }

  return {
    messages: chat.messages,
    threadId: chat.threadId,
    allowWeb: chat.allowWeb,
    setAllowWeb: (allowWeb: boolean) => setChat((current) => ({ ...current, allowWeb })),
    sendMessage,
    newChat,
    isPending: mutation.isPending,
    error: chat.error,
  }
}
