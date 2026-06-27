import { Terminal, Cpu, Radio, ShieldAlert, Sparkles, CheckCircle2 } from 'lucide-react'
import { useStore } from '../../store/useStore'

export default function AgentBus() {
  const { agentMessages } = useStore()

  const getIcon = (type: string) => {
    switch (type) {
      case 'regime': return <Radio size={14} color="var(--high-vol)" />
      case 'signal': return <Sparkles size={14} color="var(--accent)" />
      case 'gate': return <ShieldAlert size={14} color="var(--bear)" />
      default: return <Cpu size={14} color="var(--bull)" />
    }
  }

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="section-label" style={{ marginBottom: 0 }}>
          <Terminal size={15} color="var(--accent)" /> Real-Time Multi-Agent Execution Feed (Event Bus)
        </div>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {agentMessages.length} events logged
        </span>
      </div>

      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
        Live streaming asynchronous telemetry from Mamba state encoder, KAN spline network, LightGBM tree ensemble, and HMM gating supervisor.
      </p>

      <div style={{
        background: 'var(--surface-0)', border: '1px solid var(--border)', borderRadius: 10,
        padding: 16, maxHeight: 420, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10,
        fontFamily: 'var(--font-mono)', fontSize: '0.82rem'
      }}>
        {agentMessages.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px 0' }}>
            Listening for asynchronous agent messages on WebSocket bus...
          </div>
        ) : (
          agentMessages.map((msg) => (
            <div key={msg.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, paddingBottom: 10, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                {new Date(msg.timestamp).toLocaleTimeString()}
              </span>
              <div style={{ marginTop: 2 }}>{getIcon(msg.type)}</div>
              <div style={{ flex: 1 }}>
                <span style={{ color: 'var(--accent)', fontWeight: 700, marginRight: 8 }}>[{msg.model}]</span>
                <span style={{ color: 'var(--text-primary)' }}>{msg.message}</span>
                {msg.value !== undefined && (
                  <span style={{ marginLeft: 8, color: msg.value >= 0 ? 'var(--bull)' : 'var(--bear)', fontWeight: 700 }}>
                    ({msg.value >= 0 ? '+' : ''}{(msg.value * 100).toFixed(2)}%)
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
