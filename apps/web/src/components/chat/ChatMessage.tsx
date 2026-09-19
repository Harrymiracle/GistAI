import { SourceList } from '@/components/chat/SourceList'
import { Badge } from '@/components/ui/badge'
import type { AgentResponseStatus } from '@/types/agent'
import type { ChatMessage as ChatMessageModel } from '@/types/chat'

interface ChatMessageProps {
  message: ChatMessageModel
}

const statusDetails: Partial<
  Record<
    AgentResponseStatus,
    {
      label: string
      description: string
      className: string
    }
  >
> = {
  partial: {
    label: '部分回答',
    description: '当前证据只能支持部分结论',
    className: 'bg-amber-100 text-amber-800',
  },
  insufficient: {
    label: '证据不足',
    description: '现有资料不足以形成可靠结论',
    className: 'bg-slate-200 text-slate-700',
  },
  error: {
    label: '处理失败',
    description: '本次请求已完成，但 Agent 未能生成有效回答',
    className: 'bg-red-50 text-red-700',
  },
}

export function ChatMessage({ message }: ChatMessageProps) {
  if (message.role === 'user') {
    return (
      <article className="ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-blue-600 px-4 py-3 text-sm leading-7 text-white shadow-sm sm:max-w-[72%] sm:px-5">
        <p className="sr-only">用户消息</p>
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
      </article>
    )
  }

  const statusDetail = message.status
    ? statusDetails[message.status]
    : undefined

  return (
    <article className="max-w-3xl text-slate-800">
      <p className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
        GistAI
      </p>
      <div className="whitespace-pre-wrap break-words text-[15px] leading-7">
        {message.content}
      </div>
      {statusDetail ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <Badge className={statusDetail.className}>{statusDetail.label}</Badge>
          <span>{statusDetail.description}</span>
        </div>
      ) : null}
      <SourceList sources={message.sources ?? []} />
    </article>
  )
}
