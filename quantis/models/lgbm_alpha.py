"""LightGBM Alpha Model.

Predicts 5-day forward excess return over NIFTY 50.
Uses purged walk-forward cross-validation with 21-day embargo.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import RobustScaler

from quantis.config import LGBM_PARAMS, MODELS_DIR, WF_EMBARGO_DAYS

logger = logging.getLogger(__name__)

_MODEL_PATH = MODELS_DIR / "lgbm_alpha.pkl"
_SCALER_PATH = MODELS_DIR / "lgbm_scaler.pkl"


class LGBMAlphaModel:
    """Wrapper around LightGBM for alpha prediction with SHAP support."""

    def __init__(self) -> None:
        self.model: lgb.LGBMRegressor | None = None
        self.scaler = RobustScaler()
        self.feature_names: list[str] = []

    def _purged_cv_splits(
        self,
        n_samples: int,
        n_splits: int = 5,
        embargo: int = WF_EMBARGO_DAYS,
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        """Generate purged time-series CV splits with embargo gap."""
        tscv = TimeSeriesSplit(n_splits=n_splits)
        splits = []
        indices = np.arange(n_samples)
        for train_idx, val_idx in tscv.split(indices):
            # Apply embargo: remove train indices too close to val start
            val_start = val_idx[0]
            purged_train = train_idx[train_idx < val_start - embargo]
            if len(purged_train) > 100:
                splits.append((purged_train, val_idx))
        return splits

    def train(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """Train LightGBM model. Returns validation metrics."""
        self.feature_names = list(X.columns)

        X_arr = self.scaler.fit_transform(X.values)
        y_arr = y.values.astype(np.float32)

        n_samples = len(X_arr)
        splits = self._purged_cv_splits(n_samples)
        if not splits:
            raise ValueError("Insufficient data for cross-validation")

        ic_scores: list[float] = []
        best_model: lgb.LGBMRegressor | None = None
        best_ic = -np.inf

        for fold_idx, (train_idx, val_idx) in enumerate(splits):
            X_train, X_val = X_arr[train_idx], X_arr[val_idx]
            y_train, y_val = y_arr[train_idx], y_arr[val_idx]

            model = lgb.LGBMRegressor(**LGBM_PARAMS)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
            )

            val_pred = model.predict(X_val)
            if len(val_pred) > 2:
                ic, _ = pearsonr(val_pred, y_val)
            else:
                ic = 0.0

            ic_scores.append(ic)
            logger.info("LGBM fold %d/%d — IC=%.4f", fold_idx + 1, len(splits), ic)

            if ic > best_ic:
                best_ic = ic
                best_model = model

        mean_ic = float(np.mean(ic_scores))
        ic_ir = float(np.mean(ic_scores) / (np.std(ic_scores) + 1e-8))

        if mean_ic < 0.03:
            logger.warning("LGBM mean IC=%.4f < 0.03 — model has weak signal", mean_ic)

        # Final model on full data
        self.model = lgb.LGBMRegressor(**LGBM_PARAMS)
        self.model.fit(X_arr, y_arr, callbacks=[lgb.log_evaluation(period=-1)])

        joblib.dump(self, _MODEL_PATH)
        logger.info("LGBM training complete. Mean IC=%.4f, IC-IR=%.4f", mean_ic, ic_ir)
        return {"mean_ic": mean_ic, "ic_ir": ic_ir, "n_folds": len(splits)}

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict alpha for each row in X."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        X_aligned = X.reindex(columns=self.feature_names, fill_value=0.0)
        X_arr = self.scaler.transform(X_aligned.fillna(0).values)
        return self.model.predict(X_arr)

    def predict_single(self, features: dict[str, float]) -> float:
        """Predict alpha for a single feature dict."""
        df = pd.DataFrame([features])
        for col in self.feature_names:
            if col not in df.columns:
                df[col] = 0.0
        return float(self.predict(df[self.feature_names])[0])

    def shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """Compute SHAP values using fast TreeExplainer."""
        import shap
        if self.model is None:
            raise RuntimeError("Model not trained")
        explainer = shap.TreeExplainer(self.model)
        X_arr = self.scaler.transform(X[self.feature_names].fillna(0).values)
        sv = explainer.shap_values(X_arr)
        return sv

    def top_shap_features(self, X_row: pd.DataFrame, top_n: int = 10) -> dict[str, float]:
        """Return top-N SHAP features for a single prediction."""
        sv = self.shap_values(X_row)
        if sv is None or len(sv) == 0:
            return {}
        shap_row = sv[0] if sv.ndim == 2 else sv
        pairs = sorted(
            zip(self.feature_names, shap_row.tolist()),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )
        return dict(pairs[:top_n])


def load_lgbm_model() -> LGBMAlphaModel | None:
    """Load pre-trained LGBM model from disk."""
    if not _MODEL_PATH.exists():
        return None
    try:
        obj = joblib.load(_MODEL_PATH)
        if isinstance(obj, dict):
            inst = LGBMAlphaModel()
            inst.model = obj.get("model")
            inst.scaler = obj.get("scaler")
            inst.feature_names = obj.get("feature_names", obj.get("feature_cols", []))
            return inst
        return obj
    except Exception as exc:
        logger.error("Failed to load LGBM: %s", exc)
        return None
