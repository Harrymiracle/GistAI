import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listTags } from '@/api/tags'

export function TagListPage() {
  const tags = useQuery({ queryKey: ['tags'], queryFn: listTags })

  return (
    <main className="min-h-svh bg-slate-100 px-5 py-5 text-slate-950 sm:py-14">
      <div className="mx-auto max-w-4xl">
        <nav className="flex flex-wrap gap-4 text-sm text-blue-700">
          <Link to="/">返回首页</Link>
          <Link to="/articles">我的文章</Link>
          <Link to="/agent">知识助手</Link>
        </nav>
        <h1 className="mt-7 text-3xl font-semibold">文章标签</h1>
        <p className="mt-2 text-sm text-slate-600">选择标签，查看关联的文章。</p>

        {tags.isPending ? <p className="mt-8 text-slate-600" role="status">正在加载标签…</p> : null}
        {tags.isError ? (
          <div className="mt-8 rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800" role="alert">
            <p>标签加载失败，请稍后重试。</p>
            <button className="mt-2 text-sm underline" type="button" onClick={() => void tags.refetch()}>重新加载</button>
          </div>
        ) : null}
        {tags.data?.length === 0 ? <p className="mt-8 rounded-2xl border border-slate-200 bg-white p-8 text-slate-600">还没有标签。</p> : null}
        {tags.data && tags.data.length > 0 ? (
          <ul className="mt-8 flex flex-wrap gap-3">
            {tags.data.map((tag) => (
              <li key={tag.id}>
                <Link className="inline-flex rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-blue-700 shadow-sm hover:border-blue-300" to={`/articles?tag_id=${tag.id}`}>
                  {tag.name}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </main>
  )
}
