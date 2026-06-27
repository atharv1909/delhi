import { useStore } from '../store/useStore'
import RegimePanel from '../components/dashboard/RegimePanel'
import OverviewKPIs from '../components/dashboard/OverviewKPIs'
import AlphaTable from '../components/dashboard/AlphaTable'
import ShapWaterfall from '../components/dashboard/ShapWaterfall'
import MonteCarloChart from '../components/dashboard/MonteCarloChart'
import PortfolioWeights from '../components/dashboard/PortfolioWeights'
import BacktestReport from '../components/dashboard/BacktestReport'
import AgentBus from '../components/dashboard/AgentBus'
import TradeCommands from '../components/dashboard/TradeCommands'
import CausalGraph from '../components/dashboard/CausalGraph'

const TABS = [
  { id: 'overview', label: 'Overview & Allocation' },
  { id: 'signals', label: 'Alpha Signals & SHAP' },
  { id: 'portfolio', label: 'Trade Commands' },
  { id: 'risk', label: 'Monte Carlo Simulation' },
  { id: 'backtest', label: 'Walk-Forward Backtest' },
  { id: 'network', label: 'Causal Graph' },
  { id: 'live', label: 'Agent Feed' },
]

export default function ResultsPage() {
  const { result, activeResultTab, setActiveResultTab, selectedSignal } = useStore()

  if (!result) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: 450, color: 'var(--text-muted)', gap: 16 }}>
        <div style={{ fontSize: '2.5rem' }}>📈</div>
        <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-secondary)' }}>No analysis results generated yet</div>
        <p style={{ fontSize: '0.9rem', maxWidth: 400, textAlign: 'center' }}>Go to Analyze Portfolio to submit your natural language goal and generate multi-model intelligence.</p>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 1320, margin: '0 auto', paddingTop: 24 }} className="fade-in">
      {/* Regime + KPIs header */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 360px) 1fr', gap: 20, marginBottom: 24 }}>
        <RegimePanel regime={result.regime} />
        <OverviewKPIs result={result} />
      </div>

      {/* Tabs */}
      <div className="nav-tabs">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveResultTab(t.id)}
            className={`nav-tab ${activeResultTab === t.id ? 'active' : ''}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="fade-in" key={activeResultTab}>
        {activeResultTab === 'overview' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <MonteCarloChart risk={result.risk} goal={result.goal} />
            <PortfolioWeights weights={result.weights} commands={result.commands} goal={result.goal} />
          </div>
        )}

        {activeResultTab === 'signals' && (
          <div style={{ display: 'grid', gridTemplateColumns: selectedSignal ? '1.3fr 1fr' : '1fr', gap: 20, transition: 'all 0.2s' }}>
            <AlphaTable signals={result.signals} />
            {selectedSignal && <ShapWaterfall signal={selectedSignal} />}
          </div>
        )}

        {activeResultTab === 'portfolio' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr', gap: 20 }}>
            <PortfolioWeights weights={result.weights} commands={result.commands} goal={result.goal} large />
            <TradeCommands commands={result.commands} />
          </div>
        )}

        {activeResultTab === 'risk' && (
          <MonteCarloChart risk={result.risk} goal={result.goal} large />
        )}

        {activeResultTab === 'backtest' && (
          <BacktestReport backtest={result.backtest} />
        )}

        {activeResultTab === 'network' && (
          <CausalGraph signals={result.signals} weights={result.weights} />
        )}

        {activeResultTab === 'live' && (
          <AgentBus />
        )}
      </div>
    </div>
  )
}
