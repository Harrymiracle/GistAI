import { ExternalLink } from 'lucide-react'
import type { AgentSource } from '@/types/agent'

interface SourceListProps {
  sources: AgentSource[]
}

function getSafeWebUrl(url: string | null): string | null {
  if (!url) {
    return null
  }

  try {
    const parsedUrl = new URL(url)

    return parsedUrl.protocol === 'http:' || parsedUrl.protocol === 'https:'
      ? url
      : null
  } catch {
    return null
  }
}

export function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) {
    return null
  }

  return (
    <section
      className="mt-5 border-t border-slate-200/80 pt-4"
      aria-label="资料来源"
    >
      <p className="mb-3 text-xs font-semibold tracking-wide text-slate-500 uppercase">
        Sources / 资料来源
      </p>
      <ul className="grid gap-2.5">
        {sources.map((source, index) => {
          const webUrl =
            source.source_type === 'web' ? getSafeWebUrl(source.url) : null
          const metadata =
            source.source_type === 'knowledge_base'
              ? '个人知识库'
              : [source.source, source.published_at]
                  .filter(Boolean)
                  .join(' · ') || '外部网页'

          return (
            <li
              className="rounded-xl border border-slate-200 bg-slate-50/80 px-3.5 py-3"
              key={`${source.source_type}-${source.article_id ?? source.url ?? source.title}-${source.chunk_id ?? index}`}
            >
              {webUrl ? (
                <a
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-700 underline-offset-4 hover:underline"
                  href={webUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {source.title}
                  <ExternalLink className="size-3.5" aria-hidden="true" />
                </a>
              ) : (
                <p className="text-sm font-medium text-slate-800">
                  {source.title}
                </p>
              )}
              <p className="mt-1 text-xs text-slate-500">{metadata}</p>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
