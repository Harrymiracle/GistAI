import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getArticle, getArticleRequestErrorMessage, reprocessArticle } from '@/api/articles'
import { ArticleStatusBadge } from '@/components/articles/ArticleStatusBadge'
import type { ArticleDetail } from '@/types/article'

type RecoveryAction = 'refetch' | 'continue'

function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? value : null
  } catch {
    return null
  }
}

function ProcessingStages({ article }: { article: ArticleDetail }) {
  const stages = [
    { name: '网页抓取与正文提取', status: article.fetch_status, error: article.fetch_error },
    { name: 'AI 摘要与标签', status: article.ai_status, error: article.ai_error },
    { name: '文章切片与向量', status: article.embedding_status, error: article.embedding_error },
  ]

  return (
    <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
      <h2 className="text-lg font-semibold">处理状态</h2>
      <ul className="mt-4 space-y-4">
        {stages.map((stage) => (
          <li className="border-t border-slate-100 pt-4 first:border-0 first:pt-0" key={stage.name}>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-medium">{stage.name}</span>
              <ArticleStatusBadge status={stage.status} />
            </div>
            {stage.error ? <p className="mt-2 whitespace-pre-wrap break-words text-sm text-red-700">{stage.error}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ArticleDetailPage() {
  const queryClient = useQueryClient()
  const { articleId } = useParams()
  const [searchParams] = useSearchParams()
  const id = articleId && /^[1-9]\d*$/.test(articleId) ? Number(articleId) : NaN
  const validId = Number.isSafeInteger(id)
  const article = useQuery({
    queryKey: ['article', id],
    queryFn: () => getArticle(id),
    enabled: validId,
  })
  const reprocess = useMutation({
    mutationFn: (_action: RecoveryAction) => reprocessArticle(id),
    onSuccess: (result) => {
      queryClient.setQueryData(['article', id], result.article)
      void queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
  })
  const backParams = new URLSearchParams()
  for (const key of ['tag_id', 'page']) {
    const value = searchParams.get(key)
    if (value) backParams.set(key, value)
  }
  const backQuery = backParams.toString()
  const backUrl = `/articles${backQuery ? `?${backQuery}` : ''}`
  const sourceUrl = article.data ? safeSourceUrl(article.data.source_url) : null
  const hasSummary = Boolean(article.data?.one_sentence_summary || article.data?.detailed_summary || article.data?.key_points?.length)
  const showFailureNotice = article.data && (
    article.data.fetch_status === 'failed'
    || ((article.data.status === 'failed' || article.data.status === 'partial_failed')
      && (!article.data.clean_content || !hasSummary))
  )
  const canContinueProcessing = Boolean(
    article.data
    && article.data.fetch_status === 'completed'
    && article.data.clean_content
    && (article.data.ai_status !== 'completed' || article.data.embedding_status !== 'completed')
    && (article.data.status === 'failed' || article.data.status === 'partial_failed'),
  )
  const canRefetch = Boolean(
    article.data
    && article.data.fetch_status === 'failed'
    && (article.data.status === 'failed' || article.data.status === 'partial_failed'),
  )
  const recoveryAction: RecoveryAction | null = canContinueProcessing ? 'continue' : canRefetch ? 'refetch' : null
  const activeRecoveryAction = reprocess.isPending ? reprocess.variables : recoveryAction

  return (
    <main className="min-h-svh bg-slate-100 px-5 py-5 text-slate-950 sm:py-14">
      <div className="mx-auto max-w-4xl">
        <nav className="flex flex-wrap gap-4 text-sm text-blue-700">
          <Link to={backUrl}>返回文章列表</Link>
          <Link to="/tags">查看标签</Link>
          <Link to="/agent">知识助手</Link>
        </nav>
        {!validId ? <p className="mt-8 rounded-2xl bg-white p-6 text-red-700" role="alert">文章编号无效。</p> : null}
        {validId && article.isPending ? <p className="mt-8 text-slate-600" role="status">正在加载文章…</p> : null}
        {validId && article.isError ? (
          <div className="mt-8 rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800" role="alert">
            <p>文章加载失败，记录可能不存在或服务暂时不可用。</p>
            <button className="mt-2 text-sm underline" type="button" onClick={() => void article.refetch()}>重新加载</button>
          </div>
        ) : null}
        {article.data ? (
          <>
            <header className="mt-7 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h1 className="min-w-0 flex-1 break-words text-2xl font-semibold sm:text-3xl">{article.data.title?.trim() || article.data.source_url}</h1>
                <ArticleStatusBadge status={article.data.status} />
              </div>
              <div className="mt-5 space-y-2 text-sm text-slate-600">
                <p className="break-all">来源：{sourceUrl ? <a className="text-blue-700 underline" href={sourceUrl} target="_blank" rel="noopener noreferrer">{article.data.source_url}</a> : article.data.source_url}</p>
                {article.data.source_name ? <p>来源名称：{article.data.source_name}</p> : null}
                {article.data.author ? <p>作者：{article.data.author}</p> : null}
                {article.data.published_at ? <p>发布时间：{new Date(article.data.published_at).toLocaleString()}</p> : null}
              </div>
            </header>
            {showFailureNotice ? (
              <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-amber-950" role="alert">
                <p className="font-semibold">{article.data.fetch_status === 'failed' ? '抓取失败' : article.data.status === 'failed' ? '处理失败' : '部分处理失败'}</p>
                <p className="mt-1 text-sm">文章内容尚不完整。下方可查看现有内容，页面后部列有各阶段状态和错误信息。</p>
              </div>
            ) : null}
            {recoveryAction ? (
              <div className="mt-5 flex flex-wrap items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5 text-sm">
                <button
                  className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                  type="button"
                  disabled={reprocess.isPending}
                  onClick={() => reprocess.mutate(recoveryAction)}
                >
                  {reprocess.isPending
                    ? activeRecoveryAction === 'continue' ? '正在继续处理…' : '正在重新抓取…'
                    : recoveryAction === 'continue' ? '继续处理' : '重新抓取'}
                </button>
                {recoveryAction === 'refetch' && !article.data.clean_content ? (
                  reprocess.isPending ? <span className="text-slate-400">请等待当前处理完成</span> : <Link className="font-medium text-blue-700 underline" to={`/articles/${article.data.id}/manual`}>粘贴正文手动导入</Link>
                ) : null}
              </div>
            ) : null}
            {reprocess.isSuccess ? (
              <p className={`mt-4 rounded-xl p-4 text-sm ${reprocess.data.article.status === 'completed' ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900'}`} role="status">
                {reprocess.data.article.status === 'completed'
                  ? reprocess.variables === 'continue' ? '后续处理已完成。' : '重新抓取与处理已完成。'
                  : `${reprocess.variables === 'continue' ? '继续处理' : '重新抓取'}后仍未完成：${reprocess.data.article.fetch_error ?? reprocess.data.article.ai_error ?? reprocess.data.article.embedding_error ?? '请查看下方处理状态。'}`}
              </p>
            ) : null}
            {reprocess.isError ? <p className="mt-4 rounded-xl bg-red-50 p-4 text-sm text-red-800" role="alert">{reprocess.variables === 'continue' ? '继续处理' : '重新抓取'}请求失败：{getArticleRequestErrorMessage(reprocess.error)}</p> : null}

            <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
              <h2 className="text-lg font-semibold">摘要</h2>
              {article.data.one_sentence_summary ? <p className="mt-4 whitespace-pre-wrap break-words text-sm leading-7">{article.data.one_sentence_summary}</p> : null}
              {article.data.detailed_summary ? <p className="mt-4 whitespace-pre-wrap break-words text-sm leading-7">{article.data.detailed_summary}</p> : null}
              {article.data.key_points?.length ? (
                <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-7">
                  {article.data.key_points.map((point, index) => <li className="break-words" key={index}>{point}</li>)}
                </ul>
              ) : null}
              {!article.data.one_sentence_summary && !article.data.detailed_summary && !article.data.key_points?.length ? <p className="mt-4 text-sm text-slate-500">暂无摘要。</p> : null}
            </section>

            <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
              <h2 className="text-lg font-semibold">原文</h2>
              {article.data.clean_content ? (
                <div className="mt-4 whitespace-pre-wrap break-words text-sm leading-7 text-slate-800">{article.data.clean_content}</div>
              ) : <p className="mt-4 text-sm text-slate-500">暂无原文内容。</p>}
            </section>

            <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
              <h2 className="text-lg font-semibold">标签</h2>
              <div className="mt-4 flex flex-wrap gap-2">
                {article.data.tags.map((tag) => <span className="rounded-full bg-blue-50 px-3 py-1 text-xs text-blue-800" key={tag}>{tag}</span>)}
                {article.data.tags.length === 0 ? <span className="text-sm text-slate-500">暂无标签</span> : null}
              </div>
            </section>

            <ProcessingStages article={article.data} />
          </>
        ) : null}
      </div>
    </main>
  )
}
