"""Technical Indicator Pipeline
Computes all TA indicators required by the ML models using pandas_ta.
All features are strictly lagged to prevent look-ahead bias.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pandas_ta as ta  # type: ignore

logger = logging.getLogger(__name__)

# Features fed into Mamba / KAN / LightGBM
TA_FEATURE_NAMES = [
    "rsi_14", "rsi_21",
    "macd", "macd_hist", "macd_signal",
    "bb_upper", "bb_lower", "bb_width", "bb_pct",
    "atr_14",
    "obv_norm",
    "vwap_proxy",
    "sma_20", "sma_50",
    "ema_21",
    "stoch_k", "stoch_d",
    "adx_14",
    "cci_14",
    "roc_10",
]


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all TA indicators. Input must have OHLCV columns.

    Returns a DataFrame with new indicator columns appended.
    All features are computed on raw data; caller should `.shift(1)` to lag.
    """
    out = df.copy()

    # ── RSI ───────────────────────────────────────────────────────────────────
    out["rsi_14"] = ta.rsi(out["Close"], length=14)
    out["rsi_21"] = ta.rsi(out["Close"], length=21)

    # ── MACD ──────────────────────────────────────────────────────────────────
    macd = ta.macd(out["Close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        out["macd"] = macd.iloc[:, 0]
        out["macd_hist"] = macd.iloc[:, 1]
        out["macd_signal"] = macd.iloc[:, 2]
    else:
        out[["macd", "macd_hist", "macd_signal"]] = np.nan

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb = ta.bbands(out["Close"], length=20, std=2)
    if bb is not None and not bb.empty:
        out["bb_upper"] = bb.iloc[:, 0]
        out["bb_lower"] = bb.iloc[:, 2]
        mid = bb.iloc[:, 1]
        width = (bb.iloc[:, 0] - bb.iloc[:, 2]) / (mid + 1e-8)
        pct_b = (out["Close"] - bb.iloc[:, 2]) / (bb.iloc[:, 0] - bb.iloc[:, 2] + 1e-8)
        out["bb_width"] = width
        out["bb_pct"] = pct_b
    else:
        out[["bb_upper", "bb_lower", "bb_width", "bb_pct"]] = np.nan

    # ── ATR ───────────────────────────────────────────────────────────────────
    out["atr_14"] = ta.atr(out["High"], out["Low"], out["Close"], length=14)

    # ── OBV (normalised by 20-day rolling mean) ───────────────────────────────
    obv = ta.obv(out["Close"], out["Volume"])
    out["obv_norm"] = obv / (obv.rolling(20).mean().abs() + 1e-8)

    # ── VWAP proxy ────────────────────────────────────────────────────────────
    typical = (out["High"] + out["Low"] + out["Close"]) / 3
    vwap = (typical * out["Volume"]).rolling(20).sum() / (out["Volume"].rolling(20).sum() + 1e-8)
    out["vwap_proxy"] = (out["Close"] - vwap) / (vwap + 1e-8)

    # ── Moving Averages ───────────────────────────────────────────────────────
    out["sma_20"] = ta.sma(out["Close"], length=20)
    out["sma_50"] = ta.sma(out["Close"], length=50)
    out["ema_21"] = ta.ema(out["Close"], length=21)
    # Normalise by price
    for col in ["sma_20", "sma_50", "ema_21"]:
        out[col] = (out["Close"] - out[col]) / (out[col] + 1e-8)

    # ── Stochastic ────────────────────────────────────────────────────────────
    stoch = ta.stoch(out["High"], out["Low"], out["Close"])
    if stoch is not None and not stoch.empty:
        out["stoch_k"] = stoch.iloc[:, 0] / 100.0
        out["stoch_d"] = stoch.iloc[:, 1] / 100.0
    else:
        out[["stoch_k", "stoch_d"]] = np.nan

    # ── ADX ───────────────────────────────────────────────────────────────────
    adx = ta.adx(out["High"], out["Low"], out["Close"], length=14)
    if adx is not None and not adx.empty:
        out["adx_14"] = adx.iloc[:, 0] / 100.0
    else:
        out["adx_14"] = np.nan

    # ── CCI ───────────────────────────────────────────────────────────────────
    out["cci_14"] = ta.cci(out["High"], out["Low"], out["Close"], length=14) / 200.0

    # ── ROC ───────────────────────────────────────────────────────────────────
    out["roc_10"] = ta.roc(out["Close"], length=10) / 100.0

    return out


def build_feature_matrix(
    ohlcv_dict: dict[str, pd.DataFrame],
    mamba_latents: dict[str, pd.DataFrame] | None = None,
    label_horizon: int = 5,
) -> tuple[pd.DataFrame, pd.Series]:
    """Build a stacked (ticker, date) feature matrix for ML training.

    Returns:
        X: feature DataFrame with MultiIndex (date, ticker)
        y: 5-day forward excess return Series (same index)
    """
    frames = []

    # We need the Nifty index for computing excess returns
    from quantis.ingestion.market_data import fetch_index_data
    from datetime import date, timedelta

    start_dates = [df.index.min() for df in ohlcv_dict.values() if not df.empty]
    end_dates = [df.index.max() for df in ohlcv_dict.values() if not df.empty]
    if not start_dates:
        return pd.DataFrame(), pd.Series()

    start = min(start_dates).strftime("%Y-%m-%d")
    end = max(end_dates).strftime("%Y-%m-%d")
    idx_data = fetch_index_data(start, end)
    nifty_fwd = idx_data["nifty_return"].shift(-label_horizon).rolling(label_horizon).sum()

    for ticker, df in ohlcv_dict.items():
        if df.empty:
            continue
        try:
            ind = compute_indicators(df)
            ta_cols = [c for c in TA_FEATURE_NAMES if c in ind.columns]
            feat = ind[ta_cols].copy()

            # Lag features by 1 day to prevent look-ahead
            feat = feat.shift(1)

            # Add Mamba latent if available
            if mamba_latents and ticker in mamba_latents:
                lat = mamba_latents[ticker]
                feat = feat.join(lat, how="left")

            # 5-day forward excess return label
            fwd_return = df["Close"].pct_change(label_horizon).shift(-label_horizon)
            excess_return = fwd_return.subtract(nifty_fwd.reindex(fwd_return.index), fill_value=0)

            feat["_ticker"] = ticker
            feat["_label"] = excess_return

            frames.append(feat)
        except Exception as exc:
            logger.warning("Failed to build features for %s: %s", ticker, exc)

    if not frames:
        return pd.DataFrame(), pd.Series()

    combined = pd.concat(frames)
    combined = combined.dropna(subset=["_label"])

    feature_cols = [c for c in combined.columns if c not in ("_ticker", "_label")]
    X = combined[feature_cols].copy()
    y = combined["_label"].copy()

    # Fill remaining NaNs with column median (robust to outliers)
    X = X.fillna(X.median())

    return X, y
