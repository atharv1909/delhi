import axios from 'axios'

const BASE = '/api'
export const api = axios.create({ baseURL: BASE, headers: { 'Content-Type': 'application/json' } })

export async function submitAnalysis(payload: { nl_goal: string; portfolio: object[] }) {
  const { data } = await api.post('/analyze', payload)
  return data as { job_id: string; status: string }
}
export async function getStatus(jobId: string) {
  const { data } = await api.get(`/status/${jobId}`)
  return data as { job_id: string; status: string; progress: number; message: string; error?: string }
}
export async function getPortfolioResult(jobId: string) {
  const { data } = await api.get(`/portfolio/${jobId}`)
  return data
}
export async function getStocks() {
  const { data } = await api.get('/stocks')
  return data
}
export async function getRegime() {
  const { data } = await api.get('/regime')
  return data
}
export async function runScenario(scenarioType: string, jobId: string) {
  const { data } = await api.post(`/scenario/${scenarioType}`, { job_id: jobId, scenario_type: scenarioType })
  return data
}
// Live mode
export async function startLive() { const { data } = await api.post('/live/start'); return data }
export async function stopLive() { const { data } = await api.post('/live/stop'); return data }
export async function getLiveStatus() { const { data } = await api.get('/live/status'); return data }
export async function getLiveData() { const { data } = await api.get('/live/data'); return data }

export function createLiveWebSocket(onMessage: (d: unknown) => void) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/live`)
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)) } catch {} }
  ws.onerror = () => {}
  return ws
}

export function formatINR(value: number): string {
  if (Math.abs(value) >= 1_00_00_000) return `₹${(value / 1_00_00_000).toFixed(2)}Cr`
  if (Math.abs(value) >= 1_00_000) return `₹${(value / 1_00_000).toFixed(2)}L`
  if (Math.abs(value) >= 1_000) return `₹${(value / 1_000).toFixed(1)}K`
  return `₹${value.toFixed(0)}`
}
export function formatPct(value: number, decimals = 2): string { return `${(value * 100).toFixed(decimals)}%` }
export function formatNum(value: number, decimals = 2): string { return (value || 0).toFixed(decimals) }

export const NIFTY50_TICKERS = [
  'RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS','ICICIBANK.NS',
  'HINDUNILVR.NS','ITC.NS','SBIN.NS','BHARTIARTL.NS','KOTAKBANK.NS',
  'LT.NS','AXISBANK.NS','BAJFINANCE.NS','ASIANPAINT.NS','MARUTI.NS',
  'TITAN.NS','SUNPHARMA.NS','ULTRACEMCO.NS','WIPRO.NS','NTPC.NS',
]
export const SECTORS = [
  'Banking','IT','Energy','FMCG','Pharma','Auto','NBFC','Metals',
  'Infra','Utilities','Telecom','Cement','Consumer','Insurance','Healthcare','Agri',
]
