"""Pydantic schemas for all API contracts — Extended for full portfolio input."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────────────

class RiskTolerance(str, Enum):
    conservative = "conservative"
    moderate = "moderate"
    aggressive = "aggressive"


class RegimeName(str, Enum):
    bull = "bull"
    bear = "bear"
    high_vol = "high_vol"
    ranging = "ranging"


class GateStatus(str, Enum):
    active = "active"
    degraded = "degraded"
    blocked = "blocked"


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


# ── Portfolio Input (from user) ────────────────────────────────────────────────

class HoldingInput(BaseModel):
    """A single stock holding in the user's existing portfolio."""
    ticker: str = Field(..., description="NSE ticker e.g. RELIANCE.NS")
    shares: float = Field(..., gt=0, description="Number of shares held")
    avg_buy_price: float = Field(..., gt=0, description="Average purchase price in INR")
    current_price: float | None = Field(None, description="Current market price (fetched if not provided)")
    sector: str | None = Field(None, description="Sector override (auto-detected from SECTOR_MAP if blank)")

    @property
    def current_value_inr(self) -> float:
        price = self.current_price or self.avg_buy_price
        return self.shares * price

    @property
    def cost_basis_inr(self) -> float:
        return self.shares * self.avg_buy_price

    @property
    def unrealised_pnl_inr(self) -> float:
        return self.current_value_inr - self.cost_basis_inr

    @property
    def unrealised_pnl_pct(self) -> float:
        if self.cost_basis_inr == 0:
            return 0.0
        return self.unrealised_pnl_inr / self.cost_basis_inr


class PortfolioInput(BaseModel):
    """Full portfolio submitted by the user."""
    holdings: list[HoldingInput] = Field(default_factory=list)
    total_invested_inr: float = Field(..., gt=0, description="Total capital deployed (INR)")
    cash_inr: float = Field(default=0.0, ge=0, description="Uninvested cash (INR)")
    demat_id: str | None = Field(None, description="Optional broker/demat identifier")

    @property
    def total_current_value(self) -> float:
        return sum(h.current_value_inr for h in self.holdings) + self.cash_inr

    @property
    def weight_map(self) -> dict[str, float]:
        total = self.total_current_value or 1.0
        return {h.ticker: h.current_value_inr / total for h in self.holdings}


# ── Core Domain Objects ────────────────────────────────────────────────────────

class InvestmentGoal(BaseModel):
    return_target: float = Field(..., ge=0.0, le=5.0)
    max_drawdown: float = Field(..., ge=0.0, le=1.0)
    sectors_excluded: list[str] = Field(default_factory=list)
    capital_inr: float = Field(..., gt=0)
    horizon_days: int = Field(..., gt=0, le=3650)
    risk_tolerance: RiskTolerance = RiskTolerance.moderate

    @field_validator("return_target")
    @classmethod
    def clamp_return_target(cls, v: float) -> float:
        return min(v, 2.0)

    @field_validator("max_drawdown")
    @classmethod
    def clamp_drawdown(cls, v: float) -> float:
        return min(v, 0.99)


class TickerWeight(BaseModel):
    ticker: str
    weight: float = Field(..., ge=0.0, le=1.0)


class AnalyzeRequest(BaseModel):
    nl_goal: str = Field(..., min_length=10, max_length=2000, description="Natural language investment goal")
    portfolio: list[PortfolioInput] = Field(default_factory=list)
    parsed_goal: InvestmentGoal | None = Field(None, description="Optional pre-parsed goal override")


class AlphaSignal(BaseModel):
    ticker: str
    kan_alpha: float
    lgbm_alpha: float
    patchtst_alpha: float
    il_alpha: float
    final_alpha: float
    shap_data: dict[str, float] = Field(default_factory=dict)
    gate_active: bool = True


class RegimeState(BaseModel):
    state: RegimeName
    confidence: float = Field(..., ge=0.0, le=1.0)
    kelly_factor: float = Field(..., ge=0.0, le=1.0)
    model_ic: float
    gate_status: GateStatus
    transition_prob: list[float] = Field(default_factory=list)


class TradeCommand(BaseModel):
    ticker: str
    action: TradeAction
    quantity: int
    amount_inr: float
    lot_compliant: bool
    reason: str = ""


class RiskMetrics(BaseModel):
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    max_drawdown: float
    portfolio_volatility: float
    portfolio_return_expected: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    mc_percentile_5: list[float]
    mc_percentile_50: list[float]
    mc_percentile_95: list[float]
    mc_horizon_days: int


class BacktestPeriod(BaseModel):
    start: str
    end: str
    strategy_return: float
    nifty_return: float
    alpha: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    hit_rate: float
    ic: float


class BacktestMetrics(BaseModel):
    periods: list[BacktestPeriod]
    summary_sharpe: float
    summary_calmar: float
    summary_alpha: float
    summary_max_drawdown: float
    ic_ir: float


class PortfolioResult(BaseModel):
    job_id: str
    regime: RegimeState
    goal: InvestmentGoal
    signals: list[AlphaSignal]
    weights: dict[str, float]
    commands: list[TradeCommand]
    risk: RiskMetrics
    backtest: BacktestMetrics
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── API Response Wrappers ──────────────────────────────────────────────────────

class AnalyzeResponse(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.queued


class StatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = Field(0, ge=0, le=100)
    message: str = ""
    error: str | None = None


class StockInfo(BaseModel):
    ticker: str
    name: str
    sector: str
    price: float
    return_1d: float
    return_5d: float
    return_20d: float
    volume: int


class StocksResponse(BaseModel):
    stocks: list[StockInfo]
    nifty_50_level: float
    india_vix: float
    timestamp: datetime


class ScenarioRequest(BaseModel):
    job_id: str
    scenario_type: str = Field(..., pattern="^(2008|covid|rate_hike_2022|custom)$")
    custom_shock: dict[str, float] | None = None


class ScenarioResult(BaseModel):
    scenario_type: str
    baseline_cvar: float
    shocked_cvar: float
    baseline_max_dd: float
    shocked_max_dd: float
    contagion_path: dict[str, float]


# ── WebSocket Message Types ────────────────────────────────────────────────────

class WsMessageType(str, Enum):
    regime_update = "regime_update"
    price_tick = "price_tick"
    agent_message = "agent_message"
    ic_update = "ic_update"
    gate_alert = "gate_alert"


class WsMessage(BaseModel):
    type: WsMessageType
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
