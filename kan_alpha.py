"""KAN (Kolmogorov-Arnold Network) Alpha Model.

Interpretable spline-activation network predicting 5-day forward alpha.
Uses purged CV with IC metric. SHAP via KernelExplainer (async-safe).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from scipy.stats import pearsonr
from sklearn.preprocessing import RobustScaler

from quantis.config import (
    KAN_EARLY_STOP,
    KAN_EPOCHS,
    KAN_GRID_SIZE,
    KAN_LR,
    KAN_SPLINE_ORDER,
    KAN_WIDTH,
    MODELS_DIR,
    WF_EMBARGO_DAYS,
)

logger = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_MODEL_PATH = MODELS_DIR / "kan_alpha.pt"
_SCALER_PATH = MODELS_DIR / "kan_scaler.pkl"


# ── B-Spline Basis ─────────────────────────────────────────────────────────────

def _bspline_basis(x: torch.Tensor, grid: torch.Tensor, k: int) -> torch.Tensor:
    """Compute B-spline basis functions of order k on grid."""
    # x: (...,), grid: (G+1,)
    x = x.unsqueeze(-1)  # (..., 1)

    # Order 0: indicator
    basis = ((x >= grid[:-1]) & (x < grid[1:])).float()

    # Recurrence
    for order in range(1, k + 1):
        left_denom = grid[order:] - grid[:-order]
        right_denom = grid[order + 1:] - grid[1: -order + len(grid) - order]

        left = (x - grid[:-order]) / (left_denom + 1e-8) * basis[..., :-1]
        right = (grid[order + 1:] - x) / (right_denom + 1e-8) * basis[..., 1:]
        basis = left + right

    return basis  # (..., n_basis)


class SplineLayer(nn.Module):
    """KAN layer: each input-output pair has a learnable spline activation."""

    def __init__(
        self,
        in_features: int,
        out_features: int,
        grid_size: int = KAN_GRID_SIZE,
        spline_order: int = KAN_SPLINE_ORDER,
        grid_range: tuple[float, float] = (-3.0, 3.0),
    ) -> None:
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.grid_size = grid_size
        self.spline_order = spline_order
        n_basis = grid_size + spline_order  # number of basis functions

        # Grid (fixed)
        grid = torch.linspace(grid_range[0], grid_range[1], grid_size + 1)
        # Extend grid for boundary conditions
        extended = torch.cat([
            grid[0:1] - (grid[1] - grid[0]) * spline_order,
            grid,
            grid[-1:] + (grid[1] - grid[0]) * spline_order,
        ])
        self.register_buffer("grid", extended)

        # Learnable spline coefficients and residual linear weights
        self.coeff = nn.Parameter(torch.randn(out_features, in_features, n_basis) * 0.1)
        self.linear_weight = nn.Parameter(torch.randn(out_features, in_features) * 0.1)
        self.bias = nn.Parameter(torch.zeros(out_features))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, in_features) → (B, out_features)"""
        B = x.shape[0]
        # Clamp to grid range
        x_clamped = x.clamp(self.grid[self.spline_order].item(), self.grid[-(self.spline_order + 1)].item())

        # Compute basis for each input
        # x_clamped: (B, in_features)
        # We process each input feature independently
        outputs = []
        for j in range(self.in_features):
            basis = _bspline_basis(x_clamped[:, j], self.grid, self.spline_order)  # (B, n_basis)
            # Spline output for each output neuron
            spline_out = (basis.unsqueeze(1) * self.coeff[:, j, :].unsqueeze(0)).sum(-1)  # (B, out_features)
            # Residual linear
            linear_out = x_clamped[:, j:j+1] * self.linear_weight[:, j].unsqueeze(0)  # (B, out_features)
            outputs.append(spline_out + linear_out)

        out = sum(outputs) + self.bias.unsqueeze(0)  # (B, out_features)
        return out


class KANModel(nn.Module):
    """Kolmogorov-Arnold Network for alpha prediction."""

    def __init__(
        self,
        width: list[int] = KAN_WIDTH,
        grid_size: int = KAN_GRID_SIZE,
        spline_order: int = KAN_SPLINE_ORDER,
    ) -> None:
        super().__init__()
        self.layers = nn.ModuleList([
            SplineLayer(width[i], width[i + 1], grid_size, spline_order)
            for i in range(len(width) - 1)
        ])
        self.act = nn.SiLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for i, layer in enumerate(self.layers[:-1]):
            x = self.act(layer(x))
        return self.layers[-1](x).squeeze(-1)


class KANAlphaModel:
    """Training + inference wrapper for KAN."""

    def __init__(self) -> None:
        self.model: KANModel | None = None
        self.scaler = RobustScaler()
        self.feature_names: list[str] = []
        self.background_X: np.ndarray | None = None

    def _purged_splits(self, n: int, n_splits: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
        from sklearn.model_selection import TimeSeriesSplit
        tscv = TimeSeriesSplit(n_splits=n_splits)
        splits = []
        for train_idx, val_idx in tscv.split(np.arange(n)):
            val_start = val_idx[0]
            purged = train_idx[train_idx < val_start - WF_EMBARGO_DAYS]
            if len(purged) > 100:
                splits.append((purged, val_idx))
        return splits

    def train(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """Train KAN model with purged CV and early stopping."""
        self.feature_names = list(X.columns)
        width = [len(self.feature_names)] + KAN_WIDTH[1:]

        X_arr = self.scaler.fit_transform(X.values).astype(np.float32)
        y_arr = y.values.astype(np.float32)

        # Store background for SHAP
        import shap
        bg_size = min(100, len(X_arr))
        bg_idx = np.random.choice(len(X_arr), bg_size, replace=False)
        self.background_X = X_arr[bg_idx]

        splits = self._purged_splits(len(X_arr))
        ic_scores: list[float] = []

        for fold_idx, (train_idx, val_idx) in enumerate(splits):
            model = KANModel(width=width).to(DEVICE)
            optimizer = torch.optim.Adam(model.parameters(), lr=KAN_LR)
            scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
            criterion = nn.MSELoss()

            X_tr = torch.tensor(X_arr[train_idx]).to(DEVICE)
            y_tr = torch.tensor(y_arr[train_idx]).to(DEVICE)
            X_vl = torch.tensor(X_arr[val_idx]).to(DEVICE)
            y_vl_np = y_arr[val_idx]

            best_val_ic = -np.inf
            patience_count = 0
            best_state = None

            for epoch in range(KAN_EPOCHS):
                model.train()
                # Mini-batch gradient descent
                perm = torch.randperm(len(X_tr))
                batch_size = min(256, len(X_tr))
                for start in range(0, len(X_tr), batch_size):
                    idx = perm[start: start + batch_size]
                    optimizer.zero_grad()
                    pred = model(X_tr[idx])
                    loss = criterion(pred, y_tr[idx])
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()

                # Validation IC
                model.eval()
                with torch.no_grad():
                    val_pred = model(X_vl).cpu().numpy()
                if len(val_pred) > 2:
                    ic, _ = pearsonr(val_pred, y_vl_np)
                else:
                    ic = 0.0
                scheduler.step(-ic)

                if ic > best_val_ic:
                    best_val_ic = ic
                    best_state = {k: v.clone() for k, v in model.state_dict().items()}
                    patience_count = 0
                else:
                    patience_count += 1

                if patience_count >= KAN_EARLY_STOP:
                    break

            ic_scores.append(best_val_ic)
            logger.info("KAN fold %d/%d — best IC=%.4f", fold_idx + 1, len(splits), best_val_ic)

        mean_ic = float(np.mean(ic_scores))
        if mean_ic < 0.03:
            logger.warning("KAN mean IC=%.4f < 0.03", mean_ic)

        # Final model on full data
        self.model = KANModel(width=width).to(DEVICE)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=KAN_LR)
        X_full = torch.tensor(X_arr).to(DEVICE)
        y_full = torch.tensor(y_arr).to(DEVICE)
        criterion = nn.MSELoss()

        for epoch in range(KAN_EPOCHS // 2):
            self.model.train()
            perm = torch.randperm(len(X_full))
            batch_size = min(256, len(X_full))
            for start in range(0, len(X_full), batch_size):
                idx = perm[start: start + batch_size]
                optimizer.zero_grad()
                pred = self.model(X_full[idx])
                loss = criterion(pred, y_full[idx])
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()

        torch.save({
            "model": self.model.state_dict(),
            "width": width,
            "feature_names": self.feature_names,
            "background": self.background_X,
        }, _MODEL_PATH)
        joblib.dump(self.scaler, _SCALER_PATH)

        logger.info("KAN training complete. Mean IC=%.4f", mean_ic)
        return {"mean_ic": mean_ic, "ic_ir": mean_ic / (np.std(ic_scores) + 1e-8)}

    @torch.no_grad()
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("KAN not trained")
        X_arr = self.scaler.transform(X[self.feature_names].fillna(0).values).astype(np.float32)
        tensor = torch.tensor(X_arr).to(DEVICE)
        self.model.eval()
        return self.model(tensor).cpu().numpy()

    def predict_fn(self, X_arr: np.ndarray) -> np.ndarray:
        """Predict from numpy array (for KernelExplainer)."""
        if self.model is None:
            return np.zeros(len(X_arr))
        tensor = torch.tensor(X_arr.astype(np.float32)).to(DEVICE)
        self.model.eval()
        with torch.no_grad():
            return self.model(tensor).cpu().numpy()

    def top_shap_features(self, X_row: pd.DataFrame, top_n: int = 10) -> dict[str, float]:
        """Compute SHAP values via KernelExplainer (model-agnostic)."""
        import shap
        if self.background_X is None or self.model is None:
            return {}
        try:
            explainer = shap.KernelExplainer(self.predict_fn, self.background_X)
            X_arr = self.scaler.transform(X_row[self.feature_names].fillna(0).values).astype(np.float32)
            sv = explainer.shap_values(X_arr, nsamples=100, silent=True)
            if sv is not None and len(sv):
                shap_row = sv[0] if sv.ndim == 2 else sv
                pairs = sorted(
                    zip(self.feature_names, shap_row.tolist()),
                    key=lambda kv: abs(kv[1]),
                    reverse=True,
                )
                return dict(pairs[:top_n])
        except Exception as exc:
            logger.warning("KAN SHAP failed: %s", exc)
        return {}


def load_kan_model() -> KANAlphaModel | None:
    if not _MODEL_PATH.exists():
        return None
    try:
        ckpt = torch.load(_MODEL_PATH, map_location=DEVICE)
        wrapper = KANAlphaModel()
        wrapper.model = KANModel(width=ckpt["width"]).to(DEVICE)
        wrapper.model.load_state_dict(ckpt["model"])
        wrapper.model.eval()
        wrapper.feature_names = ckpt["feature_names"]
        wrapper.background_X = ckpt.get("background")
        wrapper.scaler = joblib.load(_SCALER_PATH)
        return wrapper
    except Exception as exc:
        logger.error("Failed to load KAN: %s", exc)
        return None
