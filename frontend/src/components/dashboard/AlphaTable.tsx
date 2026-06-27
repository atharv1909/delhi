import { useState } from 'react'
import { ArrowUpDown, HelpCircle, Layers, Award } from 'lucide-react'
import { useStore } from '../../store/useStore'
import type { AlphaSignal } from '../../store/useStore'

interface AlphaTableProps {
  signals: AlphaSignal[]
}

export default function AlphaTable({ signals }: AlphaTableProps) {
  const { selectedSignal, setSelectedSignal } = useStore()
  const [sortField, setSortField] = useState<keyof AlphaSignal>('final_alpha')
  const [sortAsc, setSortAsc] = useState(false)

  const handleSort = (field: keyof AlphaSignal) => {
    if (sortField === field) setSortAsc(!sortAsc)
    else { setSortField(field); setSortAsc(false) }
  }

  const sorted = [...(signals || [])].sort((a, b) => {
    const valA = Number(a[sortField] || 0)
    const valB = Number(b[sortField] || 0)
    return sortAsc ? valA - valB : valB - valA
  })

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="section-label" style={{ marginBottom: 0 }}>
          <Layers size={15} color="var(--accent)" /> Multi-Model Alpha Signals (MoE Ensemble)
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Click a row to inspect SHAP feature attribution</span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="tbl">
          <thead>
            <tr>
              <th onClick={() => handleSort('ticker')} style={{ cursor: 'pointer' }}>Ticker <ArrowUpDown size={11} /></th>
              <th onClick={() => handleSort('lgbm_alpha')} style={{ cursor: 'pointer', textAlign: 'right' }}>LightGBM <ArrowUpDown size={11} /></th>
              <th onClick={() => handleSort('kan_alpha')} style={{ cursor: 'pointer', textAlign: 'right' }}>KAN Spline <ArrowUpDown size={11} /></th>
              <th onClick={() => handleSort('patchtst_alpha')} style={{ cursor: 'pointer', textAlign: 'right' }}>PatchTST <ArrowUpDown size={11} /></th>
              <th onClick={() => handleSort('il_alpha')} style={{ cursor: 'pointer', textAlign: 'right' }}>Imitation RL <ArrowUpDown size={11} /></th>
              <th onClick={() => handleSort('final_alpha')} style={{ cursor: 'pointer', textAlign: 'right', color: 'var(--accent)' }}>MoE Final Alpha <ArrowUpDown size={11} /></th>
              <th style={{ textAlign: 'center' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s) => {
              const isSelected = selectedSignal?.ticker === s.ticker
              return (
                <tr
                  key={s.ticker}
                  onClick={() => setSelectedSignal(s)}
                  style={{
                    cursor: 'pointer',
                    background: isSelected ? 'var(--surface-2)' : 'transparent',
                    borderLeft: isSelected ? '3px solid var(--accent)' : '3px solid transparent',
                  }}
                >
                  <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.88rem' }}>
                    {s.ticker}
                    {isSelected && <Award size={13} color="var(--accent)" style={{ marginLeft: 6, verticalAlign: 'middle' }} />}
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={s.lgbm_alpha >= 0 ? 'pos' : 'neg'}>
                    {(s.lgbm_alpha * 100).toFixed(2)}%
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={s.kan_alpha >= 0 ? 'pos' : 'neg'}>
                    {(s.kan_alpha * 100).toFixed(2)}%
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={s.patchtst_alpha >= 0 ? 'pos' : 'neg'}>
                    {(s.patchtst_alpha * 100).toFixed(2)}%
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={s.il_alpha >= 0 ? 'pos' : 'neg'}>
                    {(s.il_alpha * 100).toFixed(2)}%
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '0.95rem' }} className={s.final_alpha >= 0 ? 'pos' : 'neg'}>
                    {(s.final_alpha * 100).toFixed(2)}%
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: '0.68rem', fontFamily: 'var(--font-mono)',
                      background: s.gate_active ? 'var(--bull-dim)' : 'var(--high-vol-dim)',
                      color: s.gate_active ? 'var(--bull)' : 'var(--high-vol)',
                    }}>
                      {s.gate_active ? 'PASS' : 'GATED'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
