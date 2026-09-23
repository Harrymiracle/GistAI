import { ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
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

function getSourceKey(source: AgentSource): string {
  if (source.source_type === 'knowledge_base' && source.article_id !== null) {
    return `knowledge_base:article:${source.article_id}`
  }

  if (source.source_type === 'web' && source.url) {
    return `web:url:${source.url}`
  }

  return `${source.source_type}:title:${source.title}`
}

function deduplicateSources(sources: AgentSource[]): AgentSource[] {
  const seenKeys = new Set<string>()

  return sources.filter((source) => {
    const key = getSourceKey(source)

    if (seenKeys.has(key)) {
      return false
    }

    seenKeys.add(key)
    return true
  })
}

export function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) {
    return null
  }

  const uniqueSources = deduplicateSources(sources)

  return (
    <section
      className="mt-5 border-t border-slate-200/80 pt-4"
      aria-label="资料来源"
    >
      <p className="mb-3 text-xs font-semibold tracking-wide text-slate-500 uppercase">
        Sources / 资料来源
      </p>
      <ul className="grid gap-2.5">
        {uniqueSources.map((source) => {
          const webUrl =
            source.source_type === 'web' ? getSafeWebUrl(source.url) : null
          const isKnowledgeBase = source.source_type === 'knowledge_base'
          const metadata = [source.source, source.published_at]
            .filter(Boolean)
            .join(' · ')

          return (
            <li
              className="rounded-xl border border-slate-200 bg-slate-50/80 px-3.5 py-3"
              key={getSourceKey(source)}
            >
              <div className="flex items-start gap-2.5">
                <Badge
                  className={
                    isKnowledgeBase
                      ? 'bg-blue-100 text-blue-800'
                      : 'bg-emerald-100 text-emerald-800'
                  }
                  variant="secondary"
                >
                  {isKnowledgeBase ? '知识库' : '网页'}
                </Badge>
                <div className="min-w-0">
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
                  {!isKnowledgeBase && metadata ? (
                    <p className="mt-1 text-xs text-slate-500">{metadata}</p>
                  ) : null}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
