import axios from 'axios'
import { useCallback, useEffect, useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import { AgentChatPage } from './pages/AgentChatPage'
import { ArticleDetailPage } from './pages/ArticleDetailPage'
import { ArticleImportPage } from './pages/ArticleImportPage'
import { ArticleListPage } from './pages/ArticleListPage'
import { ArticleManualImportPage } from './pages/ArticleManualImportPage'
import { TagListPage } from './pages/TagListPage'
import { useAgentChat } from './hooks/useAgentChat'

type HealthStatus = 'checking' | 'healthy' | 'unavailable'

interface HealthResponse {
  status: string
}

function HomePage() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus>('checking')

  const checkHealth = useCallback(async () => {
    setHealthStatus('checking')

    try {
      const response = await axios.get<HealthResponse>('/health')
      setHealthStatus(response.data.status === 'ok' ? 'healthy' : 'unavailable')
    } catch {
      setHealthStatus('unavailable')
    }
  }, [])

  useEffect(() => {
    void checkHealth()
  }, [checkHealth])

  const statusText = {
    checking: '正在检查后端连接…',
    healthy: 'FastAPI 服务连接正常',
    unavailable: '暂时无法连接 FastAPI 服务',
  }[healthStatus]

  return (
    <main className="app-shell">
      <section className="status-card">
        <p className="eyebrow">AI 阅读助手</p>
        <h1>GistAI</h1>
        <p className={`status status--${healthStatus}`}>{statusText}</p>
        <div className="home-actions">
          <Link className="primary-link" to="/articles/import">导入文章</Link>
          <Link className="primary-link" to="/articles">我的文章</Link>
          <Link className="primary-link" to="/tags">文章标签</Link>
          <Link className="primary-link" to="/agent">打开知识助手</Link>
          <button className="health-button" type="button" onClick={() => void checkHealth()} disabled={healthStatus === 'checking'}>
            重新检查
          </button>
        </div>
      </section>
    </main>
  )
}

function App() {
  const agentChat = useAgentChat()

  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/articles/import" element={<ArticleImportPage />} />
      <Route path="/articles" element={<ArticleListPage />} />
      <Route path="/articles/:articleId" element={<ArticleDetailPage />} />
      <Route path="/articles/:articleId/manual" element={<ArticleManualImportPage />} />
      <Route path="/tags" element={<TagListPage />} />
      <Route path="/agent" element={<AgentChatPage chat={agentChat} />} />
    </Routes>
  )
}

export default App
