import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getArticle, getArticleRequestErrorMessage, getExistingArticleId, importManualArticle } from '@/api/articles'

export function ArticleManualImportPage() {
  const { articleId } = useParams()
  const id = articleId && /^[1-9]\d*$/.test(articleId) ? Number(articleId) : NaN
  const validId = Number.isSafeInteger(id)
  const queryClient = useQueryClient()
  const article = useQuery({
    queryKey: ['article', id],
    queryFn: () => getArticle(id),
    enabled: validId,
  })
  const [sourceUrl, setSourceUrl] = useState('')
  const [content, setContent] = useState('')
  const manualImport = useMutation({
    mutationFn: () => importManualArticle(id, { source_url: sourceUrl.trim(), content }),
    onSuccess: (result) => {
      queryClient.setQueryData(['article', result.id], result)
      void queryClient.invalidateQueries({ queryKey: ['articles'] })
    },
  })

  useEffect(() => {
    if (article.data) setSourceUrl(article.data.source_url)
  }, [article.data?.id, article.data?.source_url])

  const canRecover = article.data?.fetch_status === 'failed' && !article.data.clean_content
  const existingArticleId = getExistingArticleId(manualImport.error)
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canRecover || manualImport.isPending || !sourceUrl.trim() || !content.trim()) return
    manualImport.mutate()
  }

  return (
    <main className="min-h-svh bg-slate-100 px-5 py-8 text-slate-950 sm:py-14">
      <div className="mx-auto max-w-3xl">
        <nav className="flex flex-wrap gap-4 text-sm text-blue-700">
          <Link to={validId ? `/articles/${id}` : '/articles'}>返回文章详情</Link>
          <Link to="/articles">我的文章</Link>
        </nav>
        <h1 className="mt-7 text-3xl font-semibold">粘贴正文手动导入</h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">请填写正文所属的文章链接。系统无法自动核实正文与链接是否一致，请在提交前确认来源。</p>

        {!validId ? <p className="mt-7 text-red-700" role="alert">文章编号无效。</p> : null}
        {validId && article.isPending ? <p className="mt-7 text-slate-600" role="status">正在加载失败记录…</p> : null}
        {article.isError ? <p className="mt-7 text-red-700" role="alert">无法加载原文章记录：{getArticleRequestErrorMessage(article.error)}</p> : null}
        {article.data && !canRecover && !manualImport.isSuccess ? <p className="mt-7 rounded-2xl bg-amber-50 p-5 text-amber-900" role="alert">这条记录已有正文或未处于抓取失败状态，不能从此入口手动导入。</p> : null}

        {article.data && canRecover && !manualImport.isSuccess ? (
          <>
            <div className="mt-7 rounded-2xl border border-slate-200 bg-white p-5 text-sm">
              <p className="font-medium">原失败记录 #{article.data.id}</p>
              <p className="mt-2 break-all text-slate-600">原链接：{article.data.source_url}</p>
              {article.data.fetch_error ? <p className="mt-2 text-red-700">抓取失败原因：{article.data.fetch_error}</p> : null}
              <p className="mt-3 text-slate-600">链接不变时补全原记录；改成另一篇文章的链接时新建记录，原失败记录仍会保留。</p>
            </div>

            <form className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7" onSubmit={submit}>
              <label className="block text-sm font-medium" htmlFor="manual-article-url">文章链接</label>
              <input
                id="manual-article-url"
                className="mt-2 w-full rounded-xl border border-slate-300 px-3 py-3 text-sm outline-none focus:border-blue-500"
                type="url"
                required
                value={sourceUrl}
                disabled={manualImport.isPending}
                onChange={(event) => { setSourceUrl(event.target.value); manualImport.reset() }}
              />
              <p className="mt-2 break-all rounded-lg bg-blue-50 p-3 text-sm text-blue-900">本次正文将归属于：{sourceUrl.trim() || '请填写文章链接'}</p>
              <label className="mt-6 block text-sm font-medium" htmlFor="manual-article-content">文章正文</label>
              <textarea
                id="manual-article-content"
                className="mt-2 min-h-64 w-full rounded-xl border border-slate-300 px-3 py-3 text-sm leading-6 outline-none focus:border-blue-500"
                required
                value={content}
                disabled={manualImport.isPending}
                onChange={(event) => { setContent(event.target.value); manualImport.reset() }}
              />
              <p className="mt-2 text-xs text-slate-500">正文需满足后端最小长度要求；提交后将生成摘要、标签和向量。</p>
              <button className="mt-5 rounded-xl bg-blue-600 px-5 py-3 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60" type="submit" disabled={manualImport.isPending || !sourceUrl.trim() || !content.trim()}>
                {manualImport.isPending ? '正在处理…' : '确认链接并导入正文'}
              </button>
            </form>

            {manualImport.isError ? (
              <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800" role="alert">
                <p>手动导入失败：{getArticleRequestErrorMessage(manualImport.error)}</p>
                {existingArticleId ? <Link className="mt-2 inline-block font-medium underline" to={`/articles/${existingArticleId}`}>查看已有文章 #{existingArticleId}</Link> : null}
              </div>
            ) : null}
          </>
        ) : null}
        {manualImport.isSuccess ? (
          <div className={`mt-5 rounded-2xl p-5 text-sm ${manualImport.data.status === 'completed' ? 'bg-emerald-50 text-emerald-900' : 'bg-amber-50 text-amber-900'}`} role="status">
            <p className="font-medium">{manualImport.data.status === 'completed' ? '正文导入并处理完成' : '正文已提交，但部分处理阶段未完成'}</p>
            <p className="mt-1">文章 ID：{manualImport.data.id}{manualImport.data.id === id ? '（原记录）' : '（新记录，原失败记录保留）'}</p>
            <Link className="mt-2 inline-block font-medium underline" to={`/articles/${manualImport.data.id}`}>查看文章详情与处理状态</Link>
          </div>
        ) : null}
      </div>
    </main>
  )
}
