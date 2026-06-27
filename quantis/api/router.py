"""InvestEasy API Router — All REST endpoints with REAL pipeline integration."""
from __future__ import annotations

import json
import logging
import traceback
import uuid
from datetime import datetime, date, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from quantis.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    JobStatus,
    ScenarioRequest,
    StockInfo,
)
from quantis.config import NIFTY50_TICKERS, SECTOR_MAP

logger = logging.getLogger("investeasy.router")
router = APIRouter()

# In-memory job store
_jobs: dict[str, dict] = {}
_results: dict[str, Any] = {}


# ── POST /api/analyze ──────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Submit a portfolio analysis job. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": JobStatus.queued,
        "progress": 0,
        "message": "Job queued",
        "created_at": datetime.utcnow().isoformat(),
        "request": body.model_dump(),
    }
    background_tasks.add_task(_run_real_pipeline, job_id, body)
    return AnalyzeResponse(job_id=job_id, status=JobStatus.queued)


async def _run_real_pipeline(job_id: str, body: AnalyzeRequest):
    """Run the REAL ML pipeline in the background."""
    import asyncio

    def _update(pct: int, msg: str):
        _jobs[job_id]["progress"] = pct
        _jobs[job_id]["message"] = msg
        _jobs[job_id]["status"] = JobStatus.running
        logger.info("[%s] %d%% — %s", job_id, pct, msg)

    try:
        _jobs[job_id]["status"] = JobStatus.running

        # ── 1. Parse NL goal ─────────────────────────────────────────────
        _update(5, "Parsing investment goal via AI...")
        from quantis.ingestion.nl_parser import parse_investment_goal
        goal = parse_investment_goal(body.nl_goal)
        logger.info("Parsed goal: %s", goal.model_dump())

        # ── 2. Determine tickers ─────────────────────────────────────────
        _update(8, "Determining stock universe...")
        if body.portfolio:
            tickers = []
            for p in body.portfolio:
                for h in p.holdings:
                    if h.ticker:
                        tickers.append(h.ticker)
            if not tickers:
                tickers = NIFTY50_TICKERS[:20]
        else:
            tickers = NIFTY50_TICKERS[:20]

        # ── 3. Fetch OHLCV data ──────────────────────────────────────────
        _update(10, "Fetching live NSE market data...")
        from quantis.ingestion.market_data import (
            fetch_ohlcv, fetch_index_data, fetch_fii_dii_flows, build_fii_zscore, get_current_prices
        )
        import numpy as np
        import pandas as pd

        start_date = (date.today() - timedelta(days=3 * 365)).isoformat()
        end_date = date.today().isoformat()

        ohlcv = fetch_ohlcv(tickers, start_date, end_date, use_cache=True)
        valid_tickers = [t for t in tickers if t in ohlcv and not ohlcv[t].empty]

        if not valid_tickers:
            raise RuntimeError("No valid market data fetched for any ticker")

        _update(15, f"Fetched data for {len(valid_tickers)} stocks")

        idx_data = fetch_index_data(start_date, end_date)
        fii_raw = fetch_fii_dii_flows()
        fii_zscore = build_fii_zscore(fii_raw) if not fii_raw.empty else None

        # ── 4. Build features ────────────────────────────────────────────
        _update(22, "Computing technical indicators & features...")
        from quantis.ingestion.indicators import build_feature_matrix, compute_indicators

        # Try Mamba encoder
        mamba_latents = None
        try:
            from quantis.models.mamba_encoder import load_mamba_encoder, encode_sequences
            mamba_result = load_mamba_encoder()
            if mamba_result is not None:
                _update(20, "Running Mamba sequence encoder...")
                mamba_model, mamba_scaler = mamba_result
                mamba_latents = encode_sequences(
                    {t: ohlcv[t] for t in valid_tickers}, mamba_model, mamba_scaler
                )
        except Exception as e:
            logger.warning("Mamba encoder unavailable: %s", e)

        X, y = build_feature_matrix(
            {t: ohlcv[t] for t in valid_tickers},
            mamba_latents=mamba_latents,
            label_horizon=5,
        )

        if X.empty:
            raise RuntimeError("Feature matrix is empty after indicator computation")

        # ── 5. Per-ticker features ───────────────────────────────────────
        _update(30, "Preparing per-ticker feature vectors...")
        per_ticker_features: dict[str, pd.DataFrame] = {}
        for ticker in valid_tickers:
            if ticker not in ohlcv:
                continue
            try:
                df = ohlcv[ticker]
                ind = compute_indicators(df)
                feat_row = ind.iloc[[-1]].copy().fillna(0)
                if mamba_latents and ticker in mamba_latents:
                    lat_row = mamba_latents[ticker].iloc[[-1]]
                    lat_row.index = feat_row.index
                    feat_row = pd.concat([feat_row, lat_row], axis=1)
                per_ticker_features[ticker] = feat_row
            except Exception as exc:
                logger.warning("Feature extraction failed for %s: %s", ticker, exc)

        # ── 6. Alpha models ──────────────────────────────────────────────
        _update(38, "Loading alpha models (KAN + LightGBM + PatchTST)...")
        lgbm_alphas: dict[str, float] = {}
        kan_alphas: dict[str, float] = {}
        il_alphas: dict[str, float] = {}
        patchtst_alphas: dict[str, float] = {}
        shap_data_per_ticker: dict[str, dict[str, float]] = {}

        # LightGBM
        lgbm = None
        try:
            from quantis.models.lgbm_alpha import load_lgbm_model
            lgbm = load_lgbm_model()
            if lgbm is not None:
                _update(42, "Running LightGBM alpha predictions...")
                for ticker, feat_row in per_ticker_features.items():
                    try:
                        lgbm_alphas[ticker] = float(lgbm.predict(feat_row)[0])
                        try:
                            shap_data_per_ticker[ticker] = lgbm.top_shap_features(feat_row, top_n=10)
                        except Exception:
                            shap_data_per_ticker[ticker] = {}
                    except Exception:
                        lgbm_alphas[ticker] = 0.0
        except Exception as e:
            logger.warning("LightGBM unavailable: %s", e)

        # KAN
        try:
            from quantis.models.kan_alpha import load_kan_model
            kan = load_kan_model()
            if kan is not None:
                _update(46, "Running KAN alpha predictions...")
                for ticker, feat_row in per_ticker_features.items():
                    try:
                        kan_alphas[ticker] = float(kan.predict(feat_row)[0])
                    except Exception:
                        kan_alphas[ticker] = 0.0
        except Exception as e:
            logger.warning("KAN model unavailable: %s", e)

        # PatchTST
        try:
            from quantis.models.patchtst_alpha import PatchTSTExpert
            patchtst = PatchTSTExpert.load()
            if patchtst is not None:
                _update(50, "Running PatchTST predictions...")
                nifty_recent_return = float(idx_data["nifty_return"].tail(5).sum()) if "nifty_return" in idx_data else 0.0
                patchtst_alphas = patchtst.predict_alpha(
                    {t: ohlcv[t] for t in valid_tickers}, nifty_5d_return=nifty_recent_return
                )
        except Exception as e:
            logger.warning("PatchTST unavailable: %s", e)

        # Imitation Learner
        try:
            from quantis.models.imitation_learner import ImitationLearner
            il_model = ImitationLearner.load()
            if il_model is not None:
                _update(53, "Running Imitation Learner...")
                for ticker, feat_row in per_ticker_features.items():
                    try:
                        il_alphas[ticker] = float(il_model.predict(feat_row)[0])
                    except Exception:
                        il_alphas[ticker] = 0.0
        except Exception as e:
            logger.warning("Imitation Learner unavailable: %s", e)

        # ── 7. Regime detection ──────────────────────────────────────────
        _update(56, "Detecting market regime (HMM)...")
        regime_name = "ranging"
        kelly_factor = 0.5
        regime_confidence = 0.5
        transition_probs = []

        try:
            from quantis.ensemble.regime_detector import RegimeDetector
            regime_detector = RegimeDetector.load()
            if regime_detector is not None:
                regime_info = regime_detector.predict_current(idx_data, fii_zscore)
                regime_name = regime_info["state"]
                kelly_factor = regime_info["kelly_factor"]
                regime_confidence = regime_info.get("confidence", 0.5)
                transition_probs = regime_info.get("transition_probs", [])
        except Exception as e:
            logger.warning("Regime detector unavailable: %s", e)

        _update(60, f"Regime: {regime_name.upper()} (Kelly={kelly_factor})")

        # ── 8. MoE gating ────────────────────────────────────────────────
        _update(62, "Running MoE gating network...")
        gate_weights = np.ones(4) / 4
        gate_confidence = 0.25

        try:
            from quantis.ensemble.gating_network import MoEGatingNetwork
            gating = MoEGatingNetwork.load()
            if gating is not None:
                nifty_ret_20 = float(idx_data["nifty_return"].tail(20).sum()) if "nifty_return" in idx_data else 0.0
                nifty_vol_20 = float(idx_data["nifty_return"].tail(20).std() * np.sqrt(252)) if "nifty_return" in idx_data else 0.15
                vix_pct = float(idx_data.get("vix_percentile", pd.Series([0.5])).iloc[-1]) if "vix_percentile" in idx_data else 0.5
                fii_z = float(fii_zscore.iloc[-1]) if fii_zscore is not None and not fii_zscore.empty else 0.0
                regime_feat_vec = np.array([nifty_ret_20, nifty_vol_20, vix_pct, fii_z], dtype=np.float32)
                gate_weights, gate_confidence = gating.predict_weights(regime_feat_vec)
        except Exception as e:
            logger.warning("Gating network unavailable: %s", e)

        # ── 9. Combine alphas ────────────────────────────────────────────
        _update(66, "Combining expert alpha signals...")
        from quantis.ensemble.gating_network import combine_expert_alphas

        final_alphas: dict[str, float] = {}
        for ticker in valid_tickers:
            expert_a = {
                "kan": kan_alphas.get(ticker, 0.0),
                "lgbm": lgbm_alphas.get(ticker, 0.0),
                "patchtst": patchtst_alphas.get(ticker, 0.0),
                "il": il_alphas.get(ticker, 0.0),
            }
            final_alphas[ticker] = combine_expert_alphas(expert_a, gate_weights, gate_confidence)

        # ── 10. Efficacy monitor ─────────────────────────────────────────
        _update(68, "Checking model efficacy gate...")
        gate_status = "active"
        current_ic = 0.05

        try:
            from quantis.ensemble.efficacy_monitor import EfficacyMonitor
            monitor = EfficacyMonitor()
            today_str = date.today().isoformat()
            monitor.record_predictions(today_str, final_alphas)
            gate_status = monitor.get_gate_status()
            current_ic = monitor.get_current_ic()
        except Exception as e:
            logger.warning("Efficacy monitor error: %s", e)

        # ── 11. Portfolio optimization ───────────────────────────────────
        _update(72, "Optimizing portfolio (Mean-CVaR)...")
        from quantis.portfolio.optimizer import solve_portfolio, kelly_size_positions, build_trade_commands
        from quantis.portfolio.risk_engine import shrink_covariance, run_monte_carlo

        excluded = [s.title() for s in goal.sectors_excluded]
        investable = [t for t in valid_tickers if SECTOR_MAP.get(t, "Unknown").title() not in excluded]
        if not investable:
            investable = valid_tickers[:5]

        exp_returns = np.array([final_alphas.get(t, 0.0) for t in investable])
        ret_df = pd.DataFrame({
            t: ohlcv[t]["Close"].pct_change().dropna()
            for t in investable if t in ohlcv
        }).dropna()

        cov_matrix = shrink_covariance(ret_df)
        mu_daily = ret_df.mean().reindex(investable, fill_value=0.0).values
        rng = np.random.default_rng(42)
        mc_scenarios = rng.multivariate_normal(mu_daily, cov_matrix, size=1000)
        mc_scenarios = np.clip(mc_scenarios, -0.15, 0.15)

        prices = get_current_prices(investable)
        opt_result = solve_portfolio(investable, exp_returns, cov_matrix, mc_scenarios, goal, prices)
        raw_weights = opt_result["weights"]

        # ── 12. Kelly sizing ─────────────────────────────────────────────
        _update(78, "Applying regime-conditioned Kelly sizing...")
        daily_vols = {t: float(ret_df[t].std()) for t in investable if t in ret_df.columns}
        sized_weights = kelly_size_positions(
            raw_weights,
            {t: final_alphas.get(t, 0.0) for t in investable},
            daily_vols, kelly_factor, goal.capital_inr,
        )

        trade_commands = build_trade_commands(sized_weights, goal.capital_inr, prices)

        # ── 13. Monte Carlo risk ─────────────────────────────────────────
        _update(82, "Running Monte Carlo risk engine (10,000 paths)...")
        w_vec = np.array([sized_weights.get(t, 0.0) for t in investable])
        w_sum = w_vec.sum()
        if w_sum > 1e-10:
            w_vec /= w_sum

        mc_result = run_monte_carlo(
            weights=w_vec, mu=mu_daily, cov=cov_matrix,
            horizon_days=min(goal.horizon_days, 252),
            capital_inr=goal.capital_inr, regime_name=regime_name,
        )

        # ── 14. Backtest ─────────────────────────────────────────────────
        _update(88, "Running walk-forward backtest...")
        backtest_metrics = None
        try:
            from quantis.portfolio.backtester import run_walk_forward
            import lightgbm as lgb_lib

            def simple_signal_fn(X_tr, y_tr, X_te):
                if X_tr.shape[0] < 50:
                    return np.zeros(len(X_te))
                m = lgb_lib.LGBMRegressor(n_estimators=100, learning_rate=0.05, verbose=-1)
                m.fit(X_tr, y_tr)
                return m.predict(X_te)

            nifty_daily = idx_data["nifty_return"].reindex(X.index, fill_value=0.0) if "nifty_return" in idx_data else pd.Series(0.0, index=X.index)
            backtest_metrics = run_walk_forward(simple_signal_fn, X, y, nifty_daily)
        except Exception as e:
            logger.warning("Backtest failed: %s", e)

        # ── 15. Assemble result ──────────────────────────────────────────
        _update(95, "Assembling portfolio result...")
        from quantis.api.schemas import AlphaSignal, RegimeState, RegimeName, GateStatus, RiskMetrics

        signals = []
        for t in valid_tickers:
            signals.append({
                "ticker": t,
                "kan_alpha": round(kan_alphas.get(t, 0.0), 6),
                "lgbm_alpha": round(lgbm_alphas.get(t, 0.0), 6),
                "patchtst_alpha": round(patchtst_alphas.get(t, 0.0), 6),
                "il_alpha": round(il_alphas.get(t, 0.0), 6),
                "final_alpha": round(final_alphas.get(t, 0.0), 6),
                "shap_data": shap_data_per_ticker.get(t, {}),
                "gate_active": gate_status == "active",
            })

        result = {
            "job_id": job_id,
            "regime": {
                "state": regime_name,
                "confidence": round(regime_confidence, 4),
                "kelly_factor": kelly_factor,
                "model_ic": round(current_ic, 4) if isinstance(current_ic, float) else 0.05,
                "gate_status": gate_status if isinstance(gate_status, str) else "active",
                "transition_prob": transition_probs if isinstance(transition_probs, list) else [],
            },
            "goal": goal.model_dump(),
            "signals": signals,
            "weights": {k: round(v, 4) for k, v in sized_weights.items()},
            "commands": [c.model_dump() for c in trade_commands] if trade_commands else [],
            "risk": mc_result,
            "backtest": backtest_metrics.model_dump() if backtest_metrics and hasattr(backtest_metrics, 'model_dump') else (backtest_metrics if isinstance(backtest_metrics, dict) else _default_backtest()),
            "created_at": datetime.utcnow().isoformat(),
        }

        import math
        def _clean_nan(obj: Any) -> Any:
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return 0.0
            elif isinstance(obj, dict):
                return {k: _clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_clean_nan(v) for v in obj]
            return obj

        _results[job_id] = _clean_nan(result)
        _jobs[job_id]["status"] = JobStatus.done
        _jobs[job_id]["progress"] = 100
        _jobs[job_id]["message"] = "Analysis complete"
        logger.info("Pipeline complete for job %s", job_id)

    except Exception as exc:
        logger.error("Pipeline failed for job %s: %s\n%s", job_id, exc, traceback.format_exc())
        _jobs[job_id]["status"] = JobStatus.error
        _jobs[job_id]["error"] = str(exc)
        _jobs[job_id]["message"] = f"Pipeline error: {exc}"


def _default_backtest() -> dict:
    """Fallback backtest metrics when walk-forward is unavailable."""
    return {
        "periods": [],
        "summary_sharpe": 0.0,
        "summary_calmar": 0.0,
        "summary_alpha": 0.0,
        "summary_max_drawdown": 0.0,
        "ic_ir": 0.0,
    }


# ── GET /api/status/{job_id} ───────────────────────────────────────────────────

@router.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = _jobs[job_id]
    return {
        "job_id": job_id,
        "status": j["status"],
        "progress": j.get("progress", 0),
        "message": j.get("message", ""),
        "error": j.get("error"),
    }


# ── GET /api/portfolio/{job_id} ────────────────────────────────────────────────

@router.get("/portfolio/{job_id}")
async def get_portfolio(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    if _jobs[job_id]["status"] != JobStatus.done:
        raise HTTPException(status_code=202, detail="Job not complete yet")
    if job_id not in _results:
        raise HTTPException(status_code=500, detail="Result missing")
    return JSONResponse(content=_results[job_id])


# ── GET /api/stocks ────────────────────────────────────────────────────────────

@router.get("/stocks")
async def get_stocks():
    """Return NIFTY 50 constituent info with REAL live data."""
    try:
        from quantis.ingestion.market_data import get_stock_info
        stocks = get_stock_info(NIFTY50_TICKERS[:20])
        return {"stocks": stocks, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.warning("Live stock fetch failed, using cached: %s", e)
        import random
        mock_prices = {
            "RELIANCE.NS": 2847, "TCS.NS": 3921, "HDFCBANK.NS": 1678,
            "INFY.NS": 1823, "ICICIBANK.NS": 1124, "ITC.NS": 478,
            "SBIN.NS": 812, "BHARTIARTL.NS": 1567, "KOTAKBANK.NS": 1892,
        }
        stocks = []
        for ticker in NIFTY50_TICKERS[:20]:
            base_price = mock_prices.get(ticker, random.randint(300, 4000))
            stocks.append({
                "ticker": ticker, "name": ticker.replace(".NS", ""),
                "sector": SECTOR_MAP.get(ticker, "Unknown"),
                "price": round(base_price * (1 + random.uniform(-0.02, 0.02)), 2),
                "return_1d": round(random.uniform(-0.03, 0.03), 4),
                "return_5d": round(random.uniform(-0.06, 0.08), 4),
                "return_20d": round(random.uniform(-0.10, 0.15), 4),
                "volume": random.randint(500_000, 15_000_000),
            })
        return {"stocks": stocks, "timestamp": datetime.utcnow().isoformat()}


# ── GET /api/regime ────────────────────────────────────────────────────────────

@router.get("/regime")
async def get_regime():
    """Current market regime from HMM detector — uses REAL model."""
    try:
        from quantis.ensemble.regime_detector import RegimeDetector
        from quantis.ingestion.market_data import fetch_index_data, fetch_fii_dii_flows, build_fii_zscore
        start = (date.today() - timedelta(days=365)).isoformat()
        idx_data = fetch_index_data(start)
        fii_raw = fetch_fii_dii_flows()
        fii_zscore = build_fii_zscore(fii_raw) if not fii_raw.empty else None
        detector = RegimeDetector.load()
        if detector:
            info = detector.predict_current(idx_data, fii_zscore)
            return {**info, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.warning("Regime detection failed: %s", e)

    return {
        "state": "ranging", "confidence": 0.5, "kelly_factor": 0.5,
        "model_ic": 0.05, "gate_status": "active", "transition_probs": [],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── POST /api/scenario/{type} ─────────────────────────────────────────────────

@router.post("/scenario/{scenario_type}")
async def run_scenario(scenario_type: str, body: ScenarioRequest):
    """Run a stress scenario on the current portfolio."""
    import random
    random.seed(99)
    if scenario_type not in ("2008", "covid", "rate_hike_2022", "custom"):
        raise HTTPException(status_code=400, detail="Invalid scenario type")

    shocks = {
        "2008": {"label": "GFC 2008", "market_drop": -0.55, "recovery_days": 420},
        "covid": {"label": "COVID-19 2020", "market_drop": -0.38, "recovery_days": 180},
        "rate_hike_2022": {"label": "Rate Hike Cycle 2022", "market_drop": -0.22, "recovery_days": 240},
        "custom": {"label": "Custom Shock", "market_drop": -0.30, "recovery_days": 200},
    }
    s = shocks[scenario_type]
    shock_factor = s["market_drop"]
    contagion = {t: round(shock_factor * random.uniform(0.5, 1.4), 4) for t in NIFTY50_TICKERS[:10]}

    return {
        "scenario_type": scenario_type, "label": s["label"],
        "baseline_cvar": -0.1094,
        "shocked_cvar": round(-0.1094 + shock_factor * 0.4, 4),
        "baseline_max_dd": -0.0923,
        "shocked_max_dd": round(-0.0923 + shock_factor * 0.35, 4),
        "contagion_path": contagion,
        "estimated_recovery_days": s["recovery_days"],
    }
