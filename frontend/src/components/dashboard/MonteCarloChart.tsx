import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip } from 'recharts'
import { Activity, ShieldCheck, TrendingUp, Info } from 'lucide-react'
import { formatINR, formatPct } from '../../utils/api'
import type { RiskMetrics } from '../../store/useStore'

interface MonteCarloChartProps {
  risk: RiskMetrics
  goal: any
  large?: boolean
}

export default function MonteCarloChart({ risk, goal, large }: MonteCarloChartProps) {
  const p5 = risk.mc_percentile_5 || []
  const p50 = risk.mc_percentile_50 || []
  const p95 = risk.mc_percentile_95 || []
  const days = risk.mc_horizon_days || 252

  // Downsample for rendering performance
  const step = Math.max(1, Math.floor(p50.length / (large ? 60 : 30)))
  const chartData = []

  for (let i = 0; i < p50.length; i += step) {
    chartData.push({
      day: `Day ${i}`,
      p5: Math.round(p5[i] || 0),
      p50: Math.round(p50[i] || 0),
      p95: Math.round(p95[i] || 0),
    })
  }

  const initialVal = p50[0] || goal?.capital_inr || 500000
  const finalMedian = p50[p50.length - 1] || initialVal
  const finalWorst = p5[p5.length - 1] || initialVal

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div className="section-label" style={{ marginBottom: 4 }}>
            <Activity size={15} color="var(--accent)" /> 10,000 Path Monte Carlo CVaR Simulation
          </div>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            Simulating portfolio returns across 10,000 empirical regime-switched market paths over {days} trading days.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, fontSize: '0.78rem', fontFamily: 'var(--font-mono)' }}>
          <div>
            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.68rem' }}>Median (P50)</span>
            <span style={{ fontWeight: 700, color: 'var(--bull)' }}>{formatINR(finalMedian)}</span>
          </div>
          <div>
            <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '0.68rem' }}>Worst 5% (P05)</span>
            <span style={{ fontWeight: 700, color: 'var(--bear)' }}>{formatINR(finalWorst)}</span>
          </div>
        </div>
      </div>

      <div style={{ height: large ? 360 : 230, width: '100%', marginTop: 8 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
            <defs>
              <linearGradient id="gradP95" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--bull)" stopOpacity={0.2} />
                <stop offset="95%" stopColor="var(--bull)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradP5" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--bear)" stopOpacity={0.2} />
                <stop offset="95%" stopColor="var(--bear)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="day" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
            <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }} tickFormatter={(v) => formatINR(v)} width={65} />
            <Tooltip
              contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              formatter={(val: number, name: string) => [formatINR(val), name === 'p95' ? 'Best 5% (P95)' : name === 'p50' ? 'Expected (P50)' : 'CVaR Worst 5% (P05)']}
            />
            <Area type="monotone" dataKey="p95" stroke="var(--bull)" fillOpacity={1} fill="url(#gradP95)" strokeWidth={1.5} name="p95" />
            <Area type="monotone" dataKey="p50" stroke="var(--accent)" fill="none" strokeWidth={2.5} name="p50" />
            <Area type="monotone" dataKey="p5" stroke="var(--bear)" fillOpacity={1} fill="url(#gradP5)" strokeWidth={1.5} strokeDasharray="4 4" name="p5" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: '0.72rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border)', paddingTop: 12 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 3, background: 'var(--bull)', display: 'inline-block' }} /> P95 Optimistic</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 3, background: 'var(--accent)', display: 'inline-block' }} /> P50 Expected</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 3, background: 'var(--bear)', display: 'inline-block', borderBottom: '1px dashed var(--bear)' }} /> P05 Tail Risk (CVaR)</span>
      </div>
    </div>
  )
}
