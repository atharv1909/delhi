"""Full Pipeline Orchestrator.

Called by the rq worker. Runs the complete data→signal→portfolio pipeline
and writes results to Redis for the FastAPI layer to serve.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from quantis.api.schemas import (
    AlphaSignal,
    GateStatus,
    InvestmentGoal,
    PortfolioResult,
    RegimeState,
    RegimeName,
    RiskMetrics,
)
from quantis.config import (
    KELLY_REGIME_FACTORS,
    NIFTY50_TICKERS,
    SECTOR_MAP,
    TRADING_DAYS_YEAR,
)
from quantis.ensemble.efficacy_monitor import EfficacyMonitor
from quantis.ensemble.gating_network import MoEGatingNetwork, combine_expert_alphas
from quantis.ensemble.regime_detector import RegimeDetector
from quantis.ingestion.indicators import build_feature_matrix, compute_indicators
from quantis.ingestion.market_data import (
    fetch_fii_dii_flows,
    fetch_index_data,
    fetch_ohlcv,
    get_current_prices,
    build_fii_zscore,
)
from quantis.ingestion.nl_parser import parse_investment_goal
from quantis.models.lgbm_alpha import LGBMAlphaModel, load_lgbm_model
from quantis.models.kan_alpha import KANAlphaModel, load_kan_model
from quantis.models.mamba_encoder import load_mamba_encoder, encode_sequences
from quantis.models.patchtst_alpha import PatchTSTExpert
from quantis.models.imitation_learner import ImitationLearner
from quantis.portfolio.backtester import run_walk_forward
from quantis.portfolio.optimizer import (
    build_trade_commands,
    kelly_size_positions,
    solve_portfolio,
)
from quantis.portfolio.risk_engine import (
    apply_stress_scenario,
    run_monte_carlo,
    shrink_covariance,
)

logger = logging.getLogger(__name__)

# ── Lookback windows ────────────────────────────────────────────────────────────
DATA_YEARS = 3
_START_DATE = (date.today() - timedelta(days=DATA_YEARS * 365)).isoformat()
_END_DATE = date.today().isoformat()


def _update_progress(redis_client, job_id: str, pct: int, msg: str) -> None:
    redis_client.hset(f"job:{job_id}", mapping={"progress": pct, "message": msg})
    logger.info("[%s] %d%% — %s", job_id, pct, msg)


def run_full_pipeline(
    job_id: str,
    nl_goal: str,
    portfolio_input: list[dict],
    redis_client=None,
) -> dict[str, Any]:
    """Execute the complete QUANTIS pipeline. Returns serialised PortfolioResult."""

    def progress(pct: int, msg: str) -> None:
        if redis_client:
            _update_progress(redis_client, job_id, pct, msg)

    # ── 1. Parse NL goal ──────────────────────────────────────────────────────
    progress(5, "Parsing investment goal...")
    goal = parse_investment_goal(nl_goal)
    logger.info("Goal: %s", goal.model_dump())

    # ── 2. Determine tickers ──────────────────────────────────────────────────
    progress(8, "Fetching market data...")
    if portfolio_input:
        tickers = [t["ticker"] for t in portfolio_input if t.get("ticker")]
    else:
        tickers = NIFTY50_TICKERS[:20]   # Default: top 20 Nifty stocks

    # ── 3. Fetch OHLCV data ───────────────────────────────────────────────────
    ohlcv = fetch_ohlcv(tickers, _START_DATE, _END_DATE, use_cache=True)
    valid_tickers = [t for t in tickers if t in ohlcv and not ohlcv[t].empty]

    if not valid_tickers:
        raise RuntimeError("No valid market data fetched")

    idx_data = fetch_index_data(_START_DATE, _END_DATE)
    fii_raw = fetch_fii_dii_flows()
    fii_zscore = build_fii_zscore(fii_raw) if not fii_raw.empty else None
    progress(15, f"Fetched data for {len(valid_tickers)} stocks")

    # ── 4. Mamba encoding ─────────────────────────────────────────────────────
    progress(20, "Running Mamba encoder...")
    mamba_result = load_mamba_encoder()
    mamba_latents: dict[str, pd.DataFrame] | None = None
    if mamba_result is not None:
        mamba_model, mamba_scaler = mamba_result
        mamba_latents = encode_sequences({t: ohlcv[t] for t in valid_tickers}, mamba_model, mamba_scaler)
    else:
        logger.warning("Mamba model not found — skipping latent features")

    # ── 5. Build feature matrix ────────────────────────────────────────────────
    progress(28, "Computing technical indicators & features...")
    X, y = build_feature_matrix(
        {t: ohlcv[t] for t in valid_tickers},
        mamba_latents=mamba_latents,
        label_horizon=5,
    )

    if X.empty:
        raise RuntimeError("Feature matrix is empty")

    # ── 6. Load / run alpha models ─────────────────────────────────────────────
    progress(35, "Generating alpha signals...")

    lgbm = load_lgbm_model()
    kan = load_kan_model()
    patchtst = PatchTSTExpert.load()
    il_model = ImitationLearner.load()

    # Per-ticker latest features (last row per ticker)
    per_ticker_features: dict[str, pd.DataFrame] = {}
    for ticker in valid_tickers:
        if ticker not in ohlcv:
            continue
        try:
            df = ohlcv[ticker]
            ind = compute_indicators(df)
            ta_cols = [c for c in X.columns if c in ind.columns or c.startswith("mamba_")]
            feat_row = ind[ta_cols].fillna(0).iloc[[-1]]   # last row
            if mamba_latents and ticker in mamba_latents:
                lat_row = mamba_latents[ticker].iloc[[-1]]
                lat_row.index = feat_row.index
                feat_row = pd.concat([feat_row, lat_row], axis=1)
            per_ticker_features[ticker] = feat_row
        except Exception as exc:
            logger.warning("Feature extraction failed for %s: %s", ticker, exc)

    # Get predictions from each expert
    lgbm_alphas: dict[str, float] = {}
    kan_alphas: dict[str, float] = {}
    il_alphas: dict[str, float] = {}

    for ticker, feat_row in per_ticker_features.items():
        if lgbm is not None:
            try:
                lgbm_alphas[ticker] = float(lgbm.predict(feat_row)[0])
            except Exception:
                lgbm_alphas[ticker] = 0.0

        if kan is not None:
            try:
                kan_alphas[ticker] = float(kan.predict(feat_row)[0])
            except Exception:
                kan_alphas[ticker] = 0.0

        if il_model is not None:
            try:
                il_alphas[ticker] = float(il_model.predict(feat_row)[0])
            except Exception:
                il_alphas[ticker] = 0.0

    # PatchTST panel prediction
    nifty_recent_return = float(idx_data["nifty_return"].tail(5).sum())
    patchtst_alphas: dict[str, float] = {}
    if patchtst is not None:
        patchtst_alphas = patchtst.predict_alpha(
            {t: ohlcv[t] for t in valid_tickers}, nifty_5d_return=nifty_recent_return
        )

    progress(48, "Detecting market regime...")

    # ── 7. Regime detection ───────────────────────────────────────────────────
    regime_detector = RegimeDetector.load()
    if regime_detector is None:
        logger.warning("HMM not trained — defaulting to ranging regime")
        regime_info = {"state": "ranging", "confidence": 0.5, "kelly_factor": 0.5, "transition_probs": []}
    else:
        regime_info = regime_detector.predict_current(idx_data, fii_zscore)

    regime_name = regime_info["state"]
    kelly_factor = regime_info["kelly_factor"]
    progress(55, f"Regime: {regime_name} (Kelly={kelly_factor})")

    # ── 8. MoE gating ─────────────────────────────────────────────────────────
    progress(58, "Running MoE gating network...")
    gating = MoEGatingNetwork.load()

    # Build regime feature vector for gating
    try:
        nifty_ret_20 = float(idx_data["nifty_return"].tail(20).sum())
        nifty_vol_20 = float(idx_data["nifty_return"].tail(20).std() * np.sqrt(252))
        vix_pct = float(idx_data.get("vix_percentile", pd.Series([0.5])).iloc[-1])
        fii_z = float(fii_zscore.iloc[-1]) if fii_zscore is not None and not fii_zscore.empty else 0.0
        regime_feat_vec = np.array([nifty_ret_20, nifty_vol_20, vix_pct, fii_z], dtype=np.float32)
    except Exception:
        regime_feat_vec = np.zeros(4, dtype=np.float32)

    if gating is not None:
        gate_weights, gate_confidence = gating.predict_weights(regime_feat_vec)
    else:
        gate_weights = np.ones(4) / 4
        gate_confidence = 0.25

    # ── 9. Combine alphas per ticker ──────────────────────────────────────────
    progress(62, "Combining expert signals...")
    final_alphas: dict[str, float] = {}
    shap_data_per_ticker: dict[str, dict[str, float]] = {}

    for ticker in valid_tickers:
        expert_a = {
            "kan": kan_alphas.get(ticker, 0.0),
            "lgbm": lgbm_alphas.get(ticker, 0.0),
            "patchtst": patchtst_alphas.get(ticker, 0.0),
            "il": il_alphas.get(ticker, 0.0),
        }
        final_alphas[ticker] = combine_expert_alphas(expert_a, gate_weights, gate_confidence)

        # SHAP for LightGBM (fast TreeExplainer)
        if lgbm is not None and ticker in per_ticker_features:
            try:
                shap_data_per_ticker[ticker] = lgbm.top_shap_features(per_ticker_features[ticker], top_n=10)
            except Exception:
                shap_data_per_ticker[ticker] = {}

    # ── 10. Efficacy monitor ──────────────────────────────────────────────────
    progress(65, "Checking model efficacy gate...")
    monitor = EfficacyMonitor()
    today_str = date.today().isoformat()
    monitor.record_predictions(today_str, final_alphas)
    gate_status = monitor.get_gate_status()
    current_ic = monitor.get_current_ic()

    # ── 11. Portfolio optimization ────────────────────────────────────────────
    progress(70, "Optimising portfolio...")

    excluded = [s.title() for s in goal.sectors_excluded]
    investable = [
        t for t in valid_tickers
        if SECTOR_MAP.get(t, "Unknown").title() not in excluded
    ]

    if not investable:
        investable = valid_tickers[:5]

    n = len(investable)
    exp_returns = np.array([final_alphas.get(t, 0.0) for t in investable])

    # Daily returns matrix for covariance
    ret_df = pd.DataFrame({
        t: ohlcv[t]["Close"].pct_change().dropna()
        for t in investable if t in ohlcv
    }).dropna()
    cov_matrix = shrink_covariance(ret_df)

    # Monte Carlo scenarios for CVaR
    mu_daily = ret_df.mean().reindex(investable, fill_value=0.0).values
    rng = np.random.default_rng(42)
    mc_scenarios = rng.multivariate_normal(mu_daily, cov_matrix, size=1000)
    mc_scenarios = np.clip(mc_scenarios, -0.15, 0.15)  # NSE circuit breaker

    prices = get_current_prices(investable)
    opt_result = solve_portfolio(
        investable, exp_returns, cov_matrix, mc_scenarios, goal, prices
    )
    raw_weights = opt_result["weights"]

    progress(78, "Applying Kelly sizing...")
    daily_vols = {t: float(ret_df[t].std()) for t in investable if t in ret_df.columns}
    sized_weights = kelly_size_positions(
        raw_weights,
        {t: final_alphas.get(t, 0.0) for t in investable},
        daily_vols,
        kelly_factor,
        goal.capital_inr,
    )

    # ── 12. Trade commands ────────────────────────────────────────────────────
    trade_commands = build_trade_commands(sized_weights, goal.capital_inr, prices)

    # ── 13. Risk metrics via Monte Carlo ──────────────────────────────────────
    progress(82, "Running Monte Carlo risk engine...")
    w_vec = np.array([sized_weights.get(t, 0.0) for t in investable])
    w_vec /= w_vec.sum() + 1e-10

    mc_result = run_monte_carlo(
        weights=w_vec,
        mu=mu_daily,
        cov=cov_matrix,
        horizon_days=min(goal.horizon_days, 252),
        capital_inr=goal.capital_inr,
        regime_name=regime_name,
    )

    # ── 14. Backtest ──────────────────────────────────────────────────────────
    progress(88, "Running walk-forward backtest...")

    def simple_signal_fn(X_tr, y_tr, X_te):
        """Fallback signal function for backtest using LightGBM."""
        if lgbm is None or X_tr.shape[0] < 50:
            return np.zeros(len(X_te))
        import lightgbm as lgb_lib
        m = lgb_lib.LGBMRegressor(n_estimators=100, learning_rate=0.05, verbose=-1)
        m.fit(X_tr, y_tr)
        return m.predict(X_te)

    nifty_daily = idx_data["nifty_return"].reindex(X.index, fill_value=0.0)
    backtest_metrics = run_walk_forward(simple_signal_fn, X, y, nifty_daily)

    # ── 15. Assemble result ───────────────────────────────────────────────────
    progress(95, "Assembling portfolio result...")

    signals = [
        AlphaSignal(
            ticker=t,
            kan_alpha=round(kan_alphas.get(t, 0.0), 6),
            lgbm_alpha=round(lgbm_alphas.get(t, 0.0), 6),
            patchtst_alpha=round(patchtst_alphas.get(t, 0.0), 6),
            il_alpha=round(il_alphas.get(t, 0.0), 6),
            final_alpha=round(final_alphas.get(t, 0.0), 6),
            shap_data=shap_data_per_ticker.get(t, {}),
            gate_active=gate_status == GateStatus.active,
        )
        for t in valid_tickers
    ]

    regime_state = RegimeState(
        state=RegimeName(regime_name),
        confidence=round(regime_info.get("confidence", 0.5), 4),
        kelly_factor=kelly_factor,
        model_ic=round(current_ic, 4),
        gate_status=gate_status,
        transition_prob=regime_info.get("transition_probs", []),
    )

    risk_metrics = RiskMetrics(**mc_result)

    result = PortfolioResult(
        job_id=job_id,
        regime=regime_state,
        goal=goal,
        signals=signals,
        weights={k: round(v, 4) for k, v in sized_weights.items()},
        commands=trade_commands,
        risk=risk_metrics,
        backtest=backtest_metrics,
    )

    progress(100, "Done")
    return result.model_dump(mode="json")
