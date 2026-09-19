import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import { useRef, useState } from 'react'
import { sendAgentMessage } from '../api/agent'
import type { ApiResponse } from '../types/api'
import type { ChatMessage } from '../types/chat'

const fallbackErrorMessage = '请求失败，请稍后重试'

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
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const isSendingRef = useRef(false)

  const mutation = useMutation({
    mutationFn: sendAgentMessage,
    onSuccess: (response) => {
      setThreadId(response.thread_id)
      setMessages((current) => [
        ...current,
        {
          id: createMessageId(),
          role: 'assistant',
          content: response.answer,
          status: response.status,
          sources: response.sources,
        },
      ])
    },
    onError: (requestError) => {
      setError(getErrorMessage(requestError))
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
    setError(null)
    setMessages((current) => [
      ...current,
      {
        id: createMessageId(),
        role: 'user',
        content: normalizedMessage,
      },
    ])
    mutation.mutate({
      message: normalizedMessage,
      thread_id: threadId,
    })
  }

  return {
    messages,
    threadId,
    sendMessage,
    isPending: mutation.isPending,
    error,
  }
}
