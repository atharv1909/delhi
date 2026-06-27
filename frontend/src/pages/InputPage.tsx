import { useState, useEffect, useRef } from 'react'
import { Sparkles, Plus, Trash2, ChevronDown, ChevronUp, AlertCircle, ArrowRight, Info } from 'lucide-react'
import { useStore } from '../store/useStore'
import { submitAnalysis, getStatus, getPortfolioResult, NIFTY50_TICKERS, SECTORS, formatINR } from '../utils/api'
import VoiceInput from '../components/layout/VoiceInput'
import type { Holding } from '../store/useStore'

const EXAMPLE_GOALS = [
  "I want 15% annual returns with max 10% drawdown. I have ₹5 lakhs to invest for 1 year. I'm aggressive and want to avoid pharma and FMCG.",
  "Conservative investor looking for 10–12% steady returns over 2 years. Capital: ₹10 lakhs. No exposure to cyclical sectors. Max drawdown 8%.",
  "I want to beat the NIFTY by 5% with moderate risk. ₹3 lakh corpus, 18-month horizon. Exclude PSU banking stocks.",
]

const SECTOR_COLORS: Record<string, string> = {
  Banking: '#63B3ED', IT: '#48BB78', Energy: '#F6AD55', FMCG: '#B794F4',
  Pharma: '#F6E05E', Auto: '#FC5C7D', NBFC: '#63B3ED', Metals: '#A0AEC0',
  Default: '#A0AEC0',
}

export default function InputPage() {
  const { nlGoal, setNlGoal, portfolio, setPortfolio, addHolding, removeHolding,
    job, setJob, setResult, setActiveView, pushAgentMessage } = useStore()
  const [showPortfolioForm, setShowPortfolioForm] = useState(false)
  const [newHolding, setNewHolding] = useState<Partial<Holding>>({ ticker: '', shares: 0, avg_buy_price: 0, current_price: null, sector: null })
  const [addingHolding, setAddingHolding] = useState(false)
  const [validationError, setValidationError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const totalPortfolioValue = portfolio.holdings.reduce((sum, h) => sum + h.shares * (h.current_price || h.avg_buy_price), 0) + portfolio.cash_inr
  const totalCostBasis = portfolio.holdings.reduce((sum, h) => sum + h.shares * h.avg_buy_price, 0)
  const totalPnL = totalPortfolioValue - totalCostBasis - portfolio.cash_inr

  const handleSubmit = async () => {
    if (!nlGoal.trim() || nlGoal.length < 10) { setValidationError('Please describe your investment goal (at least 10 characters).'); return }
    setValidationError('')
    const payload = {
      nl_goal: nlGoal,
      portfolio: portfolio.holdings.length > 0 ? [{ holdings: portfolio.holdings, total_invested_inr: portfolio.total_invested_inr, cash_inr: portfolio.cash_inr, demat_id: portfolio.demat_id }] : [],
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
          if (status.status === 'done') {
            clearInterval(pollRef.current!)
            const result = await getPortfolioResult(job_id)
            setResult(result)
            setActiveView('results')
            pushAgentMessage({ type: 'info', model: 'InvestEasy', message: 'Portfolio analysis complete — switching to results view.' })
          } else if (status.status === 'error') {
            clearInterval(pollRef.current!)
            setJob({ status: 'error', error: status.error || 'Unknown error' })
          }
        } catch (e) { console.error('Poll error', e) }
      }, 2000)
    } catch (err: any) { setJob({ status: 'error', error: err?.message || 'Failed to submit' }) }
  }

  const handleAddHolding = () => {
    if (!newHolding.ticker || !newHolding.shares || !newHolding.avg_buy_price) return
    addHolding({ ticker: newHolding.ticker.trim().toUpperCase(), shares: Number(newHolding.shares), avg_buy_price: Number(newHolding.avg_buy_price), current_price: newHolding.current_price ? Number(newHolding.current_price) : null, sector: newHolding.sector || null })
    setNewHolding({ ticker: '', shares: 0, avg_buy_price: 0, current_price: null, sector: null })
    setAddingHolding(false)
  }

  const isRunning = job.status === 'queued' || job.status === 'running'
  const PIPELINE_STEPS = ['NL Parser', 'Market Data', 'Mamba Encoder', 'KAN Alpha', 'LGBM Alpha', 'PatchTST', 'HMM Regime', 'MoE Gating', 'CVaR Optimizer', 'Kelly Sizing', 'Monte Carlo', 'Backtest']

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', paddingTop: 32 }} className="fade-in">
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ marginBottom: 8, fontSize: '1.8rem', fontWeight: 800, letterSpacing: '-0.03em' }}>
          <span style={{ background: 'linear-gradient(135deg, var(--accent), var(--bull))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Regime-aware</span> portfolio intelligence
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', maxWidth: 620 }}>
          Describe your investment goals in plain English or use voice input. Add your existing holdings for personalised rebalancing — powered by KAN, LightGBM, PatchTST and HMM regime detection.
        </p>
      </div>

      {/* NL Goal Panel */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-label"><Sparkles size={13} /> Investment Goal</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <textarea className="input textarea" style={{ minHeight: 120, flex: 1, fontFamily: 'var(--font-body)', fontSize: '0.95rem', lineHeight: 1.7 }}
            placeholder="E.g. 'I want 15% annual returns with max 10% drawdown, ₹5L corpus, 1 year horizon, moderate risk. Avoid pharma.'"
            value={nlGoal} onChange={(e) => setNlGoal(e.target.value)} disabled={isRunning} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <VoiceInput onTranscript={(text) => setNlGoal(nlGoal ? nlGoal + ' ' + text : text)} disabled={isRunning} />
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.3 }}>Voice<br/>Input</div>
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', alignSelf: 'center' }}>Try:</span>
          {EXAMPLE_GOALS.map((eg, i) => (
            <button key={i} onClick={() => setNlGoal(eg)}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: '0.74rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-body)', transition: 'all 0.15s' }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--accent)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}>
              {['Aggressive Growth', 'Conservative Income', 'Index Beater'][i]}
            </button>
          ))}
        </div>
      </div>

      {/* Portfolio Panel */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }} onClick={() => setShowPortfolioForm(!showPortfolioForm)}>
          <div className="section-label" style={{ marginBottom: 0 }}>
            <span>📊</span> Existing Portfolio
            {portfolio.holdings.length > 0 && <span style={{ background: 'var(--accent-dim)', color: 'var(--accent)', padding: '2px 8px', borderRadius: 10, fontSize: '0.72rem', fontWeight: 700 }}>{portfolio.holdings.length} holdings</span>}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {portfolio.holdings.length > 0 && (
              <span style={{ fontSize: '0.82rem', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {formatINR(totalPortfolioValue)}
                <span className={totalPnL >= 0 ? 'pos' : 'neg'} style={{ marginLeft: 8, fontSize: '0.75rem' }}>{totalPnL >= 0 ? '+' : ''}{formatINR(totalPnL)}</span>
              </span>
            )}
            {showPortfolioForm ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
          </div>
        </div>
        {!showPortfolioForm && portfolio.holdings.length === 0 && (
          <p style={{ fontSize: '0.83rem', color: 'var(--text-muted)', marginTop: 10 }}>
            Optional — add your holdings for personalised rebalancing. Leave empty to analyse NIFTY 50 universe.
          </p>
        )}
        {showPortfolioForm && (
          <div style={{ marginTop: 20 }} className="fade-in">
            <div className="grid-3" style={{ marginBottom: 20 }}>
              <div><label className="label">Total Invested (₹)</label><input className="input" type="number" value={portfolio.total_invested_inr} onChange={(e) => setPortfolio({ ...portfolio, total_invested_inr: Number(e.target.value) })} disabled={isRunning} /></div>
              <div><label className="label">Uninvested Cash (₹)</label><input className="input" type="number" value={portfolio.cash_inr} onChange={(e) => setPortfolio({ ...portfolio, cash_inr: Number(e.target.value) })} disabled={isRunning} /></div>
              <div><label className="label">Demat / Broker ID</label><input className="input" type="text" placeholder="e.g. Zerodha-123456" value={portfolio.demat_id} onChange={(e) => setPortfolio({ ...portfolio, demat_id: e.target.value })} disabled={isRunning} /></div>
            </div>
            {portfolio.holdings.length > 0 && (
              <div style={{ marginBottom: 20, overflowX: 'auto' }}>
                <table className="tbl">
                  <thead><tr><th>Ticker</th><th>Sector</th><th style={{ textAlign: 'right' }}>Shares</th><th style={{ textAlign: 'right' }}>Avg Buy ₹</th><th style={{ textAlign: 'right' }}>Value</th><th style={{ textAlign: 'right' }}>P&L</th><th></th></tr></thead>
                  <tbody>
                    {portfolio.holdings.map((h) => {
                      const price = h.current_price || h.avg_buy_price
                      const value = h.shares * price
                      const pnl = h.shares * (price - h.avg_buy_price)
                      const sector = h.sector || 'Unknown'
                      return (
                        <tr key={h.ticker}>
                          <td><span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '0.85rem' }}>{h.ticker}</span></td>
                          <td><span style={{ fontSize: '0.75rem', padding: '2px 8px', borderRadius: 4, background: `${SECTOR_COLORS[sector] || SECTOR_COLORS.Default}20`, color: SECTOR_COLORS[sector] || SECTOR_COLORS.Default }}>{sector}</span></td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{h.shares}</td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>₹{h.avg_buy_price.toLocaleString()}</td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{formatINR(value)}</td>
                          <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}><span className={pnl >= 0 ? 'pos' : 'neg'}>{pnl >= 0 ? '+' : ''}{formatINR(pnl)}</span></td>
                          <td><button onClick={() => removeHolding(h.ticker)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }} disabled={isRunning}><Trash2 size={13} color="var(--bear)" /></button></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {addingHolding ? (
              <div className="card-sm fade-in" style={{ marginBottom: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1.5fr', gap: 10, alignItems: 'end' }}>
                  <div><label className="label">Ticker</label><select className="input" value={newHolding.ticker} onChange={(e) => setNewHolding({ ...newHolding, ticker: e.target.value })}><option value="">Select...</option>{NIFTY50_TICKERS.filter(t => !portfolio.holdings.find(h => h.ticker === t)).map(t => <option key={t} value={t}>{t}</option>)}</select></div>
                  <div><label className="label">Shares</label><input className="input" type="number" min={1} value={newHolding.shares || ''} onChange={(e) => setNewHolding({ ...newHolding, shares: Number(e.target.value) })} placeholder="100" /></div>
                  <div><label className="label">Avg Buy ₹</label><input className="input" type="number" min={0.01} value={newHolding.avg_buy_price || ''} onChange={(e) => setNewHolding({ ...newHolding, avg_buy_price: Number(e.target.value) })} placeholder="2500" /></div>
                  <div><label className="label">Sector</label><select className="input" value={newHolding.sector || ''} onChange={(e) => setNewHolding({ ...newHolding, sector: e.target.value || null })}><option value="">Auto-detect</option>{SECTORS.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button className="btn btn-primary btn-sm" onClick={handleAddHolding} disabled={!newHolding.ticker || !newHolding.shares || !newHolding.avg_buy_price}><Plus size={13} /> Add</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => setAddingHolding(false)}>Cancel</button>
                </div>
              </div>
            ) : (
              <button className="btn btn-secondary btn-sm" onClick={() => setAddingHolding(true)} disabled={isRunning}><Plus size={13} /> Add Holding</button>
            )}
          </div>
        )}
      </div>

      {validationError && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bear-dim)', border: '1px solid rgba(252,92,125,0.3)', borderRadius: 8, padding: '10px 14px', marginBottom: 16, color: 'var(--bear)', fontSize: '0.88rem' }}>
          <AlertCircle size={14} /> {validationError}
        </div>
      )}
      {job.status === 'error' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bear-dim)', border: '1px solid rgba(252,92,125,0.3)', borderRadius: 8, padding: '10px 14px', marginBottom: 16, color: 'var(--bear)', fontSize: '0.88rem' }}>
          <AlertCircle size={14} /> {job.error || 'Analysis failed'}
        </div>
      )}

      {/* Progress */}
      {isRunning && (
        <div className="card-sm fade-in" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: '0.83rem', color: 'var(--text-secondary)' }}>{job.message}</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: '0.83rem' }}>{job.progress}%</span>
          </div>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${job.progress}%` }} /></div>
          <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {PIPELINE_STEPS.map((step, i) => {
              const threshold = ((i + 1) / PIPELINE_STEPS.length) * 100
              const done = job.progress >= threshold
              const active = job.progress >= threshold - (100 / PIPELINE_STEPS.length) && !done
              return (
                <span key={step} style={{ fontSize: '0.7rem', padding: '2px 8px', borderRadius: 4, background: done ? 'var(--bull-dim)' : active ? 'var(--accent-dim)' : 'var(--surface-3)', color: done ? 'var(--bull)' : active ? 'var(--accent)' : 'var(--text-muted)', fontFamily: 'var(--font-mono)', border: `1px solid ${done ? 'rgba(72,187,120,0.2)' : active ? 'rgba(99,179,237,0.2)' : 'transparent'}`, transition: 'all 0.3s' }}>
                  {done ? '✓ ' : active ? '⟳ ' : ''}{step}
                </span>
              )
            })}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <button className="btn btn-primary" onClick={handleSubmit} disabled={isRunning || !nlGoal.trim()} style={{ minWidth: 200, justifyContent: 'center' }}>
          {isRunning ? (<><span className="spin">⟳</span> Analysing...</>) : (<><Sparkles size={15} /> Run InvestEasy Analysis <ArrowRight size={14} /></>)}
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          <Info size={12} /> SEBI-compliant · NSE/BSE · Real ML Models · 10K MC paths
        </div>
      </div>
    </div>
  )
}
