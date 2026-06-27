"""Mixture-of-Experts Gating Network + Alpha Combiner.

GatingNet learns which expert has highest IC in each market regime.
Falls back to weighted average when confidence is low.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from quantis.config import MODELS_DIR

logger = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_MODEL_PATH = MODELS_DIR / "gating_net.pt"

EXPERT_NAMES = ["kan", "lgbm", "patchtst", "il"]
N_EXPERTS = len(EXPERT_NAMES)
REGIME_FALLBACK_CONF = 0.4   # if max softmax < this, use fallback avg


class GatingNet(nn.Module):
    """GatingNet: regime_features → expert_weights.

    Architecture per spec: Linear(4, 32) → ReLU → Dropout(0.2)
                           → Linear(32, 4) → Softmax
    """

    def __init__(self, input_dim: int = 4, n_experts: int = N_EXPERTS) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, n_experts),
        )
        self.softmax = nn.Softmax(dim=-1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.net(x)
        return self.softmax(logits)


class MoEGatingNetwork:
    """Training + inference wrapper for GatingNet."""

    def __init__(self) -> None:
        self.model: GatingNet | None = None

    def _assign_best_expert(
        self,
        expert_preds: dict[str, np.ndarray],
        y_realised: np.ndarray,
    ) -> np.ndarray:
        """For each sample, find which expert prediction is closest to realised."""
        best_labels = np.zeros(len(y_realised), dtype=np.int64)
        pred_matrix = np.stack([expert_preds[e] for e in EXPERT_NAMES], axis=1)  # (N, 4)
        for i in range(len(y_realised)):
            errors = np.abs(pred_matrix[i] - y_realised[i])
            best_labels[i] = int(np.argmin(errors))
        return best_labels

    def train(
        self,
        regime_features: np.ndarray,       # (N, 4) — same as HMM input
        expert_preds: dict[str, np.ndarray],  # {name: (N,) array}
        y_realised: np.ndarray,             # (N,) actual returns
        epochs: int = 100,
        lr: float = 1e-3,
    ) -> dict:
        """Train GatingNet via cross-entropy on best-expert labels."""
        best_labels = self._assign_best_expert(expert_preds, y_realised)

        X = torch.tensor(regime_features.astype(np.float32)).to(DEVICE)
        y = torch.tensor(best_labels).to(DEVICE)

        self.model = GatingNet().to(DEVICE)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.CrossEntropyLoss()

        best_loss = float("inf")
        for epoch in range(epochs):
            self.model.train()
            optimizer.zero_grad()
            logits = self.model.net(X)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            if loss.item() < best_loss:
                best_loss = loss.item()
                torch.save({"model": self.model.state_dict()}, _MODEL_PATH)

        logger.info("GatingNet training complete. Best loss: %.4f", best_loss)
        return {"best_loss": best_loss}

    @torch.no_grad()
    def predict_weights(self, regime_features: np.ndarray) -> tuple[np.ndarray, float]:
        """Return (expert_weights, gate_confidence) for one regime vector.

        expert_weights: array of shape (N_EXPERTS,)
        gate_confidence: max softmax value (high = confident routing)
        """
        if self.model is None:
            # Uniform fallback
            return np.ones(N_EXPERTS) / N_EXPERTS, 0.0

        self.model.eval()
        feat = torch.tensor(regime_features.astype(np.float32)).unsqueeze(0).to(DEVICE)
        weights = self.model(feat).cpu().numpy()[0]
        confidence = float(weights.max())
        return weights, confidence

    @classmethod
    def load(cls) -> "MoEGatingNetwork | None":
        if not _MODEL_PATH.exists():
            return None
        try:
            inst = cls()
            ckpt = torch.load(_MODEL_PATH, map_location=DEVICE)
            inst.model = GatingNet().to(DEVICE)
            inst.model.load_state_dict(ckpt["model"])
            inst.model.eval()
            return inst
        except Exception as exc:
            logger.error("Failed to load GatingNet: %s", exc)
            return None


def combine_expert_alphas(
    expert_alphas: dict[str, float],
    gate_weights: np.ndarray,
    gate_confidence: float,
) -> float:
    """Combine expert alpha predictions using gating weights.

    Implements spec fallback:
      final = gate_confidence * gated_alpha + (1 - gate_confidence) * mean_alpha
    """
    experts_ordered = [EXPERT_NAMES[i] for i in range(N_EXPERTS)]
    alphas = np.array([expert_alphas.get(e, 0.0) for e in experts_ordered])

    gated_alpha = float(np.dot(gate_weights, alphas))
    mean_alpha = float(np.mean(alphas))

    if gate_confidence < REGIME_FALLBACK_CONF:
        # Low confidence: blend toward uniform average
        final = gate_confidence * gated_alpha + (1 - gate_confidence) * mean_alpha
    else:
        final = gated_alpha

    return final
