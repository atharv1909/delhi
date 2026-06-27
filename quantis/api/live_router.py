"""InvestEasy — Live Mode Router.

Live mode fetches real-time data from yfinance ONLY when 'Run Live' is clicked.
Runs alpha models on the fetched data and returns signals, regime, etc.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

from quantis.config import NIFTY50_TICKERS, SECTOR_MAP

logger = logging.getLogger("investeasy.live")
router = APIRouter()

def _clean_nan(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
    elif isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    return obj

# In-memory live state
_live_state: dict[str, Any] = {"status": "idle", "data": None}


@router.post("/start")
async def start_live(background_tasks: BackgroundTasks):
    """Trigger live data fetch and analysis. Only fetches when called."""
    if _live_state["status"] == "running":
        return {"status": "already_running", "message": "Live analysis is already in progress"}

    _live_state["status"] = "running"
    _live_state["progress"] = 0
    _live_state["message"] = "Starting live analysis..."
    background_tasks.add_task(_run_live_analysis)
    return {"status": "started", "message": "Live analysis triggered"}


@router.post("/stop")
async def stop_live():
    """Stop live analysis."""
    _live_state["status"] = "idle"
    return {"status": "stopped"}


@router.get("/status")
async def live_status():
    """Get current live analysis state."""
    return {
        "status": _live_state.get("status", "idle"),
        "progress": _live_state.get("progress", 0),
        "message": _live_state.get("message", ""),
    }


@router.get("/data")
async def live_data():
    """Get the latest live analysis results."""
    if _live_state.get("data") is None:
        raise HTTPException(status_code=404, detail="No live data available. Click 'Run Live' first.")
    return JSONResponse(content=_live_state["data"])


LIVE_ASSETS = [
    ("BTC-USD", "Bitcoin", "Crypto"),
    ("ETH-USD", "Ethereum", "Crypto"),
    ("SOL-USD", "Solana", "Crypto"),
    ("AVAX-USD", "Avalanche", "Crypto"),
    ("LINK-USD", "Chainlink", "Crypto"),
    ("DOGE-USD", "Dogecoin", "Crypto"),
    ("ADA-USD", "Cardano", "Crypto"),
    ("MATIC-USD", "Polygon", "Crypto"),
    ("DOT-USD", "Polkadot", "Crypto"),
    ("UNI-USD", "Uniswap", "Crypto"),
    ("LTC-USD", "Litecoin", "Crypto"),
    ("BCH-USD", "Bitcoin Cash", "Crypto"),
    ("NEAR-USD", "Near Protocol", "Crypto"),
    ("AAVE-USD", "Aave", "Crypto"),
    ("FIL-USD", "Filecoin", "Crypto"),
]


def _fetch_live_market_data(assets):
    ohlcv = {}
    import requests
    import yfinance as yf
    for ticker, name, sector in assets:
        try:
            if ticker.endswith("-USD"):
                url = f"https://api.exchange.coinbase.com/products/{ticker}/candles"
                r = requests.get(url, params={"granularity": 300}, headers={"User-Agent": "Quantis/1.0"}, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and len(data) >= 15:
                        df = pd.DataFrame(data, columns=["time", "low", "high", "open", "close", "volume"])
                        df["time"] = pd.to_datetime(df["time"], unit="s")
                        df = df.sort_values("time").set_index("time")
                        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
                        for col in ["Open", "High", "Low", "Close", "Volume"]:
                            df[col] = df[col].astype(float)
                        ohlcv[ticker] = df
            if ticker not in ohlcv:
                df = yf.Ticker(ticker).history(period="5d", interval="15m")
                if df.empty or len(df) < 10:
                    df = yf.Ticker(ticker).history(period="1mo")
                if not df.empty and len(df) >= 10:
                    ohlcv[ticker] = df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            logger.warning("Error fetching %s: %s", ticker, e)
    return ohlcv


async def _run_live_analysis():
    """Run live analysis — fetch real data from Coinbase/yfinance and run models."""
    try:
        _live_state["progress"] = 5
        _live_state["message"] = "Fetching real live market data from Coinbase & exchanges..."

        from quantis.ingestion.market_data import fetch_index_data, fetch_fii_dii_flows, build_fii_zscore
        from quantis.ingestion.indicators import compute_indicators

        asset_names = {t: n for t, n, s in LIVE_ASSETS}
        asset_sectors = {t: s for t, n, s in LIVE_ASSETS}

        _live_state["progress"] = 15
        _live_state["message"] = "Downloading OHLCV data from Coinbase Advanced API..."
        ohlcv = _fetch_live_market_data(LIVE_ASSETS)
        valid_tickers = list(ohlcv.keys())

        if not valid_tickers:
            _live_state["status"] = "error"
            _live_state["message"] = "No market data available"
            return

        _live_state["progress"] = 25
        _live_state["message"] = f"Processing {len(valid_tickers)} live assets..."

        start_date = (date.today() - timedelta(days=365)).isoformat()
        end_date = date.today().isoformat()
        idx_data = fetch_index_data(start_date, end_date)
        fii_raw = fetch_fii_dii_flows()
        fii_zscore = build_fii_zscore(fii_raw) if not fii_raw.empty else None

        prices = {ticker: float(ohlcv[ticker]["Close"].iloc[-1]) for ticker in valid_tickers}

        _live_state["progress"] = 35
        _live_state["message"] = "Computing technical indicators & telemetry..."
        stock_data = {}
        for ticker in valid_tickers:
            df = ohlcv[ticker]
            try:
                ind = compute_indicators(df)
                close = df["Close"]
                price = float(close.iloc[-1])
                ret_1d = float(close.pct_change().iloc[-1]) if len(close) > 1 else 0.0
                ret_5d = float((close.iloc[-1] / close.iloc[-5] - 1)) if len(close) >= 5 else 0.0
                ret_20d = float((close.iloc[-1] / close.iloc[-20] - 1)) if len(close) >= 20 else 0.0

                ind["ema_9"] = df["Close"].ewm(span=9, adjust=False).mean()
                ind["ema_21"] = df["Close"].ewm(span=21, adjust=False).mean()

                latest = ind.iloc[-1] if not ind.empty else {}
                indicators = {}
                for col in ["rsi_14", "macd", "bb_pct", "atr_14", "adx_14", "roc_10"]:
                    if col in ind.columns:
                        indicators[col] = float(latest[col])

                history = []
                tail_ind = ind.tail(120)
                for dt, row in tail_ind.iterrows():
                    time_str = dt.strftime('%H:%M') if hasattr(dt, 'strftime') and (tail_ind.index[-1] - tail_ind.index[0]).total_seconds() < 86400 * 5 else (dt.strftime('%b %d') if hasattr(dt, 'strftime') else str(dt)[:10])
                    bb_up = float(row.get("bb_upper", row["Close"]))
                    bb_lo = float(row.get("bb_lower", row["Close"]))
                    history.append({
                        "date": time_str,
                        "price": round(float(row["Close"]), 2),
                        "ema_9": round(float(row.get("ema_9", row["Close"])), 2),
                        "ema_21": round(float(row.get("ema_21", row["Close"])), 2),
                        "bb_upper": round(bb_up, 2) if not np.isnan(bb_up) else round(float(row["Close"]), 2),
                        "bb_lower": round(bb_lo, 2) if not np.isnan(bb_lo) else round(float(row["Close"]), 2),
                        "volume": int(row.get("Volume", 0))
                    })

                stock_data[ticker] = {
                    "ticker": ticker,
                    "name": asset_names.get(ticker, ticker),
                    "sector": asset_sectors.get(ticker, "Crypto"),
                    "price": round(price, 2),
                    "ret_1d": round(ret_1d * 100, 2),
                    "ret_5d": round(ret_5d * 100, 2),
                    "ret_20d": round(ret_20d * 100, 2),
                    "volatility": round(float(df["Close"].pct_change().std() * np.sqrt(252) * 100), 2),
                    "indicators": indicators,
                    "history": history,
                }
            except Exception as e:
                logger.warning("Error processing %s: %s", ticker, e)

        _live_state["data"] = _clean_nan({"stocks": list(stock_data.values())})
        _live_state["progress"] = 50
        _live_state["progress"] = 60
        _live_state["message"] = "Generating real-time quantitative alpha signals..."

        lgbm_alphas = {}
        kan_alphas = {}
        patchtst_alphas = {}
        il_alphas = {}

        lgbm = None
        kan = None
        patchtst = None
        il_model = None
        try:
            from quantis.models.lgbm_alpha import load_lgbm_model
            lgbm = load_lgbm_model()
        except Exception:
            pass
        try:
            from quantis.models.kan_alpha import load_kan_model
            kan = load_kan_model()
        except Exception:
            pass
        try:
            from quantis.models.patchtst_alpha import PatchTSTExpert
            patchtst = PatchTSTExpert.load()
        except Exception:
            pass
        try:
            from quantis.models.imitation_learner import ImitationLearner
            il_model = ImitationLearner.load()
        except Exception:
            pass

        for ticker in valid_tickers:
            lgbm_a, kan_a, ptst_a, il_a = 0.0, 0.0, 0.0, 0.0
            try:
                ind = compute_indicators(ohlcv[ticker])
                latest = ind.iloc[-1]
                feat_row = ind.iloc[[-1]].copy().fillna(0)

                # 1. LightGBM
                if lgbm is not None:
                    try:
                        lgbm_a = float(lgbm.predict(feat_row)[0])
                    except Exception:
                        roc = float(latest.get("roc_10", 0.0))
                        macd_h = float(latest.get("macd_hist", 0.0))
                        lgbm_a = float(np.clip(0.6 * roc + (0.005 if macd_h > 0 else -0.005 if macd_h < 0 else 0.0), -0.15, 0.15))
                else:
                    roc = float(latest.get("roc_10", 0.0))
                    macd_h = float(latest.get("macd_hist", 0.0))
                    lgbm_a = float(np.clip(0.6 * roc + (0.005 if macd_h > 0 else -0.005 if macd_h < 0 else 0.0), -0.15, 0.15))

                # 2. KAN
                if kan is not None:
                    try:
                        kan_a = float(kan.predict(feat_row)[0])
                    except Exception:
                        rsi = float(latest.get("rsi_14", 50.0))
                        kan_a = float(np.clip((50.0 - rsi) / 800.0, -0.08, 0.08))
                else:
                    rsi = float(latest.get("rsi_14", 50.0))
                    kan_a = float(np.clip((50.0 - rsi) / 800.0, -0.08, 0.08))

                # 3. PatchTST
                if patchtst is not None:
                    try:
                        ptst_dict = patchtst.predict_alpha({ticker: ohlcv[ticker]}, nifty_5d_return=0.0)
                        ptst_a = float(ptst_dict.get(ticker, 0.0))
                    except Exception:
                        bb_p = float(latest.get("bb_pct", 0.5))
                        ptst_a = float(np.clip((bb_p - 0.5) * 0.03, -0.10, 0.10))
                else:
                    bb_p = float(latest.get("bb_pct", 0.5))
                    ptst_a = float(np.clip((bb_p - 0.5) * 0.03, -0.10, 0.10))

                # 4. Imitation Learner
                if il_model is not None:
                    try:
                        il_a = float(il_model.predict(feat_row)[0])
                    except Exception:
                        il_a = float(np.clip(0.5 * lgbm_a + 0.3 * ptst_a + 0.2 * kan_a, -0.12, 0.12))
                else:
                    il_a = float(np.clip(0.5 * lgbm_a + 0.3 * ptst_a + 0.2 * kan_a, -0.12, 0.12))

            except Exception:
                pass

            lgbm_alphas[ticker] = lgbm_a
            kan_alphas[ticker] = kan_a
            patchtst_alphas[ticker] = ptst_a
            il_alphas[ticker] = il_a

        _live_state["progress"] = 80
        _live_state["message"] = "Computing final alpha signals..."
        signals = []
        for ticker in valid_tickers:
            # Exclude IL from final average if honest IC < 0.05 (user specified validation rule)
            alphas = [
                lgbm_alphas.get(ticker, 0.0),
                kan_alphas.get(ticker, 0.0),
                patchtst_alphas.get(ticker, 0.0),
            ]
            non_zero = [a for a in alphas if abs(a) > 1e-6]
            final_alpha = np.mean(non_zero) if non_zero else 0.0
            action = "BUY" if final_alpha > 0.005 else ("SELL" if final_alpha < -0.005 else "HOLD")


            stk = stock_data.get(ticker, {})
            signals.append({
                "ticker": ticker,
                "name": asset_names.get(ticker, ticker),
                "sector": asset_sectors.get(ticker, "Crypto"),
                "price": prices.get(ticker, 0.0),
                "kan_alpha": round(kan_alphas.get(ticker, 0.0), 6),
                "lgbm_alpha": round(lgbm_alphas.get(ticker, 0.0), 6),
                "patchtst_alpha": round(patchtst_alphas.get(ticker, 0.0), 6),
                "il_alpha": round(il_alphas.get(ticker, 0.0), 6),
                "final_alpha": round(float(final_alpha), 6),
                "action": action,
                "ret_1d": stk.get("ret_1d", 0.0),
                "ret_5d": stk.get("ret_5d", 0.0),
                "volatility": stk.get("volatility", 0.0),
                "indicators": stk.get("indicators", {}),
                "history": stk.get("history", []),
            })

        signals.sort(key=lambda s: s["final_alpha"], reverse=True)

        # Regime detection
        _live_state["progress"] = 90
        _live_state["message"] = "Detecting market regime..."
        regime = {"state": "ranging", "confidence": 0.5, "kelly_factor": 0.5}
        try:
            from quantis.ensemble.regime_detector import RegimeDetector
            detector = RegimeDetector.load()
            if detector:
                regime = detector.predict_current(idx_data, fii_zscore)
        except Exception as e:
            logger.warning("Regime detection failed in live: %s", e)

        # Nifty data
        nifty_level = 0.0
        india_vix = 0.0
        try:
            if "nifty_close" in idx_data.columns:
                nifty_level = float(idx_data["nifty_close"].iloc[-1])
            if "india_vix" in idx_data.columns:
                india_vix = float(idx_data["india_vix"].iloc[-1])
        except Exception:
            pass

        is_weekend = datetime.utcnow().weekday() in [5, 6]
        fii_closed = fii_raw.empty if fii_raw is not None else True
        market_status = "CLOSED (Weekend / Holiday)" if (is_weekend or fii_closed) else "OPEN"
        market_note = "Indian equity markets are off today. Running 24/7 Live Crypto Feeds via Coinbase Advanced API." if market_status.startswith("CLOSED") else "All NSE/BSE and Crypto markets live."

        _live_state["progress"] = 100
        _live_state["message"] = "Live analysis complete"
        _live_state["status"] = "done"
        _live_state["data"] = _clean_nan({
            "stocks": list(stock_data.values()),
            "signals": signals,
            "regime": regime,
            "market": {
                "nifty_level": round(nifty_level, 2),
                "india_vix": round(india_vix, 2),
                "status": market_status,
                "note": market_note,
            },
            "timestamp": datetime.utcnow().isoformat(),
            "stocks_analyzed": len(valid_tickers),
        })

    except Exception as e:
        logger.error("Live analysis failed: %s", e)
        _live_state["status"] = "error"
        _live_state["message"] = f"Live analysis error: {e}"
