import { useState, useEffect, useRef } from 'react'
import { Sparkles, Plus, Trash2, ChevronDown, ChevronUp, AlertCircle, CheckCircle, ArrowRight, Info } from 'lucide-react'
import { useStore } from '../store/useStore'
import { submitAnalysis, getStatus, getPortfolioResult, NIFTY50_TICKERS, SECTORS, formatINR } from '../utils/api'
import type { Holding } from '../store/useStore'

const EXAMPLE_GOALS = [
  "I want 15% annual returns with max 10% drawdown. I have ₹5 lakhs to invest for 1 year. I'm aggressive and want to avoid pharma and FMCG.",
  "Conservative investor looking for 10–12% steady returns over 2 years. Capital: ₹10 lakhs. No exposure to cyclical sectors. Max drawdown 8%.",
  "I want to beat the NIFTY by 5% with moderate risk. ₹3 lakh corpus, 18-month horizon. Exclude PSU banking stocks.",
]

const SECTOR_COLORS: Record<string, string> = {
  Banking: '#58a6ff', IT: '#3fb950', Energy: '#f0883e',
  FMCG: '#bc8cff', Pharma: '#e3b341', Auto: '#ff7b72',
  NBFC: '#58a6ff', Metals: '#8b949e', Infra: '#d2a8ff',
  Default: '#8b949e',
}

export default function InputPage() {
  const {
    nlGoal, setNlGoal,
    portfolio, setPortfolio, addHolding, removeHolding, updateHolding,
    job, setJob, setResult, setActiveView, pushAgentMessage,
  } = useStore()

  const [showPortfolioForm, setShowPortfolioForm] = useState(false)
  const [newHolding, setNewHolding] = useState<Partial<Holding>>({
    ticker: '', shares: 0, avg_buy_price: 0, current_price: null, sector: null,
  })
  const [addingHolding, setAddingHolding] = useState(false)
  const [validationError, setValidationError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const totalPortfolioValue = portfolio.holdings.reduce(
    (sum, h) => sum + h.shares * (h.current_price || h.avg_buy_price), 0
  ) + portfolio.cash_inr

  const totalCostBasis = portfolio.holdings.reduce(
    (sum, h) => sum + h.shares * h.avg_buy_price, 0
  )

  const totalPnL = totalPortfolioValue - totalCostBasis - portfolio.cash_inr

  const handleSubmit = async () => {
    if (!nlGoal.trim() || nlGoal.length < 10) {
      setValidationError('Please describe your investment goal (at least 10 characters).')
      return
    }
    setValidationError('')

    const payload = {
      nl_goal: nlGoal,
      portfolio: portfolio.holdings.length > 0 ? [{
        holdings: portfolio.holdings,
        total_invested_inr: portfolio.total_invested_inr,
        cash_inr: portfolio.cash_inr,
        demat_id: portfolio.demat_id,
      }] : [],
    }

    try {
      setJob({ status: 'queued', progress: 0, message: 'Submitting analysis...' })
      pushAgentMessage({ type: 'info', model: 'System', message: 'Pipeline submitted — parsing investment goal...' })

      const { job_id } = await submitAnalysis(payload)
      setJob({ job_id, status: 'queued' })

      pollRef.current = setInterval(async () => {
        try {
          const status = await getStatus(job_id)
          setJob({ status: status.status as any, progress: status.progress, message: status.message })

          if (status.progress > 30) {
            pushAgentMessage({ type: 'signal', model: 'LightGBM', message: `Alpha computation ${status.progress}% complete` })
          }

          if (status.status === 'done') {
            clearInterval(pollRef.current!)
            const result = await getPortfolioResult(job_id)
            setResult(result)
            setActiveView('results')
            pushAgentMessage({ type: 'info', model: 'QUANTIS', message: 'Portfolio analysis complete — switching to results view.' })
          } else if (status.status === 'error') {
            clearInterval(pollRef.current!)
            setJob({ status: 'error', error: status.error || 'Unknown error' })
          }
        } catch (e) {
          console.error('Poll error', e)
        }
      }, 1200)

    } catch (err: any) {
      setJob({ status: 'error', error: err?.message || 'Failed to submit' })
    }
  }

  const handleAddHolding = () => {
    if (!newHolding.ticker || !newHolding.shares || !newHolding.avg_buy_price) return
    addHolding({
      ticker: newHolding.ticker.trim().toUpperCase(),
      shares: Number(newHolding.shares),
      avg_buy_price: Number(newHolding.avg_buy_price),
      current_price: newHolding.current_price ? Number(newHolding.current_price) : null,
      sector: newHolding.sector || null,
    })
    setNewHolding({ ticker: '', shares: 0, avg_buy_price: 0, current_price: null, sector: null })
    setAddingHolding(false)
  }

  const isRunning = job.status === 'queued' || job.status === 'running'

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', paddingTop: 32 }} className="fade-in">

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ marginBottom: 8 }}>
          <span style={{ fontStyle: 'italic', color: 'var(--accent)' }}>Regime-aware</span> portfolio intelligence
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', maxWidth: 560 }}>
          Describe your investment goals in plain English. Add your existing holdings for personalised rebalancing advice — powered by KAN, LightGBM, PatchTST and HMM regime detection.
        </p>
      </div>

      {/* NL Goal Panel */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-label">
          <Sparkles size={13} />
          Investment Goal
        </div>

        <textarea
          className="input textarea"
          style={{ minHeight: 120, fontFamily: 'var(--font-body)', fontSize: '0.95rem', lineHeight: 1.7 }}
          placeholder="E.g. 'I want 15% annual returns with max 10% drawdown, ₹5L corpus, 1 year horizon, moderate risk. Avoid pharma.'"
          value={nlGoal}
          onChange={(e) => setNlGoal(e.target.value)}
          disabled={isRunning}
        />

        {/* Example chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', alignSelf: 'center' }}>Try:</span>
          {EXAMPLE_GOALS.map((eg, i) => (
            <button
              key={i}
              onClick={() => setNlGoal(eg)}
              style={{
                background: 'var(--surface-2)', border: '1px solid var(--border)',
                borderRadius: 6, padding: '4px 10px', cursor: 'pointer',
                fontSize: '0.74rem', color: 'var(--text-secondary)',
                fontFamily: 'var(--font-body)', transition: 'all 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--accent)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
            >
              {['Aggressive Growth', 'Conservative Income', 'Index Beater'][i]}
            </button>
          ))}
        </div>
      </div>

      {/* Structured goal override */}
      <GoalFormPanel disabled={isRunning} />

      {/* Portfolio Panel */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
          onClick={() => setShowPortfolioForm(!showPortfolioForm)}
        >
          <div className="section-label" style={{ marginBottom: 0 }}>
            <span>📊</span>
            Existing Portfolio
            {portfolio.holdings.length > 0 && (
              <span style={{
                background: 'var(--accent-dim)', color: 'var(--accent)',
                padding: '2px 8px', borderRadius: 10, fontSize: '0.72rem', fontWeight: 700,
              }}>
                {portfolio.holdings.length} holdings
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {portfolio.holdings.length > 0 && (
              <span style={{ fontSize: '0.82rem', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {formatINR(totalPortfolioValue)}
                <span className={totalPnL >= 0 ? 'pos' : 'neg'} style={{ marginLeft: 8, fontSize: '0.75rem' }}>
                  {totalPnL >= 0 ? '+' : ''}{formatINR(totalPnL)}
                </span>
              </span>
            )}
            {showPortfolioForm ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
          </div>
        </div>

        {!showPortfolioForm && portfolio.holdings.length === 0 && (
          <p style={{ fontSize: '0.83rem', color: 'var(--text-muted)', marginTop: 10 }}>
            Optional — add your holdings for personalised rebalancing recommendations. Leave empty to analyse NIFTY 50 universe.
          </p>
        )}

        {showPortfolioForm && (
          <div style={{ marginTop: 20 }} className="fade-in">
            {/* Capital inputs */}
            <div className="grid-3" style={{ marginBottom: 20 }}>
              <div>
                <label className="label">Total Invested (₹)</label>
                <input
                  className="input"
                  type="number"
                  value={portfolio.total_invested_inr}
                  onChange={(e) => setPortfolio({ ...portfolio, total_invested_inr: Number(e.target.value) })}
                  disabled={isRunning}
                />
              </div>
              <div>
                <label className="label">Uninvested Cash (₹)</label>
                <input
                  className="input"
                  type="number"
                  value={portfolio.cash_inr}
                  onChange={(e) => setPortfolio({ ...portfolio, cash_inr: Number(e.target.value) })}
                  disabled={isRunning}
                />
              </div>
              <div>
                <label className="label">Demat / Broker ID (optional)</label>
                <input
                  className="input"
                  type="text"
                  placeholder="e.g. Zerodha-123456"
                  value={portfolio.demat_id}
                  onChange={(e) => setPortfolio({ ...portfolio, demat_id: e.target.value })}
                  disabled={isRunning}
                />
              </div>
            </div>

            {/* Holdings table */}
            {portfolio.holdings.length > 0 && (
              <div style={{ marginBottom: 20, overflowX: 'auto' }}>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Sector</th>
                      <th style={{ textAlign: 'right' }}>Shares</th>
                      <th style={{ textAlign: 'right' }}>Avg Buy ₹</th>
                      <th style={{ textAlign: 'right' }}>Current ₹</th>
                      <th style={{ textAlign: 'right' }}>Value</th>
                      <th style={{ textAlign: 'right' }}>P&L</th>
                      <th style={{ textAlign: 'right' }}>Weight</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.holdings.map((h) => {
                      const price = h.current_price || h.avg_buy_price
                      const value = h.shares * price
                      const pnl = h.shares * (price - h.avg_buy_price)
                      const weight = value / (totalPortfolioValue || 1)
                      const sector = h.sector || 'Unknown'
                      return (
                        <tr key={h.ticker}>
                          <td>
                            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '0.85rem' }}>
                              {h.ticker}
                            </span>
                          </td>
                          <td>
                            <span style={{
                              fontSize: '0.75rem', padding: '2px 8px', borderRadius: 4,
                              background: `${SECTOR_COLORS[sector] || SECTOR_COLORS.Default}20`,
                              color: SECTOR_COLORS[sector] || SECTOR_COLORS.Default,
                            }}>
                              {sector}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{h.shares}</td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>₹{h.avg_buy_price.toLocaleString()}</td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                            {h.current_price ? `₹${h.current_price.toLocaleString()}` : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                          </td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{formatINR(value)}</td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                            <span className={pnl >= 0 ? 'pos' : 'neg'}>
                              {pnl >= 0 ? '+' : ''}{formatINR(pnl)}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                            {(weight * 100).toFixed(1)}%
                          </td>
                          <td>
                            <button
                              onClick={() => removeHolding(h.ticker)}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}
                              disabled={isRunning}
                            >
                              <Trash2 size={13} color="var(--bear)" />
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Add holding form */}
            {addingHolding ? (
              <div className="card-sm fade-in" style={{ marginBottom: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1.5fr', gap: 10, alignItems: 'end' }}>
                  <div>
                    <label className="label">Ticker</label>
                    <select
                      className="input"
                      value={newHolding.ticker}
                      onChange={(e) => setNewHolding({ ...newHolding, ticker: e.target.value })}
                    >
                      <option value="">Select or type...</option>
                      {NIFTY50_TICKERS.filter(t => !portfolio.holdings.find(h => h.ticker === t))
                        .map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="label">Shares</label>
                    <input className="input" type="number" min={1}
                      value={newHolding.shares || ''}
                      onChange={(e) => setNewHolding({ ...newHolding, shares: Number(e.target.value) })}
                      placeholder="100"
                    />
                  </div>
                  <div>
                    <label className="label">Avg Buy ₹</label>
                    <input className="input" type="number" min={0.01}
                      value={newHolding.avg_buy_price || ''}
                      onChange={(e) => setNewHolding({ ...newHolding, avg_buy_price: Number(e.target.value) })}
                      placeholder="2500"
                    />
                  </div>
                  <div>
                    <label className="label">Current ₹ (opt)</label>
                    <input className="input" type="number" min={0}
                      value={newHolding.current_price || ''}
                      onChange={(e) => setNewHolding({ ...newHolding, current_price: Number(e.target.value) || null })}
                      placeholder="2800"
                    />
                  </div>
                  <div>
                    <label className="label">Sector</label>
                    <select className="input"
                      value={newHolding.sector || ''}
                      onChange={(e) => setNewHolding({ ...newHolding, sector: e.target.value || null })}
                    >
                      <option value="">Auto-detect</option>
                      {SECTORS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button className="btn btn-primary btn-sm" onClick={handleAddHolding}
                    disabled={!newHolding.ticker || !newHolding.shares || !newHolding.avg_buy_price}>
                    <Plus size={13} /> Add
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => setAddingHolding(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button className="btn btn-secondary btn-sm" onClick={() => setAddingHolding(true)} disabled={isRunning}>
                <Plus size={13} /> Add Holding
              </button>
            )}
          </div>
        )}
      </div>

      {/* Error */}
      {validationError && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--bear-dim)', border: '1px solid rgba(255,77,106,0.3)',
          borderRadius: 8, padding: '10px 14px', marginBottom: 16, color: 'var(--bear)', fontSize: '0.88rem',
        }}>
          <AlertCircle size={14} /> {validationError}
        </div>
      )}

      {/* Job error */}
      {job.status === 'error' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--bear-dim)', border: '1px solid rgba(255,77,106,0.3)',
          borderRadius: 8, padding: '10px 14px', marginBottom: 16, color: 'var(--bear)', fontSize: '0.88rem',
        }}>
          <AlertCircle size={14} /> {job.error || 'Analysis failed'}
        </div>
      )}

      {/* Progress */}
      {isRunning && (
        <div className="card-sm fade-in" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: '0.83rem', color: 'var(--text-secondary)' }}>{job.message}</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: '0.83rem' }}>
              {job.progress}%
            </span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${job.progress}%` }} />
          </div>
          <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {['NL Parser', 'Mamba Encoder', 'KAN Alpha', 'LGBM Alpha', 'PatchTST', 'HMM Regime', 'MoE Gating', 'CVaR Optimizer', 'Monte Carlo'].map((step, i) => {
              const threshold = (i + 1) * 11
              const done = job.progress >= threshold
              const active = job.progress >= threshold - 11 && !done
              return (
                <span key={step} style={{
                  fontSize: '0.7rem', padding: '2px 8px', borderRadius: 4,
                  background: done ? 'var(--bull-dim)' : active ? 'var(--accent-dim)' : 'var(--surface-3)',
                  color: done ? 'var(--bull)' : active ? 'var(--accent)' : 'var(--text-muted)',
                  fontFamily: 'var(--font-mono)',
                  border: `1px solid ${done ? 'rgba(0,212,160,0.2)' : active ? 'rgba(245,166,35,0.2)' : 'transparent'}`,
                  transition: 'all 0.3s',
                }}>
                  {done ? '✓ ' : active ? '⟳ ' : ''}{step}
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* Submit */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <button
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={isRunning || !nlGoal.trim()}
          style={{ minWidth: 200, justifyContent: 'center' }}
        >
          {isRunning ? (
            <>
              <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⟳</span>
              Analysing...
            </>
          ) : (
            <>
              <Sparkles size={15} />
              Run QUANTIS Analysis
              <ArrowRight size={14} />
            </>
          )}
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          <Info size={12} />
          SEBI-compliant · NSE/BSE · 10K MC paths
        </div>
      </div>

      <style>{`@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }`}</style>
    </div>
  )
}

// ── Structured goal form ───────────────────────────────────────────────────────
function GoalFormPanel({ disabled }: { disabled: boolean }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    return_target: 15,
    max_drawdown: 10,
    horizon_months: 12,
    risk_tolerance: 'moderate',
    sectors_excluded: [] as string[],
    capital_inr: 500000,
  })

  const toggleSector = (s: string) => {
    setForm(f => ({
      ...f,
      sectors_excluded: f.sectors_excluded.includes(s)
        ? f.sectors_excluded.filter(x => x !== s)
        : [...f.sectors_excluded, s],
    }))
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setOpen(!open)}>
        <div className="section-label" style={{ marginBottom: 0 }}>
          <span>🎯</span>
          Structured Goal Parameters
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 400, letterSpacing: 0, textTransform: 'none' }}>
            — overrides NL parsing if filled
          </span>
        </div>
        {open ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
      </div>

      {open && (
        <div style={{ marginTop: 20 }} className="fade-in">
          <div className="grid-3" style={{ marginBottom: 20 }}>
            <div>
              <label className="label">Target Return (%/yr)</label>
              <input className="input" type="number" min={1} max={200}
                value={form.return_target}
                onChange={(e) => setForm({ ...form, return_target: Number(e.target.value) })}
                disabled={disabled}
              />
            </div>
            <div>
              <label className="label">Max Drawdown (%)</label>
              <input className="input" type="number" min={1} max={99}
                value={form.max_drawdown}
                onChange={(e) => setForm({ ...form, max_drawdown: Number(e.target.value) })}
                disabled={disabled}
              />
            </div>
            <div>
              <label className="label">Investment Horizon (months)</label>
              <input className="input" type="number" min={1} max={120}
                value={form.horizon_months}
                onChange={(e) => setForm({ ...form, horizon_months: Number(e.target.value) })}
                disabled={disabled}
              />
            </div>
            <div>
              <label className="label">Capital (₹)</label>
              <input className="input" type="number" min={10000}
                value={form.capital_inr}
                onChange={(e) => setForm({ ...form, capital_inr: Number(e.target.value) })}
                disabled={disabled}
              />
            </div>
            <div>
              <label className="label">Risk Tolerance</label>
              <select className="input"
                value={form.risk_tolerance}
                onChange={(e) => setForm({ ...form, risk_tolerance: e.target.value })}
                disabled={disabled}
              >
                <option value="conservative">Conservative</option>
                <option value="moderate">Moderate</option>
                <option value="aggressive">Aggressive</option>
              </select>
            </div>
          </div>

          <div>
            <label className="label">Exclude Sectors</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 4 }}>
              {SECTORS.map(s => (
                <button
                  key={s}
                  onClick={() => toggleSector(s)}
                  disabled={disabled}
                  style={{
                    padding: '4px 12px', borderRadius: 6, cursor: 'pointer',
                    fontSize: '0.78rem', fontFamily: 'var(--font-body)',
                    background: form.sectors_excluded.includes(s) ? 'var(--bear-dim)' : 'var(--surface-2)',
                    border: `1px solid ${form.sectors_excluded.includes(s) ? 'rgba(255,77,106,0.4)' : 'var(--border)'}`,
                    color: form.sectors_excluded.includes(s) ? 'var(--bear)' : 'var(--text-secondary)',
                    transition: 'all 0.15s',
                  }}
                >
                  {form.sectors_excluded.includes(s) ? '✕ ' : ''}{s}
                </button>
              ))}
            </div>
          </div>

          <div style={{
            marginTop: 16, padding: '10px 14px', borderRadius: 8,
            background: 'var(--accent-dim)', border: '1px solid rgba(245,166,35,0.2)',
            fontSize: '0.78rem', color: 'var(--text-secondary)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <CheckCircle size={13} color="var(--accent)" />
            These values are sent directly to the pipeline. The NL goal above will still be parsed by the model for sentiment and context.
          </div>
        </div>
      )}
    </div>
  )
}
