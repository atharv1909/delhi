import { useEffect } from 'react'
import { useStore } from './store/useStore'
import { createLiveWebSocket } from './utils/api'
import Navbar from './components/layout/Navbar'
import InputPage from './pages/InputPage'
import ResultsPage from './pages/ResultsPage'

export default function App() {
  const { activeView, setLiveTick, pushAgentMessage } = useStore()

  useEffect(() => {
    const ws = createLiveWebSocket((msg: any) => {
      if (msg?.type === 'price_tick') {
        setLiveTick(msg.data)
      } else if (msg?.type === 'agent_message') {
        pushAgentMessage({
          type: 'info',
          model: msg.data?.model || 'System',
          message: msg.data?.message || '',
          value: msg.data?.value,
        })
      } else if (msg?.type === 'regime_update') {
        pushAgentMessage({
          type: 'regime',
          model: 'HMM Regime Detector',
          message: `Regime updated → ${msg.data?.state?.toUpperCase()} (confidence: ${(msg.data?.confidence * 100).toFixed(1)}%)`,
        })
      }
    })

    return () => ws.close()
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Navbar />
      <main style={{ flex: 1, padding: '0 24px 40px' }}>
        {activeView === 'input' ? <InputPage /> : <ResultsPage />}
      </main>
    </div>
  )
}
