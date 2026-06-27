import { Activity, Cpu, Wifi, Radio } from 'lucide-react'
import { useStore } from '../../store/useStore'

const REGIME_COLORS: Record<string, string> = {
  bull: 'var(--bull)', bear: 'var(--bear)', high_vol: 'var(--high-vol)', ranging: 'var(--ranging)',
}

export default function Navbar() {
  const { activeView, setActiveView, result, liveTick, job } = useStore()
  const regime = result?.regime

  return (
    <nav style={{
      background: 'var(--surface-0)', borderBottom: '1px solid var(--border)',
      padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      height: 56, position: 'sticky', top: 0, zIndex: 100,
      backdropFilter: 'blur(12px)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 32, height: 32,
          background: 'linear-gradient(135deg, var(--accent), var(--bull))',
          borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Activity size={16} color="#06080C" strokeWidth={2.5} />
        </div>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '1.15rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
          InvestEasy
        </span>
        <span style={{
          fontSize: '0.65rem', color: 'var(--text-muted)', background: 'var(--surface-2)',
          padding: '2px 8px', borderRadius: 4, fontFamily: 'var(--font-mono)', border: '1px solid var(--border)',
        }}>
          v1.0 · NSE/BSE
        </span>
      </div>

      <div style={{ display: 'flex', gap: 4 }}>
        {([
          { key: 'input', label: 'Analyze Portfolio', disabled: false },
          { key: 'results', label: 'Results', disabled: !result },
          { key: 'live', label: '◉ Live', disabled: false },
        ] as const).map(({ key, label, disabled }) => (
          <button key={key} onClick={() => !disabled && setActiveView(key)}
            style={{
              background: activeView === key ? 'var(--surface-2)' : 'transparent',
              border: activeView === key ? '1px solid var(--border)' : '1px solid transparent',
              color: activeView === key ? 'var(--text-primary)' : 'var(--text-muted)',
              padding: '5px 14px', borderRadius: 6,
              cursor: disabled ? 'not-allowed' : 'pointer',
              fontSize: '0.83rem', fontWeight: 500, fontFamily: 'var(--font-body)',
              opacity: disabled ? 0.4 : 1, transition: 'all 0.15s',
            }}>
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        {liveTick && (
          <div style={{ display: 'flex', gap: 14, fontSize: '0.78rem', fontFamily: 'var(--font-mono)' }}>
            <span style={{ color: 'var(--text-muted)' }}>
              NIFTY <span style={{ color: 'var(--text-primary)' }}>
                {liveTick.nifty_level?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </span>
            </span>
            <span style={{ color: 'var(--text-muted)' }}>
              VIX <span style={{ color: (liveTick.india_vix || 0) > 20 ? 'var(--high-vol)' : 'var(--text-primary)' }}>
                {liveTick.india_vix?.toFixed(2)}
              </span>
            </span>
          </div>
        )}

        {regime && (
          <div className={`badge badge-${regime.state === 'high_vol' ? 'high-vol' : regime.state}`}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: REGIME_COLORS[regime.state], display: 'inline-block' }} />
            {regime.state.toUpperCase().replace('_', ' ')}
          </div>
        )}

        {job.status === 'running' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', color: 'var(--accent)' }}>
            <Cpu size={13} className="spin" /> {job.progress}%
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.72rem', color: 'var(--bull)' }}>
          <Wifi size={12} />
          <span style={{ fontFamily: 'var(--font-mono)' }}>LIVE</span>
        </div>
      </div>
    </nav>
  )
}
