import axios from 'axios'
import { useCallback, useEffect, useState } from 'react'

type HealthStatus = 'checking' | 'healthy' | 'unavailable'

interface HealthResponse {
  status: string
}

function App() {
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
        <button type="button" onClick={() => void checkHealth()} disabled={healthStatus === 'checking'}>
          重新检查
        </button>
      </section>
    </main>
  )
}

export default App
