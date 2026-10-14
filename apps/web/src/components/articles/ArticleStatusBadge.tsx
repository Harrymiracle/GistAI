import type { ArticleProcessingStatus } from '@/types/article'

const statusDetails: Record<ArticleProcessingStatus, { label: string; className: string }> = {
  pending: { label: '待处理', className: 'bg-slate-100 text-slate-700' },
  processing: { label: '处理中', className: 'bg-blue-100 text-blue-800' },
  completed: { label: '已完成', className: 'bg-emerald-100 text-emerald-800' },
  partial_failed: { label: '部分失败', className: 'bg-amber-100 text-amber-800' },
  failed: { label: '失败', className: 'bg-red-100 text-red-800' },
}

export function ArticleStatusBadge({ status }: { status: ArticleProcessingStatus }) {
  const detail = statusDetails[status] ?? { label: status, className: 'bg-slate-100 text-slate-700' }
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${detail.className}`}>
      {detail.label}
    </span>
  )
}
