import { create } from 'zustand'

export interface Holding {
  ticker: string; shares: number; avg_buy_price: number;
  current_price: number | null; sector: string | null;
}
export interface PortfolioInput {
  holdings: Holding[]; total_invested_inr: number;
  cash_inr: number; demat_id: string;
}
export interface JobState {
  job_id: string | null; status: 'idle' | 'queued' | 'running' | 'done' | 'error';
  progress: number; message: string; error: string | null;
}
export interface AlphaSignal {
  ticker: string; kan_alpha: number; lgbm_alpha: number;
  patchtst_alpha: number; il_alpha: number; final_alpha: number;
  shap_data: Record<string, number>; gate_active: boolean;
}
export interface TradeCommand {
  ticker: string; action: 'BUY' | 'SELL' | 'HOLD';
  quantity: number; amount_inr: number; lot_compliant: boolean; reason: string;
}
export interface RiskMetrics {
  var_95: number; var_99: number; cvar_95: number; cvar_99: number;
  max_drawdown: number; portfolio_volatility: number; portfolio_return_expected: number;
  sharpe_ratio: number; sortino_ratio: number; calmar_ratio: number;
  mc_percentile_5: number[]; mc_percentile_50: number[];
  mc_percentile_95: number[]; mc_horizon_days: number;
}
export interface BacktestPeriod {
  start: string; end: string; strategy_return: number; nifty_return: number;
  alpha: number; sharpe: number; sortino: number; calmar: number;
  max_drawdown: number; hit_rate: number; ic: number;
}
export interface BacktestMetrics {
  periods: BacktestPeriod[]; summary_sharpe: number; summary_calmar: number;
  summary_alpha: number; summary_max_drawdown: number; ic_ir: number;
}
export interface PortfolioResult {
  job_id: string;
  regime: { state: string; confidence: number; kelly_factor: number; model_ic: number; gate_status: string; transition_prob: number[]; };
  goal: { return_target: number; max_drawdown: number; sectors_excluded: string[]; capital_inr: number; horizon_days: number; risk_tolerance: string; };
  signals: AlphaSignal[];
  weights: Record<string, number>;
  commands: TradeCommand[];
  risk: RiskMetrics;
  backtest: BacktestMetrics;
  created_at: string;
}
export interface LiveTick { nifty_level: number; india_vix: number; timestamp: string; }
export interface AgentMessage {
  id: string; timestamp: string;
  type: 'info' | 'regime' | 'signal' | 'gate' | 'alert';
  model: string; message: string; value?: number;
}
export interface LiveData {
  stocks: any[]; signals: any[]; regime: any; market: any;
  timestamp: string; stocks_analyzed: number;
}

interface InvestEasyStore {
  nlGoal: string; setNlGoal: (v: string) => void;
  portfolio: PortfolioInput; setPortfolio: (p: PortfolioInput) => void;
  addHolding: (h: Holding) => void; removeHolding: (ticker: string) => void;
  updateHolding: (ticker: string, updates: Partial<Holding>) => void;
  job: JobState; setJob: (j: Partial<JobState>) => void;
  result: PortfolioResult | null; setResult: (r: PortfolioResult | null) => void;
  activeView: 'input' | 'results' | 'live'; setActiveView: (v: 'input' | 'results' | 'live') => void;
  selectedSignal: AlphaSignal | null; setSelectedSignal: (s: AlphaSignal | null) => void;
  liveTick: LiveTick | null; setLiveTick: (t: LiveTick) => void;
  agentMessages: AgentMessage[]; pushAgentMessage: (m: Omit<AgentMessage, 'id' | 'timestamp'>) => void;
  activeResultTab: string; setActiveResultTab: (t: string) => void;
  // Live mode
  liveStatus: 'idle' | 'running' | 'done' | 'error'; setLiveStatus: (s: 'idle' | 'running' | 'done' | 'error') => void;
  liveProgress: number; setLiveProgress: (p: number) => void;
  liveMessage: string; setLiveMessage: (m: string) => void;
  liveData: LiveData | null; setLiveData: (d: LiveData | null) => void;
}

export const useStore = create<InvestEasyStore>((set) => ({
  nlGoal: '',
  setNlGoal: (v) => set({ nlGoal: v }),
  portfolio: { holdings: [], total_invested_inr: 500000, cash_inr: 0, demat_id: '' },
  setPortfolio: (p) => set({ portfolio: p }),
  addHolding: (h) => set((s) => ({ portfolio: { ...s.portfolio, holdings: [...s.portfolio.holdings, h] } })),
  removeHolding: (ticker) => set((s) => ({ portfolio: { ...s.portfolio, holdings: s.portfolio.holdings.filter(h => h.ticker !== ticker) } })),
  updateHolding: (ticker, updates) => set((s) => ({ portfolio: { ...s.portfolio, holdings: s.portfolio.holdings.map(h => h.ticker === ticker ? { ...h, ...updates } : h) } })),
  job: { job_id: null, status: 'idle', progress: 0, message: '', error: null },
  setJob: (j) => set((s) => ({ job: { ...s.job, ...j } })),
  result: null,
  setResult: (r) => set({ result: r }),
  activeView: 'input',
  setActiveView: (v) => set({ activeView: v }),
  selectedSignal: null,
  setSelectedSignal: (s) => set({ selectedSignal: s }),
  liveTick: null,
  setLiveTick: (t) => set({ liveTick: t }),
  agentMessages: [],
  pushAgentMessage: (m) => set((s) => ({
    agentMessages: [{ ...m, id: Math.random().toString(36).slice(2), timestamp: new Date().toISOString() }, ...s.agentMessages].slice(0, 200),
  })),
  activeResultTab: 'overview',
  setActiveResultTab: (t) => set({ activeResultTab: t }),
  liveStatus: 'idle', setLiveStatus: (s) => set({ liveStatus: s }),
  liveProgress: 0, setLiveProgress: (p) => set({ liveProgress: p }),
  liveMessage: '', setLiveMessage: (m) => set({ liveMessage: m }),
  liveData: null, setLiveData: (d) => set({ liveData: d }),
}))
