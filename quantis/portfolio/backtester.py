"""Walk-Forward Backtester using vectorbt.

Honest walk-forward methodology: train on 252 days, test 63, step 21.
No lookahead. Reports Sharpe, Sortino, Calmar, IC vs NIFTY 50.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

from quantis.api.schemas import BacktestMetrics, BacktestPeriod
from quantis.config import (
    RISK_FREE_RATE_ANNUAL,
    TRADING_DAYS_YEAR,
    WF_EMBARGO_DAYS,
    WF_STEP_DAYS,
    WF_TEST_DAYS,
    WF_TRAIN_DAYS,
)

logger = logging.getLogger(__name__)


def _sharpe(returns: np.ndarray, rf_daily: float = RISK_FREE_RATE_ANNUAL / 252) -> float:
    excess = returns - rf_daily
    if len(excess) < 2 or np.std(excess) < 1e-10:
        return 0.0
    return float(np.mean(excess) / np.std(excess) * np.sqrt(TRADING_DAYS_YEAR))


def _sortino(returns: np.ndarray, rf_daily: float = RISK_FREE_RATE_ANNUAL / 252) -> float:
    excess = returns - rf_daily
    downside = excess[excess < 0]
    if len(downside) < 2 or np.std(downside) < 1e-10:
        return 0.0
    return float(np.mean(excess) / (np.std(downside) * np.sqrt(TRADING_DAYS_YEAR)))


def _max_drawdown(returns: np.ndarray) -> float:
    equity = np.cumprod(1 + returns)
    cum_max = np.maximum.accumulate(equity)
    dd = (equity - cum_max) / (cum_max + 1e-10)
    return float(dd.min())


def _calmar(returns: np.ndarray) -> float:
    ann_ret = float(np.mean(returns) * TRADING_DAYS_YEAR)
    mdd = abs(_max_drawdown(returns))
    return ann_ret / (mdd + 1e-10)


def run_walk_forward(
    signal_fn,              # callable(X_train, y_train, X_test) → predicted_alpha (np.ndarray)
    feature_df: pd.DataFrame,   # (dates, features)
    label_series: pd.Series,    # (dates,) — 5-day forward excess return
    nifty_returns: pd.Series,   # (dates,) — NIFTY 50 daily returns
) -> BacktestMetrics:
    """Run walk-forward backtest. Returns BacktestMetrics."""
    n = len(feature_df)
    min_required = WF_TRAIN_DAYS + WF_TEST_DAYS + WF_EMBARGO_DAYS
    if n < min_required:
        logger.error("Insufficient data for walk-forward (%d < %d)", n, min_required)
        return BacktestMetrics(
            periods=[], summary_sharpe=0.0, summary_calmar=0.0,
            summary_alpha=0.0, summary_max_drawdown=0.0, ic_ir=0.0,
        )

    periods: list[BacktestPeriod] = []
    all_strategy_returns: list[float] = []
    all_ic: list[float] = []

    # Align nifty returns to feature_df index
    nifty_aligned = nifty_returns.reindex(feature_df.index, fill_value=0.0)

    dates = feature_df.index
    start = 0

    while start + WF_TRAIN_DAYS + WF_EMBARGO_DAYS + WF_TEST_DAYS <= n:
        train_end = start + WF_TRAIN_DAYS
        test_start = train_end + WF_EMBARGO_DAYS
        test_end = min(test_start + WF_TEST_DAYS, n)

        X_train = feature_df.iloc[start:train_end].values
        y_train = label_series.iloc[start:train_end].values
        X_test = feature_df.iloc[test_start:test_end].values
        y_test = label_series.iloc[test_start:test_end].values

        if len(X_train) < 50 or len(X_test) < 5:
            start += WF_STEP_DAYS
            continue

        try:
            pred_alpha = signal_fn(X_train, y_train, X_test)
        except Exception as exc:
            logger.warning("signal_fn failed in fold: %s", exc)
            start += WF_STEP_DAYS
            continue

        # Simple long-top-quartile, short-bottom-quartile (long only in this version)
        top_q = np.percentile(pred_alpha, 75)
        long_mask = pred_alpha >= top_q
        if long_mask.sum() == 0:
            start += WF_STEP_DAYS
            continue

        # Equal-weight among top-quartile stocks
        weight = 1.0 / long_mask.sum()
        strategy_excess = y_test[long_mask].mean() if long_mask.any() else 0.0
        nifty_test = nifty_aligned.iloc[test_start:test_end].values
        nifty_period = float(np.prod(1 + nifty_test) - 1)
        strategy_total = strategy_excess + nifty_period

        # Period-level returns (daily approximation)
        period_returns = np.array([strategy_excess / max(len(nifty_test), 1)] * len(nifty_test))
        all_strategy_returns.extend(period_returns.tolist())

        # IC for this period
        if len(pred_alpha) > 2 and np.std(pred_alpha) > 0 and np.std(y_test) > 0:
            ic, _ = pearsonr(pred_alpha, y_test)
            if np.isnan(ic):
                ic = 0.0
        else:
            ic = 0.0
        all_ic.append(ic)

        # Period metrics
        period_ann_ret = strategy_total * (TRADING_DAYS_YEAR / len(nifty_test))
        nifty_ann = nifty_period * (TRADING_DAYS_YEAR / len(nifty_test))
        alpha = period_ann_ret - nifty_ann
        mdd = _max_drawdown(period_returns)
        sharpe = _sharpe(period_returns)
        sortino = _sortino(period_returns)
        calmar = _calmar(period_returns)
        hit_rate = float((y_test[long_mask] > 0).mean()) if long_mask.any() else 0.0

        periods.append(BacktestPeriod(
            start=str(dates[test_start].date()),
            end=str(dates[test_end - 1].date()),
            strategy_return=round(period_ann_ret, 4),
            nifty_return=round(nifty_ann, 4),
            alpha=round(alpha, 4),
            sharpe=round(sharpe, 3),
            sortino=round(sortino, 3),
            calmar=round(calmar, 3),
            max_drawdown=round(mdd, 4),
            hit_rate=round(hit_rate, 3),
            ic=round(ic, 4),
        ))

        start += WF_STEP_DAYS

    if not periods:
        return BacktestMetrics(
            periods=[], summary_sharpe=0.0, summary_calmar=0.0,
            summary_alpha=0.0, summary_max_drawdown=0.0, ic_ir=0.0,
        )

    all_ret = np.array(all_strategy_returns)
    ic_arr = np.array(all_ic)

    return BacktestMetrics(
        periods=periods,
        summary_sharpe=round(_sharpe(all_ret), 3),
        summary_calmar=round(_calmar(all_ret), 3),
        summary_alpha=round(float(np.mean([p.alpha for p in periods])), 4),
        summary_max_drawdown=round(_max_drawdown(all_ret), 4),
        ic_ir=round(float(np.mean(ic_arr) / (np.std(ic_arr) + 1e-8)), 3),
    )
