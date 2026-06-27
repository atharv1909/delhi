import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { PieChart as PieIcon, DollarSign } from 'lucide-react'
import { formatINR, formatPct } from '../../utils/api'

interface PortfolioWeightsProps {
  weights: Record<string, number>
  commands: any[]
  goal: any
  large?: boolean
}

const COLORS = [
  '#63B3ED', '#48BB78', '#F6AD55', '#B794F4', '#FC5C7D',
  '#4FD1C5', '#F6E05E', '#A0AEC0', '#ED8936', '#9F7AEA',
]

export default function PortfolioWeights({ weights, goal, large }: PortfolioWeightsProps) {
  const entries = Object.entries(weights || {})
    .filter(([_, w]) => w > 0.01)
    .sort((a, b) => b[1] - a[1])

  const totalCapital = goal?.capital_inr || 500000

  const chartData = entries.map(([ticker, w]) => ({
    name: ticker,
    value: Number((w * 100).toFixed(1)),
    amount: w * totalCapital,
  }))

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="section-label" style={{ marginBottom: 0 }}>
          <PieIcon size={15} color="var(--accent)" /> Mean-CVaR Optimal Allocation
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{entries.length} assets selected</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: large ? '1fr 1.2fr' : '1fr', gap: 20, alignItems: 'center' }}>
        <div style={{ height: large ? 280 : 200, width: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={large ? 65 : 50}
                outerRadius={large ? 95 : 75}
                paddingAngle={3}
                dataKey="value"
              >
                {chartData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
                formatter={(val: number, name: string, entry: any) => [`${val}% (${formatINR(entry.payload.amount)})`, name]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: large ? 300 : 200, overflowY: 'auto', paddingRight: 6 }}>
          {chartData.map((d, i) => (
            <div key={d.name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', background: 'var(--surface-0)', borderRadius: 6, fontSize: '0.82rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS[i % COLORS.length] }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{d.name}</span>
              </div>
              <div style={{ display: 'flex', gap: 12, fontFamily: 'var(--font-mono)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{formatINR(d.amount)}</span>
                <span style={{ fontWeight: 700, width: 45, textAlign: 'right' }}>{d.value}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
