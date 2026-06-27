"""QUANTIS — India Market Data Pipeline.

Fetches OHLCV, validates, caches, and prepares DataFrames for modelling.
All data is point-in-time safe (no look-ahead). 
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from pandas_market_calendars import get_calendar

from quantis.config import (
    CACHE_DIR,
    DATA_DIR,
    INDIA_VIX,
    NIFTY50_INDEX,
    NIFTY50_TICKERS,
    NSE_SUFFIX,
    TRADING_DAYS_YEAR,
)

logger = logging.getLogger(__name__)

# ── Joblib cache (1-hr TTL using mtime trick) ──────────────────────────────────
_memory = joblib.Memory(CACHE_DIR, verbose=0)

_NSE_CALENDAR = get_calendar("BSE")   # BSE calendar used as proxy for NSE


def _get_nse_trading_days(start: str, end: str) -> pd.DatetimeIndex:
    sched = _NSE_CALENDAR.schedule(start_date=start, end_date=end)
    return _NSE_CALENDAR.date_range(sched, frequency="1D")


def _cache_path(name: str) -> Path:
    return DATA_DIR / f"{name}.parquet"


# ── Core fetchers ──────────────────────────────────────────────────────────────

def fetch_ohlcv(
    tickers: list[str],
    start: str,
    end: str | None = None,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for multiple tickers. Returns {ticker: DataFrame}.

    DataFrame columns: Open, High, Low, Close, Volume (all float64).
    Indexed by UTC date, sorted ascending. No forward-looking contamination.
    """
    if end is None:
        end = date.today().isoformat()

    result: dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        cache_file = _cache_path(f"ohlcv_{ticker.replace('.', '_')}_{start}_{end}")

        if use_cache and cache_file.exists():
            # Invalidate if >1 hour old
            import time
            if time.time() - cache_file.stat().st_mtime < 3600:
                df = pd.read_parquet(cache_file)
                result[ticker] = df
                continue

        try:
            raw = yf.download(
                ticker,
                start=start,
                end=end,
                progress=False,
                auto_adjust=True,
                prepost=False,
            )
            if raw.empty:
                logger.warning("No data for %s", ticker)
                continue

            # Flatten MultiIndex columns if present
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.index = pd.to_datetime(df.index).tz_localize(None)
            df.sort_index(inplace=True)

            # Drop circuit-breaker rows: volume==0 AND |return| > 4%
            ret = df["Close"].pct_change().abs()
            circuit_mask = (df["Volume"] == 0) & (ret > 0.04)
            if circuit_mask.sum() > 0:
                logger.debug("Dropping %d circuit-breaker rows for %s", circuit_mask.sum(), ticker)
                df = df[~circuit_mask]

            # Require minimum 252 days
            if len(df) < TRADING_DAYS_YEAR:
                logger.warning(
                    "%s has only %d days (<252). Skipping.", ticker, len(df)
                )
                continue

            # Drop if >5% missing candles in lookback
            expected = (pd.to_datetime(end) - pd.to_datetime(start)).days * (252 / 365)
            missing_pct = (expected - len(df)) / expected
            if missing_pct > 0.05:
                logger.warning(
                    "%s has %.1f%% missing candles. Skipping.", ticker, missing_pct * 100
                )
                continue

            df.to_parquet(cache_file)
            result[ticker] = df

        except Exception as exc:
            logger.error("Failed to fetch %s: %s", ticker, exc)

    return result


def fetch_index_data(start: str, end: str | None = None) -> pd.DataFrame:
    """Fetch NIFTY 50 and India VIX data."""
    if end is None:
        end = date.today().isoformat()

    nifty = fetch_ohlcv([NIFTY50_INDEX], start, end)
    vix = fetch_ohlcv([INDIA_VIX], start, end)

    idx_df = pd.DataFrame()
    if NIFTY50_INDEX in nifty:
        idx_df["nifty_close"] = nifty[NIFTY50_INDEX]["Close"]
        idx_df["nifty_return"] = idx_df["nifty_close"].pct_change()
        idx_df["nifty_vol_20d"] = idx_df["nifty_return"].rolling(20).std() * np.sqrt(252)

    if INDIA_VIX in vix:
        vix_close = vix[INDIA_VIX]["Close"]
        idx_df = idx_df.join(vix_close.rename("india_vix"), how="left")
        # VIX percentile rank over rolling 252-day window
        idx_df["vix_percentile"] = (
            idx_df["india_vix"]
            .rolling(252, min_periods=60)
            .rank(pct=True)
        )

    return idx_df.dropna(subset=["nifty_close"])


def fetch_fii_dii_flows(date_str: str | None = None) -> pd.Series:
    """Fetch FII/DII net equity flows from NSE.

    Returns a Series indexed by date with FII net flow in INR crores.
    Falls back to zeros on failure (data isn't always available).
    """
    try:
        import httpx
        url = "https://www.nseindia.com/api/fiidiiTradesEquities"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com",
        }
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()

        rows = []
        for rec in data.get("data", []):
            try:
                trade_date = pd.to_datetime(rec["date"], format="%d-%b-%Y")
                fii_net = float(str(rec.get("netFII", "0")).replace(",", ""))
                rows.append({"date": trade_date, "fii_net_flow": fii_net})
            except (KeyError, ValueError):
                continue

        if rows:
            df = pd.DataFrame(rows).set_index("date").sort_index()
            return df["fii_net_flow"]

    except Exception as exc:
        logger.warning("FII/DII fetch failed: %s — using zeros", exc)

    return pd.Series(dtype=float, name="fii_net_flow")


def build_fii_zscore(fii_series: pd.Series, window: int = 20) -> pd.Series:
    """Compute 20-day z-score of FII net flows."""
    roll_mean = fii_series.rolling(window).mean()
    roll_std = fii_series.rolling(window).std()
    zscore = (fii_series - roll_mean) / (roll_std + 1e-8)
    return zscore.rename("fii_zscore")


def get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fast batch fetch of last-trade prices using yfinance fast_info."""
    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            fi = yf.Ticker(ticker).fast_info
            prices[ticker] = float(fi.get("last_price", fi.get("previous_close", 0.0)))
        except Exception:
            prices[ticker] = 0.0
    return prices


def get_stock_info(tickers: list[str]) -> list[dict]:
    """Get current stock metadata for the /api/stocks endpoint."""
    from quantis.config import SECTOR_MAP

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=60)).isoformat()
    ohlcv = fetch_ohlcv(tickers, start, end, use_cache=True)

    nifty_data = fetch_index_data(start, end)

    results = []
    for ticker in tickers:
        if ticker not in ohlcv:
            continue
        df = ohlcv[ticker]
        close = df["Close"]
        price = float(close.iloc[-1])
        ret_1d = float(close.pct_change().iloc[-1]) if len(close) > 1 else 0.0
        ret_5d = float((close.iloc[-1] / close.iloc[-5] - 1)) if len(close) >= 5 else 0.0
        ret_20d = float((close.iloc[-1] / close.iloc[-20] - 1)) if len(close) >= 20 else 0.0
        vol = int(df["Volume"].iloc[-1])

        results.append({
            "ticker": ticker,
            "name": ticker.replace(NSE_SUFFIX, ""),
            "sector": SECTOR_MAP.get(ticker, "Unknown"),
            "price": price,
            "return_1d": ret_1d,
            "return_5d": ret_5d,
            "return_20d": ret_20d,
            "volume": vol,
        })

    return results
