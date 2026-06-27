import { useEffect, useState } from 'react'
import { Play, Square, RefreshCw, Radio, TrendingUp, AlertTriangle, ShieldCheck } from 'lucide-react'
import { ResponsiveContainer, AreaChart, Area, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { useStore } from '../store/useStore'
import { startLive, stopLive, getLiveStatus, getLiveData, formatINR } from '../utils/api'

export default function LivePage() {
  const { liveStatus, setLiveStatus, liveProgress, setLiveProgress, liveMessage, setLiveMessage, liveData, setLiveData } = useStore()
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)

  const handleStart = async () => {
    try {
      setLiveStatus('running')
      setLiveProgress(5)
      setLiveMessage('Triggering live fetch...')
      await startLive()
    } catch (e: any) {
      setLiveStatus('error')
      setLiveMessage(e?.message || 'Failed to start live analysis')
    }
  }

  const handleStop = async () => {
    try {
      await stopLive()
      setLiveStatus('idle')
    } catch {}
  }

  // Poll live status when running
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>
    if (liveStatus === 'running') {
      interval = setInterval(async () => {
        try {
          const res = await getLiveStatus()
          setLiveStatus(res.status)
          setLiveProgress(res.progress)
          setLiveMessage(res.message)
          if (res.status === 'done') {
            const data = await getLiveData()
            setLiveData(data)
          }
        } catch {}
      }, 1500)
    }
    return () => clearInterval(interval)
  }, [liveStatus])

  const REGIME_COLORS: Record<string, string> = {
    bull: 'var(--bull)', bear: 'var(--bear)', high_vol: 'var(--high-vol)', ranging: 'var(--ranging)',
  }

  return (
    <div style={{ maxWidth: 1320, margin: '0 auto', paddingTop: 24 }} className="fade-in">
      {/* Header bar */}
      <div className="card" style={{ marginBottom: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <Radio size={20} color="var(--accent)" className={liveStatus === 'running' ? 'pulse' : ''} />
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, letterSpacing: '-0.02em' }}>Live Market Intelligence</h2>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
            On-demand live execution: fetches 5-minute intraday OHLCV candles directly from Coinbase Advanced REST API & exchange feeds, computing real-time EMA/BB/RSI telemetry & LightGBM/KAN alpha inference.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {liveStatus === 'running' ? (
            <button className="btn" onClick={handleStop} style={{ background: 'var(--bear-dim)', color: 'var(--bear)', border: '1px solid rgba(252,92,125,0.3)' }}>
              <Square size={14} /> Stop Live Analysis
            </button>
          ) : (
            <button className="btn btn-primary" onClick={handleStart}>
              <Play size={14} /> Run Live Analysis
            </button>
          )}
        </div>
      </div>

      {/* Progress banner */}
      {liveStatus === 'running' && (
        <div className="card-sm fade-in" style={{ marginBottom: 24, border: '1px solid var(--border-accent)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--accent)' }}>
              <RefreshCw size={13} className="spin" style={{ marginRight: 6 }} /> {liveMessage}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 700 }}>{liveProgress}%</span>
          </div>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${liveProgress}%` }} /></div>
        </div>
      )}

      {liveStatus === 'error' && (
        <div style={{ background: 'var(--bear-dim)', border: '1px solid rgba(252,92,125,0.3)', padding: 16, borderRadius: 10, color: 'var(--bear)', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 10 }}>
          <AlertTriangle size={18} /> <span>{liveMessage}</span>
        </div>
      )}

      {!liveData && liveStatus !== 'running' && (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: '3rem', marginBottom: 12 }}>⚡</div>
          <h3 style={{ fontSize: '1.2rem', color: 'var(--text-secondary)', marginBottom: 8 }}>Ready for Live Market Scanning</h3>
          <p style={{ fontSize: '0.9rem', maxWidth: 520, margin: '0 auto' }}>
            Click "Run Live Analysis" above to fetch 5-minute intraday candles directly from Coinbase Advanced REST API & exchange feeds. Note: On Weekends/Holidays when Indian equity markets are closed, 24/7 crypto execution remains fully active!
          </p>
        </div>
      )}

      {/* Live results matrix */}
      {liveData && (
        <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* Market Status Banner */}
          {liveData.market?.status && (
            <div className="card-sm fade-in" style={{
              background: liveData.market.status.includes('CLOSED') ? 'rgba(255, 170, 0, 0.1)' : 'rgba(0, 230, 118, 0.1)',
              border: `1px solid ${liveData.market.status.includes('CLOSED') ? 'rgba(255, 170, 0, 0.3)' : 'rgba(0, 230, 118, 0.3)'}`,
              padding: '14px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 12
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: '1.4rem' }}>{liveData.market.status.includes('CLOSED') ? '🏖️' : '🟢'}</span>
                <div>
                  <div style={{ fontWeight: 700, color: liveData.market.status.includes('CLOSED') ? '#ffaa00' : 'var(--bull)', fontSize: '0.98rem' }}>
                    NSE / BSE Equity Market Status: {liveData.market.status}
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                    {liveData.market.note || "Live feeds active."}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--surface-2)', padding: '6px 14px', borderRadius: 20, border: '1px solid var(--border)' }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#00e676', display: 'inline-block', boxShadow: '0 0 8px #00e676' }} />
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>Coinbase Crypto 24/7 Live</span>
              </div>
            </div>
          )}

          {/* Top market summary cards */}
          <div className="grid-3">
            <div className="kpi-card">
              <span className="kpi-label">NIFTY 50 Level</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span className="kpi-value">{liveData.market?.nifty_level?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
                <span style={{ fontSize: '0.78rem', color: 'var(--bull)' }}>● Live Snapshot</span>
              </div>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">India VIX Volatility Index</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span className="kpi-value" style={{ color: (liveData.market?.india_vix || 0) > 20 ? 'var(--high-vol)' : 'var(--text-primary)' }}>
                  {liveData.market?.india_vix?.toFixed(2)}
                </span>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Implied Vol</span>
              </div>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">Detected Market Regime</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span className={`badge badge-${liveData.regime?.state === 'high_vol' ? 'high-vol' : liveData.regime?.state || 'ranging'}`}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: REGIME_COLORS[liveData.regime?.state] || 'var(--ranging)', display: 'inline-block' }} />
                  {(liveData.regime?.state || 'ranging').toUpperCase().replace('_', ' ')}
                </span>
                <span style={{ fontSize: '0.78rem', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                  Kelly: {(liveData.regime?.kelly_factor || 0.5) * 100}%
                </span>
              </div>
            </div>
          </div>

          {/* Interactive Recharts Analytics Section */}
          {(() => {
            const activeAsset = liveData.signals?.find((s: any) => s.ticker === selectedTicker) || liveData.signals?.[0]
            if (!activeAsset) return null
            const getCurr = (t: string) => (t.endsWith('.NS') || t.endsWith('.BO') ? '₹' : '$')
            const curr = getCurr(activeAsset.ticker)

            return (
              <div className="card fade-in" style={{ border: '1px solid var(--border-accent)', padding: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <h3 style={{ fontSize: '1.35rem', fontWeight: 800, margin: 0, color: 'var(--text-primary)' }}>
                        {activeAsset.name} <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>({activeAsset.ticker})</span>
                      </h3>
                      <span style={{ fontSize: '0.75rem', padding: '3px 8px', borderRadius: 4, background: 'var(--surface-2)', color: 'var(--text-secondary)' }}>{activeAsset.sector}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginTop: 8 }}>
                      <span style={{ fontSize: '1.5rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                        {curr}{activeAsset.price?.toLocaleString()}
                      </span>
                      <span className={activeAsset.ret_1d >= 0 ? 'pos' : 'neg'} style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', fontSize: '0.95rem' }}>
                        {activeAsset.ret_1d >= 0 ? '+' : ''}{activeAsset.ret_1d}% (1D)
                      </span>
                      <span style={{
                        padding: '4px 10px', borderRadius: 6, fontSize: '0.75rem', fontWeight: 700, fontFamily: 'var(--font-mono)',
                        background: activeAsset.action === 'BUY' ? 'var(--bull-dim)' : activeAsset.action === 'SELL' ? 'var(--bear-dim)' : 'var(--surface-2)',
                        color: activeAsset.action === 'BUY' ? 'var(--bull)' : activeAsset.action === 'SELL' ? 'var(--bear)' : 'var(--text-secondary)',
                      }}>
                        AI Signal: {activeAsset.action}
                      </span>
                    </div>
                  </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                    {liveData.signals?.slice(0, 10).map((s: any) => (
                      <button
                        key={s.ticker}
                        onClick={() => setSelectedTicker(s.ticker)}
                        style={{
                          padding: '4px 10px', borderRadius: 16, fontSize: '0.78rem', fontWeight: 700, fontFamily: 'var(--font-mono)', cursor: 'pointer',
                          background: (selectedTicker === s.ticker || (!selectedTicker && s === activeAsset)) ? 'var(--accent)' : 'var(--surface-2)',
                          color: (selectedTicker === s.ticker || (!selectedTicker && s === activeAsset)) ? '#000' : 'var(--text-secondary)',
                          border: '1px solid rgba(255,255,255,0.06)'
                        }}
                      >
                        {s.ticker}
                      </button>
                    ))}
                  </div>

                {/* Recharts Price AreaChart with EMA & Bollinger Bands */}
                {activeAsset.history && activeAsset.history.length > 0 ? (
                  <div style={{ height: 320, width: '100%', marginBottom: 24 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={activeAsset.history} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.45}/>
                            <stop offset="95%" stopColor="var(--accent)" stopOpacity={0.0}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                        <XAxis dataKey="date" stroke="var(--text-muted)" fontSize={11} tickLine={false} />
                        <YAxis domain={['auto', 'auto']} stroke="var(--text-muted)" fontSize={11} tickLine={false} tickFormatter={(val) => `${curr}${Number(val).toLocaleString()}`} />
                        <Tooltip
                          contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
                          formatter={(val: any, name: any) => [`${curr}${Number(val).toLocaleString()}`, name]}
                        />
                        <Area type="monotone" dataKey="bb_upper" stroke="none" fill="rgba(64,224,208,0.06)" name="BB Upper" />
                        <Area type="monotone" dataKey="bb_lower" stroke="none" fill="var(--surface-1)" name="BB Lower" />
                        <Area type="monotone" dataKey="price" stroke="var(--accent)" strokeWidth={2.5} fillOpacity={1} fill="url(#colorPrice)" name="Price" />
                        <Line type="monotone" dataKey="ema_9" stroke="#FFD700" strokeWidth={1.5} dot={false} name="EMA 9" />
                        <Line type="monotone" dataKey="ema_21" stroke="#FF69B4" strokeWidth={1.5} dot={false} name="EMA 21" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', background: 'var(--surface-2)', borderRadius: 8, marginBottom: 20 }}>
                    No historical telemetry available for this asset
                  </div>
                )}

                {/* Indicator Telemetry Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(135px, 1fr))', gap: 12 }}>
                  <div style={{ background: 'var(--surface-2)', padding: 12, borderRadius: 8, border: '1px solid rgba(255,255,255,0.03)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 4 }}>RSI (14)</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: (activeAsset.indicators?.rsi_14 || 50) > 70 ? 'var(--bear)' : (activeAsset.indicators?.rsi_14 || 50) < 30 ? 'var(--bull)' : 'var(--text-primary)' }}>
                      {activeAsset.indicators?.rsi_14?.toFixed(1) || 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--surface-2)', padding: 12, borderRadius: 8, border: '1px solid rgba(255,255,255,0.03)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 4 }}>MACD</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: (activeAsset.indicators?.macd || 0) >= 0 ? 'var(--bull)' : 'var(--bear)' }}>
                      {activeAsset.indicators?.macd?.toFixed(2) || 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--surface-2)', padding: 12, borderRadius: 8, border: '1px solid rgba(255,255,255,0.03)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 4 }}>Bollinger %B</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      {activeAsset.indicators?.bb_pct?.toFixed(2) || 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--surface-2)', padding: 12, borderRadius: 8, border: '1px solid rgba(255,255,255,0.03)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 4 }}>ATR (14)</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      {activeAsset.indicators?.atr_14?.toFixed(2) || 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--surface-2)', padding: 12, borderRadius: 8, border: '1px solid rgba(255,255,255,0.03)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 4 }}>ADX (14)</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      {activeAsset.indicators?.adx_14?.toFixed(1) || 'N/A'}
                    </div>
                  </div>
                  <div style={{ background: 'var(--surface-2)', padding: 12, borderRadius: 8, border: '1px solid rgba(255,255,255,0.03)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 4 }}>10D ROC</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: (activeAsset.indicators?.roc_10 || 0) >= 0 ? 'var(--bull)' : 'var(--bear)' }}>
                      {activeAsset.indicators?.roc_10 !== undefined ? `${(activeAsset.indicators.roc_10 * 100).toFixed(1)}%` : 'N/A'}
                    </div>
                  </div>
                </div>
              </div>
            )
          })()}

          {/* Signals Table */}
          <div className="card">
            <div className="section-label" style={{ justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <TrendingUp size={15} color="var(--accent)" /> Live Alpha Predictions & Signals
              </div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                Analyzed {liveData.stocks_analyzed} stocks at {new Date(liveData.timestamp).toLocaleTimeString()}
              </span>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Sector</th>
                    <th style={{ textAlign: 'right' }}>Price</th>
                    <th style={{ textAlign: 'right' }}>LGBM Alpha</th>
                    <th style={{ textAlign: 'right' }}>KAN Alpha</th>
                    <th style={{ textAlign: 'right' }}>Combined Alpha</th>
                    <th style={{ textAlign: 'center' }}>Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {liveData.signals?.map((s: any) => {
                    const curr = s.ticker.endsWith('.NS') || s.ticker.endsWith('.BO') ? '₹' : '$'
                    const isSelected = (selectedTicker === s.ticker) || (!selectedTicker && liveData.signals?.[0]?.ticker === s.ticker)
                    return (
                      <tr key={s.ticker} onClick={() => setSelectedTicker(s.ticker)} style={{ cursor: 'pointer', background: isSelected ? 'rgba(99,102,241,0.12)' : 'transparent', transition: 'background 0.2s' }}>
                        <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.88rem' }}>{s.ticker}</td>
                        <td><span style={{ fontSize: '0.75rem', padding: '2px 8px', borderRadius: 4, background: 'var(--surface-2)', color: 'var(--text-secondary)' }}>{s.sector}</span></td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{curr}{s.price?.toLocaleString()}</td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={s.lgbm_alpha >= 0 ? 'pos' : 'neg'}>
                          {(s.lgbm_alpha * 100).toFixed(2)}%
                        </td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }} className={s.kan_alpha >= 0 ? 'pos' : 'neg'}>
                          {(s.kan_alpha * 100).toFixed(2)}%
                        </td>
                        <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 700 }} className={s.final_alpha >= 0 ? 'pos' : 'neg'}>
                          {(s.final_alpha * 100).toFixed(2)}%
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <span style={{
                            padding: '4px 10px', borderRadius: 6, fontSize: '0.72rem', fontWeight: 700, fontFamily: 'var(--font-mono)',
                            background: s.action === 'BUY' ? 'var(--bull-dim)' : s.action === 'SELL' ? 'var(--bear-dim)' : 'var(--surface-2)',
                            color: s.action === 'BUY' ? 'var(--bull)' : s.action === 'SELL' ? 'var(--bear)' : 'var(--text-secondary)',
                            border: `1px solid ${s.action === 'BUY' ? 'rgba(72,187,120,0.3)' : s.action === 'SELL' ? 'rgba(252,92,125,0.3)' : 'transparent'}`
                          }}>
                            {s.action}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
