import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts'
import { Sparkles, HelpCircle, Layers } from 'lucide-react'
import type { AlphaSignal } from '../../store/useStore'

interface ShapWaterfallProps {
  signal: AlphaSignal
}

export default function ShapWaterfall({ signal }: ShapWaterfallProps) {
  const shapData = signal?.shap_data || {}
  const entries = Object.entries(shapData).slice(0, 8)

  const chartData = entries.map(([feature, val]) => ({
    feature: feature.replace(/_/g, ' ').toUpperCase(),
    value: Number((val * 100).toFixed(3)),
  }))

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <div className="section-label" style={{ marginBottom: 4 }}>
          <Sparkles size={14} color="var(--accent)" /> SHAP Feature Attribution — {signal.ticker}
        </div>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
          Game-theoretic SHAP values breaking down drivers behind {signal.ticker}'s {(signal.final_alpha * 100).toFixed(2)}% expected alpha prediction.
        </p>
      </div>

      {chartData.length === 0 ? (
        <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No SHAP attribution data available for this ticker.
        </div>
      ) : (
        <div style={{ height: 240, width: '100%', marginTop: 10 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart layout="vertical" data={chartData} margin={{ top: 5, right: 20, left: 80, bottom: 5 }}>
              <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
              <YAxis dataKey="feature" type="category" tick={{ fill: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font-mono)' }} width={80} />
              <Tooltip
                contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--text-primary)' }}
                formatter={(val: number) => [`${val > 0 ? '+' : ''}${val}%`, 'SHAP Impact']}
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.value >= 0 ? 'var(--bull)' : 'var(--bear)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
