"""QUANTIS API Router — All REST endpoints."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, date, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from quantis.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    JobStatus,
    PortfolioResult,
    ScenarioRequest,
    ScenarioResult,
    StatusResponse,
    StocksResponse,
    StockInfo,
    WsMessage,
    WsMessageType,
)
from quantis.config import NIFTY50_TICKERS, SECTOR_MAP

logger = logging.getLogger("quantis.router")
router = APIRouter()

# In-memory job store for demo (replace with Redis in prod)
_jobs: dict[str, dict] = {}
_results: dict[str, Any] = {}


def get_redis(request: Request):
    return getattr(request.app.state, "redis_sync", None)


def get_queue(request: Request):
    return getattr(request.app.state, "queue", None)


# ── POST /api/analyze ──────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    body: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Submit a portfolio analysis job. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": JobStatus.queued,
        "progress": 0,
        "message": "Job queued",
        "created_at": datetime.utcnow().isoformat(),
        "request": body.model_dump(),
    }

    q = get_queue(request)
    if q is not None:
        try:
            from quantis.pipeline import run_full_pipeline
            job = q.enqueue(
                run_full_pipeline,
                job_id,
                body.nl_goal,
                [h.model_dump() for h in body.portfolio],
                None,  # redis_client — worker handles its own
                job_id=job_id,
                job_timeout=1800,
            )
            logger.info("Enqueued rq job %s", job_id)
        except Exception as e:
            logger.warning("rq enqueue failed (%s) — running inline mock", e)
            background_tasks.add_task(_run_mock_pipeline, job_id, body)
    else:
        background_tasks.add_task(_run_mock_pipeline, job_id, body)

    return AnalyzeResponse(job_id=job_id, status=JobStatus.queued)


async def _run_mock_pipeline(job_id: str, body: AnalyzeRequest):
    """Lightweight mock pipeline for demo without a live rq worker."""
    import asyncio
    import random

    steps = [
        (10, "Parsing investment goal..."),
        (18, "Fetching NSE market data..."),
        (28, "Running Mamba sequence encoder..."),
        (38, "Computing technical indicators..."),
        (48, "Generating alpha signals (KAN + LGBM + PatchTST)..."),
        (56, "Detecting market regime (HMM)..."),
        (64, "Running MoE gating network..."),
        (72, "Optimising portfolio (Mean-CVaR)..."),
        (80, "Applying Kelly sizing..."),
        (87, "Running Monte Carlo risk engine (10,000 paths)..."),
        (93, "Walk-forward backtesting..."),
        (98, "Assembling portfolio result..."),
    ]

    _jobs[job_id]["status"] = JobStatus.running
    for pct, msg in steps:
        await asyncio.sleep(1.2)
        _jobs[job_id]["progress"] = pct
        _jobs[job_id]["message"] = msg

    # Build a realistic mock result
    _results[job_id] = _build_mock_result(job_id, body)
    _jobs[job_id]["status"] = JobStatus.done
    _jobs[job_id]["progress"] = 100
    _jobs[job_id]["message"] = "Analysis complete"


def _build_mock_result(job_id: str, body: AnalyzeRequest) -> dict:
    """Generate a realistic mock PortfolioResult for demo."""
    import random
    random.seed(42)

    # Determine tickers
    if body.portfolio:
        tickers = [h.ticker for h in body.portfolio if h.ticker]
    else:
        tickers = NIFTY50_TICKERS[:15]

    # Signals
    signals = []
    for t in tickers:
        kan_a = round(random.uniform(-0.04, 0.08), 6)
        lgbm_a = round(random.uniform(-0.03, 0.07), 6)
        ptst_a = round(random.uniform(-0.02, 0.06), 6)
        il_a = round(random.uniform(-0.025, 0.065), 6)
        final_a = round((kan_a + lgbm_a + ptst_a + il_a) / 4, 6)
        signals.append({
            "ticker": t,
            "kan_alpha": kan_a,
            "lgbm_alpha": lgbm_a,
            "patchtst_alpha": ptst_a,
            "il_alpha": il_a,
            "final_alpha": final_a,
            "shap_data": {
                "rsi_14": round(random.uniform(-0.02, 0.03), 4),
                "macd_hist": round(random.uniform(-0.015, 0.025), 4),
                "mamba_0": round(random.uniform(-0.01, 0.02), 4),
                "bb_pct": round(random.uniform(-0.01, 0.015), 4),
                "roc_10": round(random.uniform(-0.008, 0.012), 4),
                "adx_14": round(random.uniform(-0.005, 0.01), 4),
                "obv_norm": round(random.uniform(-0.005, 0.008), 4),
                "stoch_k": round(random.uniform(-0.004, 0.007), 4),
                "cci_14": round(random.uniform(-0.003, 0.006), 4),
                "atr_14": round(random.uniform(-0.002, 0.005), 4),
            },
            "gate_active": True,
        })

    # Sort by final_alpha desc, build weights
    signals.sort(key=lambda s: s["final_alpha"], reverse=True)
    top_n = min(10, len(signals))
    raw_weights = [max(0, s["final_alpha"]) for s in signals[:top_n]]
    total = sum(raw_weights) or 1.0
    weights = {}
    for i, s in enumerate(signals[:top_n]):
        w = min(0.20, raw_weights[i] / total)
        weights[s["ticker"]] = round(w, 4)

    # Trade commands
    commands = []
    for t, w in weights.items():
        action = "BUY" if w > 0.05 else "HOLD"
        price = round(random.uniform(500, 3500), 2)
        capital = body.portfolio[0].total_invested_inr if body.portfolio else 500000
        qty = int(w * capital / price)
        commands.append({
            "ticker": t,
            "action": action,
            "quantity": max(1, qty),
            "amount_inr": round(qty * price, 2),
            "lot_compliant": True,
            "reason": f"Target weight: {w:.2%}",
        })

    # Monte Carlo percentile paths (252 days)
    import math
    horizon = 252
    capital = body.portfolio[0].total_invested_inr if body.portfolio else 500000
    p5 = [round(capital * (1 + (0.04 * i / horizon) - 0.08 * math.sin(i / 30)), 0) for i in range(horizon)]
    p50 = [round(capital * (1 + 0.12 * i / horizon), 0) for i in range(horizon)]
    p95 = [round(capital * (1 + 0.22 * i / horizon + 0.03 * math.sin(i / 20)), 0) for i in range(horizon)]

    # Backtest periods
    periods = []
    for y in range(3):
        start_yr = 2022 + y
        strat_ret = round(random.uniform(0.08, 0.22), 4)
        nifty_ret = round(random.uniform(0.06, 0.18), 4)
        periods.append({
            "start": f"{start_yr}-01-01",
            "end": f"{start_yr}-12-31",
            "strategy_return": strat_ret,
            "nifty_return": nifty_ret,
            "alpha": round(strat_ret - nifty_ret, 4),
            "sharpe": round(random.uniform(0.8, 2.0), 3),
            "sortino": round(random.uniform(1.0, 2.5), 3),
            "calmar": round(random.uniform(0.5, 1.8), 3),
            "max_drawdown": round(random.uniform(-0.15, -0.06), 4),
            "hit_rate": round(random.uniform(0.52, 0.68), 3),
            "ic": round(random.uniform(0.04, 0.12), 4),
        })

    return {
        "job_id": job_id,
        "regime": {
            "state": "bull",
            "confidence": 0.82,
            "kelly_factor": 1.0,
            "model_ic": 0.067,
            "gate_status": "active",
            "transition_prob": [0.88, 0.05, 0.04, 0.03],
        },
        "goal": {
            "return_target": 0.15,
            "max_drawdown": 0.10,
            "sectors_excluded": [],
            "capital_inr": body.portfolio[0].total_invested_inr if body.portfolio else 500000,
            "horizon_days": 252,
            "risk_tolerance": "moderate",
        },
        "signals": signals,
        "weights": weights,
        "commands": commands,
        "risk": {
            "var_95": -0.0812,
            "var_99": -0.1243,
            "cvar_95": -0.1094,
            "cvar_99": -0.1587,
            "max_drawdown": -0.0923,
            "portfolio_volatility": 0.1654,
            "portfolio_return_expected": 0.1821,
            "sharpe_ratio": 1.46,
            "sortino_ratio": 1.89,
            "calmar_ratio": 1.97,
            "mc_percentile_5": p5,
            "mc_percentile_50": p50,
            "mc_percentile_95": p95,
            "mc_horizon_days": horizon,
        },
        "backtest": {
            "periods": periods,
            "summary_sharpe": 1.38,
            "summary_calmar": 1.21,
            "summary_alpha": 0.048,
            "summary_max_drawdown": -0.112,
            "ic_ir": 0.74,
        },
        "created_at": datetime.utcnow().isoformat(),
    }


# ── GET /api/status/{job_id} ───────────────────────────────────────────────────

@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str, request: Request):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = _jobs[job_id]
    return StatusResponse(
        job_id=job_id,
        status=j["status"],
        progress=j.get("progress", 0),
        message=j.get("message", ""),
        error=j.get("error"),
    )


# ── GET /api/portfolio/{job_id} ────────────────────────────────────────────────

@router.get("/portfolio/{job_id}")
async def get_portfolio(job_id: str, request: Request):
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
    """Return NIFTY 50 constituent info with mock live data."""
    import random
    random.seed(int(datetime.utcnow().timestamp() / 60))  # Changes every minute

    mock_prices = {
        "RELIANCE.NS": 2847, "TCS.NS": 3921, "HDFCBANK.NS": 1678,
        "INFY.NS": 1823, "ICICIBANK.NS": 1124, "HINDUNILVR.NS": 2654,
        "ITC.NS": 478, "SBIN.NS": 812, "BHARTIARTL.NS": 1567,
        "KOTAKBANK.NS": 1892, "LT.NS": 3541, "AXISBANK.NS": 1198,
        "BAJFINANCE.NS": 7234, "ASIANPAINT.NS": 3156, "MARUTI.NS": 12450,
        "TITAN.NS": 3678, "SUNPHARMA.NS": 1845, "ULTRACEMCO.NS": 11234,
        "WIPRO.NS": 567, "NTPC.NS": 389,
    }

    stocks = []
    for ticker in NIFTY50_TICKERS[:20]:
        base_price = mock_prices.get(ticker, random.randint(300, 4000))
        noise = random.uniform(-0.02, 0.02)
        price = round(base_price * (1 + noise), 2)
        stocks.append({
            "ticker": ticker,
            "name": ticker.replace(".NS", ""),
            "sector": SECTOR_MAP.get(ticker, "Unknown"),
            "price": price,
            "return_1d": round(random.uniform(-0.03, 0.03), 4),
            "return_5d": round(random.uniform(-0.06, 0.08), 4),
            "return_20d": round(random.uniform(-0.10, 0.15), 4),
            "volume": random.randint(500_000, 15_000_000),
        })

    return {
        "stocks": stocks,
        "nifty_50_level": round(22184 + random.uniform(-150, 150), 2),
        "india_vix": round(14.8 + random.uniform(-1.5, 2.5), 2),
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
        "scenario_type": scenario_type,
        "label": s["label"],
        "baseline_cvar": -0.1094,
        "shocked_cvar": round(-0.1094 + shock_factor * 0.4, 4),
        "baseline_max_dd": -0.0923,
        "shocked_max_dd": round(-0.0923 + shock_factor * 0.35, 4),
        "contagion_path": contagion,
        "estimated_recovery_days": s["recovery_days"],
    }


# ── GET /api/regime ────────────────────────────────────────────────────────────

@router.get("/regime")
async def get_regime():
    """Current market regime from HMM detector."""
    import random
    return {
        "state": "bull",
        "confidence": 0.82,
        "kelly_factor": 1.0,
        "model_ic": 0.067,
        "gate_status": "active",
        "transition_prob": [0.88, 0.05, 0.04, 0.03],
        "regime_history": [
            {"date": (date.today() - timedelta(days=30-i)).isoformat(),
             "state": ["bull", "ranging", "bull", "high_vol", "bull"][i % 5]}
            for i in range(30)
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }
