import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteTag, ignorePendingTag, listPendingTags, listTags, mergePendingTag, promotePendingTag } from '@/api/tags'
import type { ApiResponse } from '@/types/api'
import type { PendingTagRead, TagRead } from '@/types/tag'

async function refreshTagCaches(queryClient: QueryClient) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['tags'] }),
    queryClient.invalidateQueries({ queryKey: ['pending-tags'] }),
    queryClient.invalidateQueries({ queryKey: ['articles'] }),
    queryClient.invalidateQueries({ queryKey: ['article'] }),
  ])
}

function tagActionError(error: unknown): { message: string; refresh: boolean } {
  if (axios.isAxiosError<ApiResponse<unknown>>(error)) {
    if (error.response?.status === 404) return { message: '主题或目标已不存在，列表已更新，请重新选择。', refresh: true }
    if (error.response?.data?.code === 40905) return { message: '主题状态已变化，列表已更新，请重新选择。', refresh: true }
    if (error.response?.data?.code === 40906) return { message: '文章关联已变化，列表已更新，请重试。', refresh: true }
    if (error.response?.status === 409) return { message: '主题信息已变化，列表已更新，请重试。', refresh: true }
  }
  return { message: '操作失败，请稍后重试。', refresh: false }
}

type ActionFeedback = { onActionStart: () => void; onActionError: (error: unknown) => void }

function ActiveTagItem({ tag, onActionStart, onActionError }: { tag: TagRead } & ActionFeedback) {
  const queryClient = useQueryClient()
  const inFlight = useRef(false)
  const [busy, setBusy] = useState(false)
  const deletion = useMutation({ mutationFn: () => deleteTag(tag.id) })
  const remove = async () => {
    if (inFlight.current) return
    if (!window.confirm(`确定删除正式主题“${tag.name}”吗？\n将移除该主题及其与 ${tag.article_count} 篇文章的关联，不会删除文章。`)) return
    inFlight.current = true
    setBusy(true)
    onActionStart()
    try {
      await deletion.mutateAsync()
      await refreshTagCaches(queryClient)
    } catch (error) {
      onActionError(error)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="min-w-0">
        <Link className="font-medium text-blue-700 hover:underline" to={`/articles?tag_id=${tag.id}`}>{tag.name}</Link>
        <p className="mt-1 text-sm text-slate-500">{tag.article_count} 篇文章</p>
      </div>
      <button className="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60" type="button" disabled={busy} onClick={() => void remove()}>
        {busy ? '正在删除…' : '删除'}
      </button>
    </li>
  )
}

type PendingAction = { kind: 'promote' | 'ignore' } | { kind: 'merge'; targetId: number }

function PendingTagItem({ tag, activeTags, onActionStart, onActionError }: { tag: PendingTagRead; activeTags: TagRead[] } & ActionFeedback) {
  const queryClient = useQueryClient()
  const inFlight = useRef(false)
  const [busy, setBusy] = useState(false)
  const [targetId, setTargetId] = useState('')
  const target = activeTags.find((item) => item.id !== tag.id && String(item.id) === targetId)
  const action = useMutation({
    mutationFn: async (value: PendingAction) => {
      if (value.kind === 'promote') {
        await promotePendingTag(tag.id)
      } else if (value.kind === 'merge') {
        await mergePendingTag(tag.id, value.targetId)
      } else {
        await ignorePendingTag(tag.id)
      }
    },
  })
  const run = async (value: PendingAction) => {
    if (inFlight.current) return
    const count = tag.sources.length
    if (value.kind === 'merge' && (!target || target.id !== value.targetId)) return
    const confirmed = value.kind === 'promote'
      ? window.confirm(`确定将“${tag.name}”设为正式主题吗？\n来源文章：${count} 篇。`)
      : value.kind === 'ignore'
        ? window.confirm(`确定忽略“${tag.name}”吗？\n将移除这项建议及其与 ${count} 篇文章的关联，不会删除文章。`)
        : window.confirm(`确定将“${tag.name}”归入正式主题“${target?.name}”吗？\n来源文章：${count} 篇。`)
    if (!confirmed) return
    if (value.kind === 'merge' && (!target || target.id !== value.targetId)) return
    inFlight.current = true
    setBusy(true)
    onActionStart()
    try {
      await action.mutateAsync(value)
      await refreshTagCaches(queryClient)
    } catch (error) {
      onActionError(error)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }
  return (
    <li className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="break-words font-semibold">{tag.name}</h3>
      <p className="mt-1 text-sm text-slate-500">来源文章：{tag.sources.length} 篇</p>
      {tag.sources.length ? (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
          {tag.sources.map((source) => <li key={source.article_id}><Link className="break-words text-blue-700 hover:underline" to={`/articles/${source.article_id}`}>{source.title?.trim() || `文章 #${source.article_id}`}</Link></li>)}
        </ul>
      ) : <p className="mt-3 text-sm text-slate-500">暂无来源文章。</p>}
      <div className="mt-5 flex flex-wrap items-end gap-3 text-sm">
        <button className="rounded-lg bg-blue-600 px-3 py-2 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60" type="button" disabled={busy} onClick={() => void run({ kind: 'promote' })}>设为正式</button>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="block text-xs text-slate-600" htmlFor={`pending-target-${tag.id}`}>归入目标</label>
            <select id={`pending-target-${tag.id}`} className="mt-1 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm" value={target?.id ?? ''} disabled={busy || activeTags.length === 0} onChange={(event) => setTargetId(event.target.value)}>
              <option value="">选择正式主题</option>
              {activeTags.filter((item) => item.id !== tag.id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>
          <button className="rounded-lg border border-blue-200 px-3 py-2 font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60" type="button" disabled={busy || !target} onClick={() => { if (target) void run({ kind: 'merge', targetId: target.id }) }}>归入</button>
        </div>
        <button className="rounded-lg border border-slate-300 px-3 py-2 font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60" type="button" disabled={busy} onClick={() => void run({ kind: 'ignore' })}>忽略</button>
      </div>
      {activeTags.length === 0 ? <p className="mt-2 text-xs text-slate-500">暂无正式主题，不能归入。可先将建议设为正式主题。</p> : null}
    </li>
  )
}

export function TagListPage() {
  const queryClient = useQueryClient()
  const tags = useQuery({ queryKey: ['tags'], queryFn: listTags })
  const pendingTags = useQuery({ queryKey: ['pending-tags'], queryFn: listPendingTags })
  const [actionError, setActionError] = useState<string | null>(null)
  const [refreshingConflict, setRefreshingConflict] = useState(false)
  const onActionError = (error: unknown) => {
    const result = tagActionError(error)
    setActionError(result.message)
    if (result.refresh) {
      setRefreshingConflict(true)
      void Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: ['tags'] }),
        queryClient.invalidateQueries({ queryKey: ['pending-tags'] }),
      ]).then(() => setRefreshingConflict(false))
    }
  }
  return (
    <main className="min-h-svh bg-slate-100 px-5 py-5 text-slate-950 sm:py-14">
      <div className="mx-auto max-w-4xl">
        <nav className="flex flex-wrap gap-4 text-sm text-blue-700">
          <Link to="/">返回首页</Link>
          <Link to="/articles">我的文章</Link>
          <Link to="/agent">知识助手</Link>
        </nav>
        <h1 className="mt-7 text-3xl font-semibold">文章主题</h1>
        <p className="mt-2 text-sm text-slate-600">查看正式主题，整理待审建议。</p>
        {actionError ? <p className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">{actionError}</p> : null}
        {refreshingConflict ? <p className="mt-4 text-sm text-slate-600" role="status">正在更新主题列表…</p> : null}

        <section className="mt-8" aria-labelledby="active-tags-heading">
          <h2 className="text-xl font-semibold" id="active-tags-heading">正式主题</h2>
          {tags.isPending ? <p className="mt-4 text-slate-600" role="status">正在加载正式主题…</p> : null}
          {tags.isError ? <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800" role="alert"><p>正式主题加载失败，请稍后重试。</p><button className="mt-2 text-sm underline" type="button" onClick={() => void tags.refetch()}>重新加载</button></div> : null}
          {!refreshingConflict && !tags.isError && tags.data?.length === 0 ? <p className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 text-slate-600">还没有正式主题。</p> : null}
          {!refreshingConflict && !tags.isError && tags.data && tags.data.length > 0 ? <ul className="mt-4 space-y-3">{tags.data.map((tag) => <ActiveTagItem key={tag.id} tag={tag} onActionStart={() => setActionError(null)} onActionError={onActionError} />)}</ul> : null}
        </section>

        <section className="mt-10" aria-labelledby="pending-tags-heading">
          <h2 className="text-xl font-semibold" id="pending-tags-heading">待整理主题</h2>
          {pendingTags.isPending ? <p className="mt-4 text-slate-600" role="status">正在加载待整理主题…</p> : null}
          {pendingTags.isError ? <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800" role="alert"><p>待整理主题加载失败，请稍后重试。</p><button className="mt-2 text-sm underline" type="button" onClick={() => void pendingTags.refetch()}>重新加载</button></div> : null}
          {!refreshingConflict && !pendingTags.isError && pendingTags.data?.length === 0 ? <p className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 text-slate-600">没有待整理主题。</p> : null}
          {!refreshingConflict && !pendingTags.isError && pendingTags.data && pendingTags.data.length > 0 ? <ul className="mt-4 space-y-4">{pendingTags.data.map((tag) => <PendingTagItem key={tag.id} tag={tag} activeTags={tags.isError ? [] : tags.data ?? []} onActionStart={() => setActionError(null)} onActionError={onActionError} />)}</ul> : null}
        </section>
      </div>
    </main>
  )
}
