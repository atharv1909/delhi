import type { RegimeState } from '../../store/useStore'

const REGIME_CONFIG = {
  bull: { label: 'BULL TRENDING', color: 'var(--bull)', dim: 'var(--bull-dim)', emoji: '📈', kelly: 'Full Kelly (1.0×)', desc: 'High returns, low vol. All experts active.' },
  bear: { label: 'BEAR TRENDING', color: 'var(--bear)', dim: 'var(--bear-dim)', emoji: '📉', kelly: 'Quarter Kelly (0.25×)', desc: 'Negative returns, rising vol. Defensive mode.' },
  high_vol: { label: 'HIGH VOLATILITY', color: 'var(--high-vol)', dim: 'var(--high-vol-dim)', emoji: '⚡', kelly: 'Zero Kelly (0.0×)', desc: 'Extreme volatility. Cash or hedges only.' },
  ranging: { label: 'RANGING', color: 'var(--ranging)', dim: 'var(--ranging-dim)', emoji: '↔', kelly: 'Half Kelly (0.5×)', desc: 'Near-zero returns. Mean-reversion favoured.' },
}

const GATE_CONFIG = {
  active: { label: 'GATE ACTIVE', color: 'var(--bull)', className: 'badge-active' },
  degraded: { label: 'GATE DEGRADED', color: 'var(--accent)', className: 'badge-degraded' },
  blocked: { label: 'GATE BLOCKED', color: 'var(--bear)', className: 'badge-blocked' },
}

interface Props { regime: RegimeState }

export default function RegimePanel({ regime }: Props) {
  const cfg = REGIME_CONFIG[regime.state] || REGIME_CONFIG.ranging
  const gate = GATE_CONFIG[regime.gate_status] || GATE_CONFIG.active

  return (
    <div className="card" style={{
      background: `linear-gradient(135deg, var(--surface-1) 0%, ${cfg.dim} 100%)`,
      border: `1px solid ${cfg.color}30`,
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Background glyph */}
      <div style={{
        position: 'absolute', right: 12, top: 12,
        fontSize: '4rem', opacity: 0.08, userSelect: 'none',
      }}>
        {cfg.emoji}
      </div>

      <div style={{ position: 'relative' }}>
        <div style={{ marginBottom: 12 }}>
          <span style={{ fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.12em', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            HMM REGIME
          </span>
        </div>

        {/* State badge */}
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 16,
        }}>
          <div style={{
            width: 10, height: 10, borderRadius: '50%',
            background: cfg.color,
            boxShadow: `0 0 12px ${cfg.color}80`,
            animation: regime.state === 'bull' ? 'regimePulse 2s infinite' :
                       regime.state === 'bear' ? 'regimePulseBear 2s infinite' : 'none',
          }} />
          <span style={{
            fontFamily: 'var(--font-mono)', fontWeight: 700,
            fontSize: '1.1rem', color: cfg.color, letterSpacing: '0.04em',
          }}>
            {cfg.label}
          </span>
        </div>

        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 16 }}>
          {cfg.desc}
        </p>

        {/* Metrics grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 2, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}>CONFIDENCE</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.2rem', fontWeight: 600, color: cfg.color }}>
              {(regime.confidence * 100).toFixed(1)}%
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 2, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}>MODEL IC</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.2rem', fontWeight: 600, color: regime.model_ic > 0.05 ? 'var(--bull)' : regime.model_ic > 0 ? 'var(--accent)' : 'var(--bear)' }}>
              {regime.model_ic.toFixed(4)}
            </div>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 4, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}>KELLY SIZING</div>
            <div style={{ fontSize: '0.82rem', color: cfg.color, fontWeight: 600 }}>{cfg.kelly}</div>
          </div>
        </div>

        {/* Transition probabilities */}
        {regime.transition_prob.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 6, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}>TRANSITION PROBS</div>
            {['Bull', 'Bear', 'HighVol', 'Ranging'].map((label, i) => {
              const prob = regime.transition_prob[i] || 0
              const colors = ['var(--bull)', 'var(--bear)', 'var(--high-vol)', 'var(--ranging)']
              return (
                <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', width: 52, fontFamily: 'var(--font-mono)' }}>{label}</span>
                  <div style={{ flex: 1, height: 4, background: 'var(--surface-3)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ width: `${prob * 100}%`, height: '100%', background: colors[i], borderRadius: 2 }} />
                  </div>
                  <span style={{ fontSize: '0.72rem', fontFamily: 'var(--font-mono)', color: colors[i], width: 38, textAlign: 'right' }}>
                    {(prob * 100).toFixed(1)}%
                  </span>
                </div>
              )
            })}
          </div>
        )}

        {/* Gate status */}
        <div className={`badge ${gate.className}`} style={{ fontSize: '0.72rem' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: gate.color, display: 'inline-block' }} />
          {gate.label}
        </div>
      </div>

      <style>{`
        @keyframes regimePulse { 0%,100%{box-shadow:0 0 12px var(--bull)80} 50%{box-shadow:0 0 20px var(--bull)} }
        @keyframes regimePulseBear { 0%,100%{box-shadow:0 0 12px var(--bear)80} 50%{box-shadow:0 0 20px var(--bear)} }
      `}</style>
    </div>
  )
}
