"""Monte Carlo Risk Engine.

10,000 simulation paths using Cholesky-decomposed covariance.
Regime-adjusted drift. VaR/CVaR. Causal shock propagation.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy.linalg import cholesky, cho_factor, cho_solve
from sklearn.covariance import LedoitWolf

from quantis.api.schemas import RiskMetrics
from quantis.config import MC_N_PATHS, RISK_FREE_RATE_DAILY, TRADING_DAYS_YEAR, VAR_CONFIDENCE

logger = logging.getLogger(__name__)

# Stress scenario shocks: {scenario: {sector_or_ticker: shock_magnitude}}
STRESS_SCENARIOS: dict[str, dict[str, float]] = {
    "2008": {
        "Banking": -0.55, "NBFC": -0.50, "Energy": -0.40,
        "IT": -0.30, "FMCG": -0.15, "Pharma": -0.10,
    },
    "covid": {
        "Aviation": -0.70, "Hotels": -0.65, "Auto": -0.40,
        "Banking": -0.35, "IT": 0.20, "Pharma": 0.15, "Telecom": 0.10,
    },
    "rate_hike_2022": {
        "NBFC": -0.35, "Banking": -0.20, "IT": -0.30,
        "Utilities": 0.05, "Energy": 0.10,
    },
}


def shrink_covariance(returns: pd.DataFrame) -> np.ndarray:
    """Compute Ledoit-Wolf shrunk covariance matrix."""
    clean = returns.dropna(axis=1, how="any").dropna()
    if clean.empty or clean.shape[1] < 2:
        return np.eye(returns.shape[1]) * 0.0001
    lw = LedoitWolf()
    lw.fit(clean.values)
    n_full = returns.shape[1]
    tickers_clean = list(clean.columns)
    cov_full = np.eye(n_full) * 0.0001
    for i, ti in enumerate(returns.columns):
        for j, tj in enumerate(returns.columns):
            if ti in tickers_clean and tj in tickers_clean:
                ii = tickers_clean.index(ti)
                jj = tickers_clean.index(tj)
                cov_full[i, j] = lw.covariance_[ii, jj]
    return cov_full


def run_monte_carlo(
    weights: np.ndarray,               # (n_assets,)
    mu: np.ndarray,                    # (n_assets,) daily expected returns
    cov: np.ndarray,                   # (n_assets, n_assets)
    horizon_days: int,
    capital_inr: float,
    regime_name: str = "bull",
    n_paths: int = MC_N_PATHS,
) -> dict[str, Any]:
    """Run MC simulation. Returns path statistics and risk metrics."""
    n_assets = len(weights)

    # Regime-adjusted drift and covariance
    regime_multipliers = {
        "bull": (1.0, 1.0),
        "ranging": (0.5, 1.0),
        "bear": (0.3, 1.3),
        "high_vol": (0.0, 2.0),
    }
    ret_mult, vol_mult = regime_multipliers.get(regime_name, (1.0, 1.0))
    mu_adj = mu * ret_mult
    cov_adj = cov * (vol_mult ** 2)

    # Cholesky decomposition
    try:
        # Add small regularisation for numerical stability
        reg_cov = cov_adj + np.eye(n_assets) * 1e-6
        L = cholesky(reg_cov, lower=True)
    except np.linalg.LinAlgError:
        logger.warning("Covariance not PD; using diagonal only")
        L = np.diag(np.sqrt(np.maximum(np.diag(cov_adj), 1e-6)))

    # Simulate paths: (n_assets, n_paths, horizon)
    rng = np.random.default_rng(seed=42)
    Z = rng.standard_normal((n_paths, n_assets, horizon_days))
    dR = mu_adj[None, :, None] + np.einsum("ij,njt->nit", L, Z)
    # dR: (n_paths, n_assets, horizon_days)


    # Portfolio returns per path per day
    port_ret = np.einsum("a,nah->nh", weights, dR)  # (n_paths, horizon)

    # Cumulative portfolio value paths
    port_value = capital_inr * np.cumprod(1 + port_ret, axis=1)  # (n_paths, horizon)

    # Percentile paths
    p5 = np.percentile(port_value, 5, axis=0).tolist()
    p50 = np.percentile(port_value, 50, axis=0).tolist()
    p95 = np.percentile(port_value, 95, axis=0).tolist()

    # Terminal return distribution
    terminal_returns = (port_value[:, -1] / capital_inr) - 1

    # VaR and CVaR
    var_95 = float(np.percentile(terminal_returns, (1 - VAR_CONFIDENCE) * 100))
    cvar_95 = float(terminal_returns[terminal_returns <= var_95].mean())
    var_99 = float(np.percentile(terminal_returns, 1.0))
    cvar_99 = float(terminal_returns[terminal_returns <= var_99].mean())

    # Max drawdown per path, then distribution
    cum_max = np.maximum.accumulate(port_value, axis=1)
    drawdowns = (port_value - cum_max) / (cum_max + 1e-10)
    max_dd_per_path = drawdowns.min(axis=1)
    median_max_dd = float(np.median(max_dd_per_path))

    # Expected portfolio metrics
    daily_port_ret = np.einsum("a,nah->nh", weights, dR).mean(axis=0)
    ann_return = float(np.mean(daily_port_ret) * TRADING_DAYS_YEAR)
    ann_vol = float(np.std(daily_port_ret) * np.sqrt(TRADING_DAYS_YEAR))
    sharpe = (ann_return - 0.071) / (ann_vol + 1e-8)
    downside = daily_port_ret[daily_port_ret < 0]
    sortino = (ann_return - 0.071) / (np.std(downside) * np.sqrt(TRADING_DAYS_YEAR) + 1e-8) if len(downside) > 1 else 0.0
    calmar = ann_return / (abs(median_max_dd) + 1e-8)

    return {
        "var_95": var_95,
        "var_99": var_99,
        "cvar_95": cvar_95,
        "cvar_99": cvar_99,
        "max_drawdown": median_max_dd,
        "portfolio_volatility": ann_vol,
        "portfolio_return_expected": ann_return,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "mc_percentile_5": p5,
        "mc_percentile_50": p50,
        "mc_percentile_95": p95,
        "mc_horizon_days": horizon_days,
    }


def apply_stress_scenario(
    scenario_type: str,
    weights: dict[str, float],
    sector_map: dict[str, str],
    base_mu: dict[str, float],
    custom_shocks: dict[str, float] | None = None,
) -> dict[str, float]:
    """Apply stress scenario shocks to expected returns.

    Returns {ticker: shocked_return} dict.
    """
    if scenario_type == "custom" and custom_shocks:
        shocks = custom_shocks
    else:
        shocks = STRESS_SCENARIOS.get(scenario_type, {})

    shocked_returns: dict[str, float] = {}
    for ticker, mu in base_mu.items():
        sector = sector_map.get(ticker, "Unknown")
        shock = shocks.get(ticker, shocks.get(sector, 0.0))
        shocked_returns[ticker] = mu + shock   # additive shock

    return shocked_returns
