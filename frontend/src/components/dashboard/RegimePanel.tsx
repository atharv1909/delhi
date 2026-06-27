import { ShieldAlert, ShieldCheck, Activity, Compass } from 'lucide-react'
import { formatPct } from '../../utils/api'

interface RegimePanelProps {
  regime: {
    state: string
    confidence: number
    kelly_factor: number
    model_ic: number
    gate_status: string
    transition_prob?: number[]
  }
}

const REGIME_DESC: Record<string, { label: string; desc: string; color: string; bg: string }> = {
  bull: { label: 'Bull Expansion', desc: 'Upward momentum confirmed. 100% Kelly allocation enabled.', color: 'var(--bull)', bg: 'regime-bull' },
  bear: { label: 'Bearish Contraction', desc: 'Downward drift detected. Capital preservation mode (25% Kelly cap).', color: 'var(--bear)', bg: 'regime-bear' },
  high_vol: { label: 'High Volatility Regime', desc: 'VIX spike / erratic swings. Defensive posture active (0% equity expansion).', color: 'var(--high-vol)', bg: 'regime-high-vol' },
  ranging: { label: 'Ranging Consolidation', desc: 'Sideways market channel. Mean-reverting alpha weighting (50% Kelly factor).', color: 'var(--ranging)', bg: 'regime-ranging' },
}

export default function RegimePanel({ regime }: RegimePanelProps) {
  const stateKey = (regime.state || 'ranging').toLowerCase()
  const info = REGIME_DESC[stateKey] || REGIME_DESC.ranging

  return (
    <div className={`card ${info.bg}`} style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minHeight: 180 }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Compass size={18} color={info.color} />
            <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-secondary)' }}>
              Market Regime Gating
            </span>
          </div>
          <span className={`badge badge-${stateKey === 'high_vol' ? 'high-vol' : stateKey}`}>
            ● {info.label}
          </span>
        </div>

        <p style={{ fontSize: '0.88rem', color: 'var(--text-primary)', lineHeight: 1.5, marginBottom: 16 }}>
          {info.desc}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div>
          <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>HMM Confidence</span>
          <span style={{ fontSize: '1.05rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
            {formatPct(regime.confidence || 0.75, 1)}
          </span>
        </div>

        <div>
          <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Kelly Sizing Cap</span>
          <span style={{ fontSize: '1.05rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: info.color }}>
            {formatPct(regime.kelly_factor || 0.5, 0)}
          </span>
        </div>

        <div>
          <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Model IC Gate</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {regime.gate_status === 'active' ? <ShieldCheck size={14} color="var(--bull)" /> : <ShieldAlert size={14} color="var(--high-vol)" />}
            <span style={{ fontSize: '0.9rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: regime.gate_status === 'active' ? 'var(--bull)' : 'var(--high-vol)' }}>
              {regime.gate_status?.toUpperCase() || 'ACTIVE'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
