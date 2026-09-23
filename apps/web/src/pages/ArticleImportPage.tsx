import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import {
  ArrowLeft,
  BookOpenText,
  CircleAlert,
  CircleCheck,
  LoaderCircle,
} from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { createArticle } from '@/api/articles'
import { Button } from '@/components/ui/button'
import type { ArticleDetail } from '@/types/article'

interface ApiErrorBody {
  message?: string
}

interface ProcessingFailure {
  stage: string
  message: string
}

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    return error.response?.data.message ?? '导入请求失败，请稍后重试'
  }

  return error instanceof Error ? error.message : '导入请求失败，请稍后重试'
}

function getProcessingFailures(article: ArticleDetail): ProcessingFailure[] {
  const failures: ProcessingFailure[] = []

  if (article.fetch_status === 'failed') {
    failures.push({
      stage: 'URL 抓取与正文提取',
      message: article.fetch_error ?? '未能获取有效正文',
    })
  }
  if (article.ai_status === 'failed') {
    failures.push({
      stage: 'AI 摘要与标签',
      message: article.ai_error ?? 'AI 处理失败',
    })
  }
  if (article.embedding_status === 'failed') {
    failures.push({
      stage: '文章切片与 Embedding',
      message: article.embedding_error ?? 'Embedding 处理失败',
    })
  }

  return failures
}

export function ArticleImportPage() {
  const [url, setUrl] = useState('')
  const mutation = useMutation({
    mutationFn: createArticle,
  })

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const sourceUrl = url.trim()

    if (!sourceUrl) {
      return
    }

    mutation.mutate({
      source_url: sourceUrl,
      source_type: 'web',
    })
  }

  const article = mutation.data
  const isCompleted = article?.status === 'completed'
  const isProcessingFailed =
    article?.status === 'failed' || article?.status === 'partial_failed'
  const processingFailures = article ? getProcessingFailures(article) : []

  return (
    <main className="min-h-svh bg-slate-100 px-5 py-8 text-slate-950 sm:py-14">
      <section className="mx-auto w-full max-w-2xl rounded-3xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-900/5 sm:p-10">
        <Link
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-slate-900"
          to="/"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          返回首页
        </Link>

        <div className="mt-7 flex items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-blue-600 text-white shadow-sm">
            <BookOpenText className="size-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              导入文章
            </h1>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              输入公开文章 URL，系统将同步提取正文、生成摘要与标签，并写入知识库。
            </p>
          </div>
        </div>

        <form className="mt-8" onSubmit={handleSubmit}>
          <label
            className="text-sm font-medium text-slate-800"
            htmlFor="article-url"
          >
            文章 URL
          </label>
          <input
            id="article-url"
            className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-3 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100"
            type="url"
            inputMode="url"
            autoComplete="url"
            placeholder="https://example.com/article"
            value={url}
            disabled={mutation.isPending}
            required
            onChange={(event) => {
              setUrl(event.target.value)
              if (mutation.isSuccess || mutation.isError) {
                mutation.reset()
              }
            }}
          />
          <p className="mt-2 text-xs leading-5 text-slate-500">
            导入过程会等待后端完成全部处理，耗时取决于文章长度和 AI 服务响应速度。
          </p>

          <Button
            className="mt-5 h-10 w-full rounded-xl bg-blue-600 px-4 text-white hover:bg-blue-700 sm:w-auto"
            type="submit"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <LoaderCircle className="animate-spin" aria-hidden="true" />
            ) : null}
            {mutation.isPending ? '正在导入' : '导入文章'}
          </Button>
        </form>

        {mutation.isError ? (
          <div
            className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
            role="alert"
          >
            <div className="flex items-start gap-2.5">
              <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <p className="font-medium">导入请求失败</p>
                <p className="mt-1 leading-6">{getErrorMessage(mutation.error)}</p>
              </div>
            </div>
          </div>
        ) : null}

        {isCompleted && article ? (
          <div
            className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-emerald-950"
            role="status"
          >
            <div className="flex items-start gap-3">
              <CircleCheck
                className="mt-0.5 size-5 shrink-0 text-emerald-600"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <h2 className="font-semibold">导入成功</h2>
                <p className="mt-1 truncate text-sm text-emerald-800">
                  {article.title ?? article.source_url}
                </p>
                <p className="mt-2 text-xs text-emerald-700">
                  正文、AI 摘要与标签、文章切片和向量均已处理完成。
                </p>
                <Link
                  className="mt-4 inline-flex h-9 items-center justify-center rounded-lg bg-emerald-700 px-4 text-sm font-medium text-white transition-colors hover:bg-emerald-800"
                  to="/agent"
                >
                  去 Agent Chat
                </Link>
              </div>
            </div>
          </div>
        ) : null}

        {isProcessingFailed && article ? (
          <div
            className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-amber-950"
            role="alert"
          >
            <div className="flex items-start gap-3">
              <CircleAlert
                className="mt-0.5 size-5 shrink-0 text-amber-600"
                aria-hidden="true"
              />
              <div>
                <h2 className="font-semibold">文章未能完整导入</h2>
                <p className="mt-1 text-sm leading-6 text-amber-800">
                  Article 已创建，但同步处理链路存在失败阶段。
                </p>
                {processingFailures.length > 0 ? (
                  <ul className="mt-3 space-y-2 text-sm">
                    {processingFailures.map((failure) => (
                      <li key={failure.stage}>
                        <span className="font-medium">{failure.stage}：</span>
                        {failure.message}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm">后端未返回具体的阶段错误信息。</p>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  )
}
