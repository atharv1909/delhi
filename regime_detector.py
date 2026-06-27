"""HMM Market Regime Detector.

4-state Hidden Markov Model: Bull / Bear / HighVol / Ranging.
Runs continuously on live market features, gates portfolio deployment.
"""
from __future__ import annotations

import logging
from enum import IntEnum
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

from quantis.config import (
    HMM_COVARIANCE_TYPE,
    HMM_N_COMPONENTS,
    HMM_N_INIT,
    HMM_N_ITER,
    KELLY_REGIME_FACTORS,
    MODELS_DIR,
)

logger = logging.getLogger(__name__)

_MODEL_PATH = MODELS_DIR / "hmm_regime.pkl"
_SCALER_PATH = MODELS_DIR / "hmm_scaler.pkl"

# Maps HMM state index → regime name (assigned post-hoc by mean return / vol)
_STATE_NAMES = ["bull", "bear", "high_vol", "ranging"]


class RegimeIndex(IntEnum):
    BULL = 0
    BEAR = 1
    HIGH_VOL = 2
    RANGING = 3


class RegimeDetector:
    """Fits a Gaussian HMM on market features and predicts regime at each date."""

    def __init__(self) -> None:
        self.model: GaussianHMM | None = None
        self.scaler = StandardScaler()
        self.state_map: dict[int, str] = {}   # raw HMM state → regime name
        self.trained_date: str | None = None

    def _build_features(
        self,
        nifty_return: pd.Series,
        nifty_vol: pd.Series,
        vix_percentile: pd.Series,
        fii_zscore: pd.Series | None = None,
    ) -> np.ndarray:
        """Build 4-dim feature matrix for HMM.

        Features:
          1. 20-day rolling annualised return of NIFTY 50
          2. 20-day rolling annualised volatility of NIFTY 50
          3. India VIX percentile rank (0-1 over 1-year window)
          4. FII net flow Z-score (20-day window)
        """
        aligned = pd.DataFrame({
            "ret": nifty_return,
            "vol": nifty_vol,
            "vix": vix_percentile,
        })
        if fii_zscore is not None:
            aligned["fii"] = fii_zscore.reindex(aligned.index, method="ffill")
        else:
            aligned["fii"] = 0.0

        aligned = aligned.dropna()
        return aligned.values, aligned.index

    def train(
        self,
        idx_data: pd.DataFrame,
        fii_zscore: pd.Series | None = None,
    ) -> dict:
        """Train HMM on 5+ years of NSE index data.

        idx_data must contain: nifty_return, nifty_vol_20d, vix_percentile.
        """
        feat_arr, dates = self._build_features(
            idx_data["nifty_return"],
            idx_data.get("nifty_vol_20d", idx_data["nifty_return"].rolling(20).std() * np.sqrt(252)),
            idx_data.get("vix_percentile", pd.Series(0.5, index=idx_data.index)),
            fii_zscore,
        )

        feat_scaled = self.scaler.fit_transform(feat_arr)

        # Multiple restarts for robustness
        best_model = None
        best_score = -np.inf
        for trial in range(HMM_N_INIT):
            try:
                model = GaussianHMM(
                    n_components=HMM_N_COMPONENTS,
                    covariance_type=HMM_COVARIANCE_TYPE,
                    n_iter=HMM_N_ITER,
                    random_state=trial,
                )
                model.fit(feat_scaled)
                score = model.score(feat_scaled)
                if score > best_score:
                    best_score = score
                    best_model = model
            except Exception as exc:
                logger.debug("HMM trial %d failed: %s", trial, exc)

        if best_model is None:
            raise RuntimeError("HMM failed to converge")

        self.model = best_model

        # Assign regime names to states by mean return
        states = self.model.predict(feat_scaled)
        nifty_ret_arr = idx_data["nifty_return"].dropna().reindex(pd.DatetimeIndex(dates)).values

        state_stats: dict[int, dict] = {}
        for s in range(HMM_N_COMPONENTS):
            mask = states == s
            ret_s = nifty_ret_arr[mask]
            vol_s = feat_arr[mask, 1]
            state_stats[s] = {
                "mean_ret": float(np.nanmean(ret_s)),
                "mean_vol": float(np.nanmean(vol_s)),
                "n": int(mask.sum()),
            }

        # Assign: highest mean return → bull
        #         lowest mean return → bear
        #         highest vol → high_vol
        #         remainder → ranging
        sorted_by_ret = sorted(state_stats.keys(), key=lambda s: state_stats[s]["mean_ret"], reverse=True)
        sorted_by_vol = sorted(state_stats.keys(), key=lambda s: state_stats[s]["mean_vol"], reverse=True)

        self.state_map = {}
        self.state_map[sorted_by_ret[0]] = "bull"
        self.state_map[sorted_by_ret[-1]] = "bear"
        remaining = [s for s in range(HMM_N_COMPONENTS) if s not in self.state_map]
        high_vol_state = max(remaining, key=lambda s: state_stats[s]["mean_vol"])
        self.state_map[high_vol_state] = "high_vol"
        for s in remaining:
            if s != high_vol_state:
                self.state_map[s] = "ranging"

        logger.info("HMM state map: %s", self.state_map)
        for s, stats in state_stats.items():
            logger.info("  State %d (%s): ret=%.4f vol=%.4f n=%d",
                        s, self.state_map.get(s, "?"), stats["mean_ret"], stats["mean_vol"], stats["n"])

        # Check diagonal persistence
        trans = self.model.transmat_
        diag = np.diag(trans)
        logger.info("HMM transition diagonal: %s (want > 0.9)", np.round(diag, 3).tolist())
        if np.any(diag < 0.7):
            logger.warning("Low diagonal in transition matrix — regimes may be unstable")

        self.trained_date = pd.Timestamp.now().isoformat()
        joblib.dump(self, _MODEL_PATH)
        logger.info("HMM training complete. Log-likelihood=%.2f", best_score)
        return {"log_likelihood": best_score, "state_map": self.state_map}

    def predict_current(
        self,
        idx_data: pd.DataFrame,
        fii_zscore: pd.Series | None = None,
    ) -> dict:
        """Predict current regime from the most recent data point.

        Returns: {state: str, confidence: float, kelly_factor: float,
                  transition_probs: list[float]}
        """
        if self.model is None:
            raise RuntimeError("HMM not trained")

        feat_arr, _ = self._build_features(
            idx_data["nifty_return"],
            idx_data.get("nifty_vol_20d", idx_data["nifty_return"].rolling(20).std() * np.sqrt(252)),
            idx_data.get("vix_percentile", pd.Series(0.5, index=idx_data.index)),
            fii_zscore,
        )

        feat_scaled = self.scaler.transform(feat_arr)

        # Get state sequence
        states = self.model.predict(feat_scaled)
        current_raw_state = int(states[-1])
        regime_name = self.state_map.get(current_raw_state, "ranging")

        # Posterior probabilities for confidence
        posteriors = self.model.predict_proba(feat_scaled)
        confidence = float(posteriors[-1, current_raw_state])

        # Transition probabilities from current state
        trans_probs = self.model.transmat_[current_raw_state].tolist()

        return {
            "state": regime_name,
            "confidence": confidence,
            "kelly_factor": KELLY_REGIME_FACTORS.get(regime_name, 0.0),
            "transition_probs": trans_probs,
            "raw_state": current_raw_state,
        }

    def predict_history(
        self,
        idx_data: pd.DataFrame,
        fii_zscore: pd.Series | None = None,
    ) -> pd.Series:
        """Return regime name for each historical date (for backtest use)."""
        if self.model is None:
            raise RuntimeError("HMM not trained")

        feat_arr, dates = self._build_features(
            idx_data["nifty_return"],
            idx_data.get("nifty_vol_20d", idx_data["nifty_return"].rolling(20).std() * np.sqrt(252)),
            idx_data.get("vix_percentile", pd.Series(0.5, index=idx_data.index)),
            fii_zscore,
        )

        feat_scaled = self.scaler.transform(feat_arr)
        states = self.model.predict(feat_scaled)
        regime_names = [self.state_map.get(int(s), "ranging") for s in states]
        return pd.Series(regime_names, index=pd.DatetimeIndex(dates), name="regime")

    @classmethod
    def load(cls) -> "RegimeDetector | None":
        if not _MODEL_PATH.exists():
            return None
        try:
            inst = joblib.load(_MODEL_PATH)
            return inst
        except Exception as exc:
            logger.error("Failed to load HMM: %s", exc)
            return None
