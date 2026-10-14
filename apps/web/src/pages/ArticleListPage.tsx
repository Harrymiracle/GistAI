import { useQuery } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { listArticles } from '@/api/articles'
import { listTags } from '@/api/tags'
import { ArticleStatusBadge } from '@/components/articles/ArticleStatusBadge'

function positiveInteger(value: string | null): number | undefined {
  if (!value || !/^[1-9]\d*$/.test(value)) return undefined
  const number = Number(value)
  return Number.isSafeInteger(number) ? number : undefined
}

function listUrl(page: number, tagId?: number): string {
  const params = new URLSearchParams()
  if (tagId !== undefined) params.set('tag_id', String(tagId))
  if (page > 1) params.set('page', String(page))
  const query = params.toString()
  return `/articles${query ? `?${query}` : ''}`
}

function pageTokens(page: number, totalPages: number): (number | 'ellipsis')[] {
  const nearby = new Set([1, totalPages])
  for (let number = Math.max(1, page - 2); number <= Math.min(totalPages, page + 2); number += 1) {
    nearby.add(number)
  }

  const pages = [...nearby].filter((number) => number >= 1).sort((a, b) => a - b)
  const tokens: (number | 'ellipsis')[] = []
  for (const number of pages) {
    const previous = tokens.length ? tokens[tokens.length - 1] : undefined
    if (typeof previous === 'number' && number - previous === 2) tokens.push(previous + 1)
    if (typeof previous === 'number' && number - previous > 2) tokens.push('ellipsis')
    tokens.push(number)
  }
  return tokens
}

export function ArticleListPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const page = positiveInteger(searchParams.get('page')) ?? 1
  const tagId = positiveInteger(searchParams.get('tag_id'))
  const [jumpInput, setJumpInput] = useState(String(page))
  const [jumpError, setJumpError] = useState(false)
  const articles = useQuery({
    queryKey: ['articles', page, tagId],
    queryFn: () => listArticles(page, tagId),
  })
  const tags = useQuery({
    queryKey: ['tags'],
    queryFn: listTags,
    enabled: tagId !== undefined,
  })
  const selectedTag = tags.data?.find((tag) => tag.id === tagId)
  const totalPages = articles.data ? Math.ceil(articles.data.total / articles.data.page_size) : 0
  const jumpPage = positiveInteger(jumpInput)
  const validJump = jumpPage !== undefined && jumpPage <= totalPages

  useEffect(() => {
    setJumpInput(String(page))
    setJumpError(false)
  }, [page, tagId])

  useEffect(() => {
    if (articles.data && page > Math.max(1, totalPages)) {
      void navigate(listUrl(1, tagId), { replace: true })
    }
  }, [articles.data, navigate, page, tagId, totalPages])

  const submitJump = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!validJump || jumpPage === undefined) {
      setJumpError(true)
      return
    }
    setJumpError(false)
    void navigate(listUrl(jumpPage, tagId))
  }

  return (
    <main className="min-h-svh bg-slate-100 px-5 py-5 text-slate-950 sm:py-14">
      <div className="mx-auto max-w-4xl">
        <nav className="flex flex-wrap gap-4 text-sm text-blue-700">
          <Link to="/">返回首页</Link>
          <Link to="/tags">查看标签</Link>
          <Link to="/articles/import">导入文章</Link>
          <Link to="/agent">知识助手</Link>
        </nav>
        <header className="mt-7">
          <h1 className="text-3xl font-semibold">我的文章</h1>
          <p className="mt-2 text-sm text-slate-600">
            {tagId === undefined ? '查看已导入的文章及其处理状态。' : `标签：${selectedTag?.name ?? `#${tagId}`}`}
          </p>
          {tagId !== undefined ? <Link className="mt-2 inline-block text-sm text-blue-700" to="/articles">查看全部文章</Link> : null}
        </header>

        {articles.isPending ? <p className="mt-8 text-slate-600" role="status">正在加载文章…</p> : null}
        {articles.isError ? (
          <div className="mt-8 rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800" role="alert">
            <p>文章加载失败，请稍后重试。</p>
            <button className="mt-2 text-sm underline" type="button" onClick={() => void articles.refetch()}>重新加载</button>
          </div>
        ) : null}
        {articles.data?.items.length === 0 && page <= Math.max(1, totalPages) ? (
          <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-8 text-slate-600">
            {tagId === undefined && page === 1 ? '还没有文章。' : '当前条件下没有文章。'}
            {page > 1 ? <Link className="mt-3 block text-sm text-blue-700" to={listUrl(1, tagId)}>返回第一页</Link> : null}
          </div>
        ) : null}
        {articles.data && articles.data.items.length > 0 ? (
          <>
            <p className="mt-7 text-sm text-slate-500">共 {articles.data.total} 篇 · 第 {page} 页</p>
            <ul className="mt-3 space-y-4">
              {articles.data.items.map((article) => (
                <li className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" key={article.id}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <Link className="min-w-0 flex-1 text-lg font-semibold text-blue-700 hover:underline break-words" to={`/articles/${article.id}${searchParams.toString() ? `?${searchParams}` : ''}`}>
                      {article.title?.trim() || article.source_url}
                    </Link>
                    <ArticleStatusBadge status={article.status} />
                  </div>
                  <p className="mt-2 break-all text-xs text-slate-500">{article.source_url}</p>
                  {article.one_sentence_summary ? <p className="mt-3 text-sm leading-6 text-slate-700">{article.one_sentence_summary}</p> : null}
                  <div className="mt-4 flex flex-wrap gap-2">
                    {article.tags.map((tag) => <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700" key={tag}>{tag}</span>)}
                    {article.tags.length === 0 ? <span className="text-xs text-slate-400">暂无标签</span> : null}
                  </div>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {articles.data && totalPages > 0 && page <= totalPages ? (
          <nav aria-label="文章分页" className="mt-6 flex flex-wrap items-center gap-2 text-sm">
            {page > 1 ? <Link className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-blue-700" to={listUrl(page - 1, tagId)}>上一页</Link> : <span className="rounded-lg border border-slate-200 px-3 py-2 text-slate-400" aria-disabled="true">上一页</span>}
            {pageTokens(page, totalPages).map((token, index) => token === 'ellipsis' ? (
              <span className="px-1 text-slate-500" aria-hidden="true" key={`ellipsis-${index}`}>…</span>
            ) : token === page ? (
              <span className="rounded-lg bg-blue-600 px-3 py-2 font-semibold text-white" aria-current="page" key={token}>{token}</span>
            ) : (
              <Link className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-blue-700" to={listUrl(token, tagId)} key={token}>{token}</Link>
            ))}
            {page < totalPages ? <Link className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-blue-700" to={listUrl(page + 1, tagId)}>下一页</Link> : <span className="rounded-lg border border-slate-200 px-3 py-2 text-slate-400" aria-disabled="true">下一页</span>}
            <form className="ml-0 flex flex-wrap items-center gap-2 sm:ml-auto" onSubmit={submitJump}>
              <label htmlFor="jump-page">跳至第</label>
              <input
                id="jump-page"
                className="w-16 rounded-lg border border-slate-300 bg-white px-2 py-2 text-center outline-none focus:border-blue-500"
                type="text"
                inputMode="numeric"
                aria-invalid={jumpError}
                aria-describedby={jumpError ? 'jump-page-error' : undefined}
                value={jumpInput}
                onChange={(event) => { setJumpInput(event.target.value); setJumpError(false) }}
              />
              <span>页 / 共 {totalPages} 页</span>
              <button className="rounded-lg bg-blue-600 px-3 py-2 font-medium text-white hover:bg-blue-700" type="submit">跳转</button>
              {jumpError ? <span className="w-full text-xs text-red-700" id="jump-page-error" role="alert">请输入 1 至 {totalPages} 的整数页码。</span> : null}
            </form>
          </nav>
        ) : null}
      </div>
    </main>
  )
}
