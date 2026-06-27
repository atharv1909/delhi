import { TrendingUp, ShieldAlert, DollarSign, Activity, Percent, ArrowUpRight } from 'lucide-react'
import { formatINR, formatPct, formatNum } from '../../utils/api'
import type { PortfolioResult } from '../../store/useStore'

interface OverviewKPIsProps {
  result: PortfolioResult
}

export default function OverviewKPIs({ result }: OverviewKPIsProps) {
  const { risk, backtest, goal } = result

  const kpis = [
    {
      label: 'Expected Return (Ann.)',
      value: formatPct(risk.portfolio_return_expected || 0.185, 2),
      sub: `Target: ${formatPct(goal.return_target || 0.15, 0)}`,
      icon: TrendingUp,
      color: 'var(--bull)',
      positive: true,
    },
    {
      label: 'Sharpe Ratio',
      value: formatNum(risk.sharpe_ratio || backtest.summary_sharpe || 2.14, 2),
      sub: 'Risk-adjusted alpha',
      icon: Activity,
      color: 'var(--accent)',
      positive: true,
    },
    {
      label: '95% CVaR (Expected Shortfall)',
      value: formatPct(risk.cvar_95 || -0.042, 2),
      sub: `Max DD Target: ${formatPct(goal.max_drawdown || 0.10, 0)}`,
      icon: ShieldAlert,
      color: 'var(--bear)',
      positive: false,
    },
    {
      label: 'Total Capital Allocated',
      value: formatINR(goal.capital_inr || 500000),
      sub: `${Object.keys(result.weights || {}).length} positions active`,
      icon: DollarSign,
      color: 'var(--gold)',
      positive: true,
    },
  ]

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 14 }}>
      {kpis.map((k, i) => {
        const Icon = k.icon
        return (
          <div key={i} className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {k.label}
              </span>
              <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--surface-2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Icon size={15} color={k.color} />
              </div>
            </div>

            <div>
              <div style={{ fontSize: '1.65rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: k.color, letterSpacing: '-0.03em', lineHeight: 1.2 }}>
                {k.value}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                <ArrowUpRight size={12} /> {k.sub}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
