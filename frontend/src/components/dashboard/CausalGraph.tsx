import { Network, ArrowRight, ShieldCheck, Zap } from 'lucide-react'
import { formatPct } from '../../utils/api'

interface CausalGraphProps {
  signals: any[]
  weights: Record<string, number>
}

export default function CausalGraph({ signals, weights }: CausalGraphProps) {
  const activeTickers = Object.keys(weights || {}).filter(t => (weights[t] || 0) > 0.02).slice(0, 6)

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <div className="section-label" style={{ marginBottom: 4 }}>
          <Network size={15} color="var(--accent)" /> Causal Alpha Graph & Regime Flow Architecture
        </div>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          Visualizing how macroeconomic feature variables propagate through Mamba + KAN + LightGBM models into final optimal portfolio allocation.
        </p>
      </div>

      {/* Visual Flow Representation */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1.2fr auto 1fr auto 1fr', gap: 12, alignItems: 'center', background: 'var(--surface-0)', padding: 20, borderRadius: 12, overflowX: 'auto', minWidth: 700 }}>
        {/* Layer 1: Inputs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', textAlign: 'center' }}>1. Macro & OHLCV</div>
          {['NSE Price Ticks', 'India VIX Spike', 'FII Net Flows', 'US 10Y Yield'].map((inp, i) => (
            <div key={i} style={{ background: 'var(--surface-2)', padding: '8px 12px', borderRadius: 6, fontSize: '0.78rem', fontFamily: 'var(--font-mono)', border: '1px solid var(--border)', textAlign: 'center' }}>
              {inp}
            </div>
          ))}
        </div>

        <ArrowRight size={18} color="var(--text-muted)" />

        {/* Layer 2: Models */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', textAlign: 'center' }}>2. Alpha Inference</div>
          <div style={{ background: 'var(--accent-dim)', border: '1px solid rgba(99,179,237,0.3)', padding: '8px 12px', borderRadius: 6, fontSize: '0.78rem', color: 'var(--accent)', fontWeight: 700, textAlign: 'center' }}>
            ⚡ LightGBM Tree
          </div>
          <div style={{ background: 'var(--bull-dim)', border: '1px solid rgba(72,187,120,0.3)', padding: '8px 12px', borderRadius: 6, fontSize: '0.78rem', color: 'var(--bull)', fontWeight: 700, textAlign: 'center' }}>
            〰️ KAN Spline
          </div>
          <div style={{ background: 'var(--high-vol-dim)', border: '1px solid rgba(246,173,85,0.3)', padding: '8px 12px', borderRadius: 6, fontSize: '0.78rem', color: 'var(--high-vol)', fontWeight: 700, textAlign: 'center' }}>
            ⏱️ PatchTST Transformer
          </div>
        </div>

        <ArrowRight size={18} color="var(--text-muted)" />

        {/* Layer 3: Regime Gate */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', textAlign: 'center' }}>3. MoE & HMM Gate</div>
          <div style={{ background: 'linear-gradient(135deg, var(--surface-2), var(--surface-3))', border: '1px solid var(--border-accent)', padding: '16px 12px', borderRadius: 8, textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 800, color: 'var(--text-primary)' }}>Soft MoE Gating</span>
            <span style={{ fontSize: '0.72rem', color: 'var(--bull)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
              <ShieldCheck size={12} /> Kelly Cap Efficacy
            </span>
          </div>
        </div>

        <ArrowRight size={18} color="var(--text-muted)" />

        {/* Layer 4: Weights */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', textAlign: 'center' }}>4. Optimal Weights</div>
          {activeTickers.length === 0 ? (
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center' }}>Pending...</div>
          ) : (
            activeTickers.map(t => (
              <div key={t} style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--surface-1)', padding: '6px 10px', borderRadius: 6, fontSize: '0.78rem', fontFamily: 'var(--font-mono)' }}>
                <span style={{ fontWeight: 700 }}>{t}</span>
                <span style={{ color: 'var(--bull)' }}>{formatPct(weights[t] || 0, 1)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
