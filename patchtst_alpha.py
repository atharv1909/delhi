"""QUANTIS — PatchTST Expert Model (replaces LSTM + ARIMA).

Panel time-series forecasting using patch-based Transformer.
Uses neuralforecast for training and inference.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from quantis.config import MODELS_DIR

logger = logging.getLogger(__name__)

_MODEL_PATH = MODELS_DIR / "patchtst_model"


class PatchTSTExpert:
    """Wrapper around neuralforecast PatchTST for alpha prediction."""

    HORIZON = 5
    INPUT_SIZE = 252

    def __init__(self) -> None:
        self.model = None
        self.tickers: list[str] = []
        self.last_trained_date: str | None = None

    def _build_panel_df(self, ohlcv_dict: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Convert {ticker: OHLCV} to long-format panel DataFrame for neuralforecast."""
        frames = []
        for ticker, df in ohlcv_dict.items():
            if df.empty or len(df) < self.INPUT_SIZE + self.HORIZON:
                continue
            panel = pd.DataFrame({
                "unique_id": ticker,
                "ds": df.index,
                "y": df["Close"].values,
            })
            frames.append(panel)

        if not frames:
            raise ValueError("No valid data for PatchTST panel")

        combined = pd.concat(frames, ignore_index=True)
        combined["ds"] = pd.to_datetime(combined["ds"])
        combined = combined.sort_values(["unique_id", "ds"]).reset_index(drop=True)
        return combined

    def train(self, ohlcv_dict: dict[str, pd.DataFrame]) -> dict:
        """Train PatchTST on NSE close price panel."""
        try:
            from neuralforecast import NeuralForecast
            from neuralforecast.models import PatchTST
        except ImportError:
            logger.error("neuralforecast not installed. Run: pip install neuralforecast")
            return {"error": "neuralforecast not installed"}

        self.tickers = [t for t in ohlcv_dict if not ohlcv_dict[t].empty]
        panel_df = self._build_panel_df(ohlcv_dict)

        logger.info("Training PatchTST on %d stocks, %d total rows", len(self.tickers), len(panel_df))

        # Log-transform close prices (more stationary)
        panel_df["y"] = np.log(panel_df["y"] + 1e-8)

        model = PatchTST(
            h=self.HORIZON,
            input_size=self.INPUT_SIZE,
            patch_len=16,
            stride=8,
            d_model=128,
            nhead=4,
            num_encoder_layers=3,
            max_steps=200,
            learning_rate=1e-4,
            gradient_clip_val=1.0,
            batch_size=32,
            scaler_type="standard",
            loss="MSE",
            valid_loss="MSE",
            early_stop_patience_steps=10,
        )

        nf = NeuralForecast(models=[model], freq="B")  # B = business day

        # Split: last 10% as validation (time-safe)
        unique_ids = panel_df["unique_id"].unique()
        val_fraction = 0.1
        train_frames, val_frames = [], []
        for uid in unique_ids:
            sub = panel_df[panel_df["unique_id"] == uid].sort_values("ds")
            cut = max(self.INPUT_SIZE + self.HORIZON, int(len(sub) * (1 - val_fraction)))
            train_frames.append(sub.iloc[:cut])
            if len(sub) > cut:
                val_frames.append(sub.iloc[cut - self.INPUT_SIZE:])

        train_df = pd.concat(train_frames, ignore_index=True)

        try:
            nf.fit(df=train_df)
            self.model = nf

            # Save
            _MODEL_PATH.mkdir(parents=True, exist_ok=True)
            nf.save(path=str(_MODEL_PATH), model_index=None, overwrite=True)
            self.last_trained_date = pd.Timestamp.now().isoformat()
            joblib.dump({"tickers": self.tickers, "trained": self.last_trained_date}, _MODEL_PATH / "meta.pkl")

            logger.info("PatchTST training complete")
            return {"status": "success", "n_stocks": len(self.tickers)}

        except Exception as exc:
            logger.error("PatchTST training failed: %s", exc)
            return {"error": str(exc)}

    def predict_alpha(
        self,
        ohlcv_dict: dict[str, pd.DataFrame],
        nifty_5d_return: float = 0.0,
    ) -> dict[str, float]:
        """Predict 5-day forward return for each ticker, return excess over NIFTY."""
        if self.model is None:
            return {}

        try:
            panel_df = self._build_panel_df(ohlcv_dict)
            panel_df["y"] = np.log(panel_df["y"] + 1e-8)

            # Predict from last INPUT_SIZE points of each ticker
            latest_frames = []
            for uid in panel_df["unique_id"].unique():
                sub = panel_df[panel_df["unique_id"] == uid].sort_values("ds")
                latest_frames.append(sub.tail(self.INPUT_SIZE))

            futr_df = pd.concat(latest_frames, ignore_index=True)
            forecasts = self.model.predict(df=futr_df)

            results: dict[str, float] = {}
            for uid in forecasts["unique_id"].unique():
                sub = forecasts[forecasts["unique_id"] == uid]
                # Sum log-returns over horizon ≈ cumulative 5-day return
                pred_vals = sub[[c for c in sub.columns if "PatchTST" in c]].values.flatten()
                if len(pred_vals) == 0:
                    continue
                # Last known log price
                ticker_hist = panel_df[panel_df["unique_id"] == uid]["y"]
                last_log_price = float(ticker_hist.iloc[-1])
                # 5-day ahead = sum of log-return steps
                fwd_log_price = float(pred_vals[-1]) if len(pred_vals) >= self.HORIZON else float(pred_vals[-1])
                fwd_return = float(np.exp(fwd_log_price - last_log_price) - 1)
                excess = fwd_return - nifty_5d_return
                results[uid] = excess

            return results

        except Exception as exc:
            logger.error("PatchTST predict failed: %s", exc)
            return {}

    @classmethod
    def load(cls) -> "PatchTSTExpert | None":
        if not _MODEL_PATH.exists():
            return None
        try:
            from neuralforecast import NeuralForecast
            instance = cls()
            instance.model = NeuralForecast.load(path=str(_MODEL_PATH))
            meta = joblib.load(_MODEL_PATH / "meta.pkl")
            instance.tickers = meta.get("tickers", [])
            instance.last_trained_date = meta.get("trained")
            return instance
        except Exception as exc:
            logger.error("Failed to load PatchTST: %s", exc)
            return None
