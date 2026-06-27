import { ShoppingCart, CheckCircle, AlertCircle, ArrowRight } from 'lucide-react'
import { formatINR } from '../../utils/api'
import type { TradeCommand } from '../../store/useStore'

interface TradeCommandsProps {
  commands: TradeCommand[]
}

export default function TradeCommands({ commands }: TradeCommandsProps) {
  const list = commands || []
  const buyCount = list.filter(c => c.action === 'BUY').length
  const sellCount = list.filter(c => c.action === 'SELL').length

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="section-label" style={{ marginBottom: 0 }}>
          <ShoppingCart size={15} color="var(--bull)" /> SEBI-Compliant Executable Trade Commands
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <span className="badge badge-bull">{buyCount} BUY</span>
          <span className="badge badge-bear">{sellCount} SELL</span>
        </div>
      </div>

      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
        Integer share quantities rounded to exchange lot sizes. Demat rebalancing ready for broker gateway execution.
      </p>

      {list.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.88rem' }}>
          No rebalancing trades required — existing allocation is within threshold.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Ticker</th>
                <th style={{ textAlign: 'center' }}>Action</th>
                <th style={{ textAlign: 'right' }}>Shares</th>
                <th style={{ textAlign: 'right' }}>Est. Amount</th>
                <th style={{ textAlign: 'center' }}>Lot Compliant</th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.ticker}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.88rem' }}>{c.ticker}</td>
                  <td style={{ textAlign: 'center' }}>
                    <span style={{
                      padding: '4px 10px', borderRadius: 6, fontSize: '0.72rem', fontWeight: 800, fontFamily: 'var(--font-mono)',
                      background: c.action === 'BUY' ? 'var(--bull-dim)' : c.action === 'SELL' ? 'var(--bear-dim)' : 'var(--surface-2)',
                      color: c.action === 'BUY' ? 'var(--bull)' : c.action === 'SELL' ? 'var(--bear)' : 'var(--text-secondary)',
                      border: `1px solid ${c.action === 'BUY' ? 'rgba(72,187,120,0.3)' : c.action === 'SELL' ? 'rgba(252,92,125,0.3)' : 'transparent'}`
                    }}>
                      {c.action}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                    {c.quantity?.toLocaleString('en-IN')}
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                    {formatINR(c.amount_inr || 0)}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {c.lot_compliant ? (
                      <span style={{ color: 'var(--bull)', display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.75rem' }}>
                        <CheckCircle size={13} /> Yes
                      </span>
                    ) : (
                      <span style={{ color: 'var(--high-vol)', display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.75rem' }}>
                        <AlertCircle size={13} /> Fractional
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', maxWidth: 280 }}>
                    {c.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
