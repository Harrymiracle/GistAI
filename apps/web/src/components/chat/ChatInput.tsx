import { SendHorizontal } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface ChatInputProps {
  isPending: boolean
  error: string | null
  onSend: (message: string) => void
}

export function ChatInput({ isPending, error, onSend }: ChatInputProps) {
  const [input, setInput] = useState('')

  const submitMessage = () => {
    const message = input.trim()

    if (!message || isPending) {
      return
    }

    onSend(message)
    setInput('')
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    submitMessage()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === 'Enter' &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault()
      submitMessage()
    }
  }

  return (
    <form
      className="border-t border-slate-200 bg-white p-4 sm:p-5"
      onSubmit={handleSubmit}
    >
      {error ? (
        <p
          className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      <div className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm transition-shadow focus-within:border-blue-400 focus-within:ring-3 focus-within:ring-blue-100">
        <Textarea
          className="max-h-48 min-h-20 resize-none border-0 bg-transparent px-2 py-2.5 shadow-none focus-visible:border-transparent focus-visible:ring-0"
          aria-label="输入问题"
          value={input}
          maxLength={4000}
          placeholder="输入你的问题…"
          rows={3}
          disabled={isPending}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <Button
          className="mb-0.5 size-10 shrink-0 rounded-xl bg-blue-600 text-white hover:bg-blue-700"
          type="submit"
          size="icon"
          disabled={isPending || input.trim().length === 0}
          aria-label={isPending ? '正在发送' : '发送消息'}
        >
          <SendHorizontal aria-hidden="true" />
        </Button>
      </div>
      <p className="mt-2 px-1 text-xs text-slate-500">
        Enter 发送，Shift + Enter 换行
      </p>
    </form>
  )
}
