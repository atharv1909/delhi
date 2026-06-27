"""Mean-CVaR Portfolio Optimizer with SEBI Constraints.

Uses cvxpy to solve a Mean-CVaR problem subject to:
  - Long-only (no shorting)
  - Max 20% single-stock weight
  - Max 35% sector weight
  - Excluded sectors from NL parser
  - SEBI lot-size compliance
  - Volatility constraint from user's max_drawdown input
"""
from __future__ import annotations

import logging
from typing import Any

import cvxpy as cp
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from quantis.api.schemas import InvestmentGoal, RiskTolerance, TradeAction, TradeCommand
from quantis.config import (
    MAX_SECTOR_WEIGHT,
    MAX_SINGLE_STOCK_WEIGHT,
    MC_N_PATHS,
    SECTOR_MAP,
    TRADING_DAYS_YEAR,
)

logger = logging.getLogger(__name__)

# Approximate NSE F&O lot sizes (units per contract)
NSE_LOT_SIZES: dict[str, int] = {
    "RELIANCE.NS": 250, "TCS.NS": 150, "HDFCBANK.NS": 550,
    "INFY.NS": 300, "ICICIBANK.NS": 700, "NIFTY": 50, "BANKNIFTY": 15,
}
DEFAULT_LOT_SIZE = 1  # Equity delivery — no lot size constraint


def _risk_lambda(goal: InvestmentGoal) -> float:
    """Map risk tolerance to CVaR lambda."""
    return {
        RiskTolerance.aggressive: 0.5,
        RiskTolerance.moderate: 2.0,
        RiskTolerance.conservative: 5.0,
    }[goal.risk_tolerance]


def _max_vol_from_drawdown(max_drawdown: float, horizon_days: int) -> float:
    """Approximate max acceptable daily volatility from drawdown target.

    Using: max_drawdown ≈ vol * sqrt(horizon) * 2.33 (99% confidence)
    """
    horizon_years = horizon_days / TRADING_DAYS_YEAR
    approx_daily_vol = max_drawdown / (2.33 * np.sqrt(horizon_years * TRADING_DAYS_YEAR))
    return max(approx_daily_vol, 0.005)   # floor at 0.5% daily vol


def solve_portfolio(
    tickers: list[str],
    expected_returns: np.ndarray,   # (n,) — MoE final alphas
    cov_matrix: np.ndarray,         # (n, n) — shrunk covariance
    scenarios: np.ndarray,          # (n_scenarios, n) — MC return scenarios
    goal: InvestmentGoal,
    prices: dict[str, float],
) -> dict[str, Any]:
    """Solve Mean-CVaR optimisation. Returns weights dict and metadata."""
    n = len(tickers)
    assert expected_returns.shape == (n,)
    assert cov_matrix.shape == (n, n)
    assert scenarios.shape[1] == n

    n_scenarios = scenarios.shape[0]
    alpha_cvar = 0.95
    lam = _risk_lambda(goal)
    max_vol = _max_vol_from_drawdown(goal.max_drawdown, goal.horizon_days)

    # ── CVaR via Rockafellar-Uryasev reformulation ─────────────────────────
    w = cp.Variable(n, nonneg=True)          # weights
    z = cp.Variable(n_scenarios, nonneg=True)  # CVaR auxiliary
    xi = cp.Variable()                         # VaR threshold

    port_returns = scenarios @ w              # (n_scenarios,)
    portfolio_return = expected_returns @ w
    cvar = xi + (1 / ((1 - alpha_cvar) * n_scenarios)) * cp.sum(z)
    objective = cp.Maximize(portfolio_return - lam * cvar)

    constraints = [
        cp.sum(w) == 1,
        z >= -port_returns - xi,
    ]

    # Max single stock
    for i in range(n):
        constraints.append(w[i] <= MAX_SINGLE_STOCK_WEIGHT)

    # Sector caps
    sectors = [SECTOR_MAP.get(t, "Unknown") for t in tickers]
    unique_sectors = set(sectors)
    for sector in unique_sectors:
        if sector in (s.title() for s in goal.sectors_excluded):
            for i, t in enumerate(tickers):
                if sectors[i] == sector:
                    constraints.append(w[i] == 0)
        else:
            sector_idx = [i for i, s in enumerate(sectors) if s == sector]
            if sector_idx:
                constraints.append(cp.sum(w[sector_idx]) <= MAX_SECTOR_WEIGHT)

    # Portfolio volatility constraint
    port_var = cp.quad_form(w, cov_matrix)
    constraints.append(cp.sqrt(port_var) <= max_vol)

    problem = cp.Problem(objective, constraints)

    # Try ECOS first, fallback to SCS
    for solver in [cp.ECOS, cp.SCS]:
        try:
            problem.solve(solver=solver, warm_start=True, verbose=False)
            if problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
                break
        except Exception as exc:
            logger.warning("Solver %s failed: %s", solver, exc)

    if w.value is None:
        logger.error("Portfolio optimization failed. Returning equal weights.")
        raw_weights = np.ones(n) / n
    else:
        raw_weights = np.maximum(w.value, 0)
        raw_weights /= raw_weights.sum() + 1e-10   # re-normalize

    weights = {ticker: float(raw_weights[i]) for i, ticker in enumerate(tickers)}
    return {
        "weights": weights,
        "cvar_obj": float(problem.value) if problem.value is not None else 0.0,
        "status": problem.status or "failed",
    }


def kelly_size_positions(
    weights: dict[str, float],
    expected_returns: dict[str, float],
    daily_vols: dict[str, float],
    kelly_factor: float,
    capital_inr: float,
) -> dict[str, float]:
    """Apply fractional Kelly sizing on top of CVaR weights.

    Returns {ticker: capital_fraction} capped at 20% per stock.
    """
    risk_free = 0.071 / 252   # daily
    kelly_fracs: dict[str, float] = {}

    for ticker, w in weights.items():
        if w < 1e-4:
            kelly_fracs[ticker] = 0.0
            continue
        mu = expected_returns.get(ticker, 0.0) / 252   # daily excess
        sigma = daily_vols.get(ticker, 0.01)
        f_star = (mu - risk_free) / (sigma ** 2 + 1e-10)
        f_actual = f_star * kelly_factor
        # Hard cap per spec
        f_capped = max(0.0, min(f_actual, MAX_SINGLE_STOCK_WEIGHT))
        kelly_fracs[ticker] = f_capped

    # Renormalise to sum ≤ 1
    total = sum(kelly_fracs.values())
    if total > 1.0:
        kelly_fracs = {k: v / total for k, v in kelly_fracs.items()}

    return kelly_fracs


def build_trade_commands(
    weights: dict[str, float],
    capital_inr: float,
    prices: dict[str, float],
    current_weights: dict[str, float] | None = None,
) -> list[TradeCommand]:
    """Convert weight targets to BUY/SELL/HOLD commands with lot compliance."""
    commands = []
    current = current_weights or {}

    for ticker, target_w in weights.items():
        price = prices.get(ticker, 0.0)
        if price <= 0:
            continue

        target_inr = target_w * capital_inr
        quantity = int(target_inr // price)

        current_w = current.get(ticker, 0.0)
        diff = target_w - current_w

        if abs(diff) < 0.005:
            action = TradeAction.HOLD
        elif diff > 0:
            action = TradeAction.BUY
        else:
            action = TradeAction.SELL

        lot_size = NSE_LOT_SIZES.get(ticker, DEFAULT_LOT_SIZE)
        lot_compliant = (quantity % lot_size == 0) or lot_size == 1

        commands.append(TradeCommand(
            ticker=ticker,
            action=action,
            quantity=quantity,
            amount_inr=round(quantity * price, 2),
            lot_compliant=lot_compliant,
            reason=f"Target weight: {target_w:.2%}, Current: {current_w:.2%}",
        ))

    return commands
