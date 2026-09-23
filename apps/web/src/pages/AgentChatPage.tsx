import {
  ArrowLeft,
  BookOpenText,
  LoaderCircle,
  MessageSquarePlus,
  Sparkles,
} from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { ChatInput } from '@/components/chat/ChatInput'
import { ChatMessage } from '@/components/chat/ChatMessage'
import { Button } from '@/components/ui/button'
import { useAgentChat } from '@/hooks/useAgentChat'

const exampleQuestions = [
  '总结一下我知识库里关于大语言模型训练的内容',
  '只根据我的知识库回答：大语言模型训练有哪些阶段？',
  'RAG 的基本工作流程是什么？',
]

export function AgentChatPage() {
  const {
    messages,
    allowWeb,
    setAllowWeb,
    sendMessage,
    newChat,
    isPending,
    error,
  } = useAgentChat()
  const conversationEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (messages.length === 0 && !isPending) {
      return
    }

    const prefersReducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches

    conversationEndRef.current?.scrollIntoView({
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
      block: 'end',
    })
  }, [messages, isPending])

  return (
    <main className="min-h-svh bg-slate-100 px-0 py-0 text-slate-950 sm:px-5 sm:py-6">
      <section className="mx-auto grid min-h-svh w-full max-w-5xl grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-white sm:min-h-[calc(100svh-3rem)] sm:rounded-3xl sm:border sm:border-slate-200 sm:shadow-xl sm:shadow-slate-900/5">
        <header className="border-b border-slate-200 bg-white px-5 py-4 sm:px-8 sm:py-5">
          <Link
            className="mb-3 inline-flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-slate-900"
            to="/"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            返回首页
          </Link>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
                <BookOpenText className="size-5" aria-hidden="true" />
              </span>
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-slate-950 sm:text-2xl">
                  GistAI 知识助手
                </h1>
                <p className="mt-1 text-sm text-slate-500">
                  基于个人知识库和允许访问的外部资料回答问题。
                </p>
              </div>
            </div>
            <Button
              className="self-start sm:self-auto"
              type="button"
              variant="outline"
              disabled={isPending}
              onClick={newChat}
            >
              <MessageSquarePlus aria-hidden="true" />
              新建会话
            </Button>
          </div>
        </header>

        <div
          className="overflow-y-auto bg-slate-50/70 px-5 py-6 sm:px-8 sm:py-8"
          aria-live="polite"
          aria-busy={isPending}
        >
          {messages.length === 0 ? (
            <div className="mx-auto flex h-full max-w-2xl flex-col justify-center py-10 text-center">
              <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-blue-50 text-blue-700">
                <Sparkles className="size-6" aria-hidden="true" />
              </span>
              <h2 className="mt-5 text-2xl font-semibold tracking-tight text-slate-900">
                从你的知识开始提问
              </h2>
              <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
                我会优先结合你的个人知识库，并在允许时参考外部资料。
              </p>
              <ul className="mx-auto mt-7 grid w-full max-w-xl gap-2 text-left text-sm text-slate-600 sm:grid-cols-3">
                {exampleQuestions.map((question) => (
                  <li key={question}>
                    <Button
                      className="h-full min-h-14 w-full justify-start whitespace-normal rounded-xl px-3.5 py-3.5 text-left leading-5 shadow-sm"
                      type="button"
                      variant="outline"
                      disabled={isPending}
                      onClick={() => sendMessage(question)}
                    >
                      {question}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-7">
              {messages.map((message) => (
                <ChatMessage message={message} key={message.id} />
              ))}
            </div>
          )}

          {isPending ? (
            <div
              className="mx-auto mt-6 flex max-w-3xl items-center gap-2 text-sm text-slate-500"
              role="status"
            >
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              正在思考并查找资料…
            </div>
          ) : null}
          <div ref={conversationEndRef} aria-hidden="true" />
        </div>

        <div className="bg-white">
          <label className="flex items-center justify-between gap-4 px-5 pt-4 sm:px-6 sm:pt-5">
            <span>
              <span className="block text-sm font-medium text-slate-800">
                允许联网补充
              </span>
              <span className="mt-0.5 block text-xs leading-5 text-slate-500">
                知识库不足或需要最新信息时，可搜索网页。
              </span>
            </span>
            <input
              className="peer sr-only"
              type="checkbox"
              checked={allowWeb}
              disabled={isPending}
              onChange={(event) => setAllowWeb(event.target.checked)}
            />
            <span
              className="relative h-6 w-11 shrink-0 rounded-full bg-slate-300 transition-colors after:absolute after:left-1 after:top-1 after:size-4 after:rounded-full after:bg-white after:shadow-sm after:transition-transform peer-checked:bg-blue-600 peer-checked:after:translate-x-5 peer-disabled:cursor-not-allowed peer-disabled:opacity-50 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-blue-600"
              aria-hidden="true"
            />
          </label>
          <ChatInput
            isPending={isPending}
            error={error}
            onSend={sendMessage}
          />
        </div>
      </section>
    </main>
  )
}
