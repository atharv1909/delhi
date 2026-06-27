"""Model Efficacy Monitor & Deployment Gate.

Tracks rolling Information Coefficient (IC) between predicted and realised
alpha. Triggers DEGRADED/BLOCKED gate when IC drops, preventing bad trades.

This is the primary research-grade USP of QUANTIS.
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime

import numpy as np
import pandas as pd

from quantis.api.schemas import GateStatus
from quantis.config import (
    IC_BLOCKED_THRESHOLD,
    IC_DEGRADED_DAYS,
    IC_DEGRADED_THRESHOLD,
    IC_RECOVERY_DAYS,
    IC_RECOVERY_THRESHOLD,
    IC_ROLLING_WINDOW,
)

logger = logging.getLogger(__name__)


class EfficacyMonitor:
    """Rolling IC tracker with deployment gate logic.

    Call `record_predictions()` when signals are generated.
    Call `record_realisations()` 5 trading days later.
    Call `get_gate_status()` before submitting any trade.
    """

    def __init__(self) -> None:
        # Stores {date_str: {ticker: predicted_alpha}}
        self._predictions: dict[str, dict[str, float]] = {}
        # Stores {date_str: {ticker: realised_return}}
        self._realisations: dict[str, dict[str, float]] = {}
        # Rolling IC history
        self._ic_history: deque[tuple[str, float]] = deque(maxlen=IC_ROLLING_WINDOW * 3)

        # Gate state
        self._gate_status: GateStatus = GateStatus.active
        self._consecutive_below_degraded: int = 0
        self._consecutive_above_recovery: int = 0
        self._current_ic: float = 0.0

    def record_predictions(self, date: str, predictions: dict[str, float]) -> None:
        """Store model predictions at signal generation time."""
        self._predictions[date] = predictions
        logger.debug("EfficacyMonitor: recorded %d predictions for %s", len(predictions), date)

    def record_realisations(self, date: str, realisations: dict[str, float]) -> None:
        """Record realised 5-day returns and compute IC.

        This should be called ~5 trading days after record_predictions.
        """
        self._realisations[date] = realisations

        # Find the corresponding prediction date (signal day for this realisation)
        pred_date = date   # In walk-forward, they align by construction
        if pred_date not in self._predictions:
            return

        pred = self._predictions[pred_date]
        real = realisations

        common_tickers = [t for t in pred if t in real]
        if len(common_tickers) < 3:
            logger.warning("Too few common tickers (%d) to compute IC", len(common_tickers))
            return

        pred_vec = np.array([pred[t] for t in common_tickers])
        real_vec = np.array([real[t] for t in common_tickers])

        if np.std(pred_vec) < 1e-8 or np.std(real_vec) < 1e-8:
            ic = 0.0
        else:
            ic = float(np.corrcoef(pred_vec, real_vec)[0, 1])
            if np.isnan(ic):
                ic = 0.0

        self._ic_history.append((date, ic))
        self._current_ic = ic
        self._update_gate(ic)
        logger.info("IC[%s]=%.4f | gate=%s", date, ic, self._gate_status)

    def _update_gate(self, ic: float) -> None:
        """Update gate status based on IC value."""
        if ic < IC_DEGRADED_THRESHOLD:
            self._consecutive_below_degraded += 1
            self._consecutive_above_recovery = 0
        elif ic >= IC_RECOVERY_THRESHOLD:
            self._consecutive_above_recovery += 1
            self._consecutive_below_degraded = 0
        else:
            self._consecutive_below_degraded = 0
            self._consecutive_above_recovery = 0

        # Transition logic
        if self._gate_status == GateStatus.active:
            if self._consecutive_below_degraded >= IC_DEGRADED_DAYS:
                self._gate_status = GateStatus.degraded
                logger.warning("GATE → DEGRADED: IC below %.3f for %d days",
                               IC_DEGRADED_THRESHOLD, IC_DEGRADED_DAYS)

        elif self._gate_status == GateStatus.degraded:
            if ic < IC_BLOCKED_THRESHOLD:
                self._gate_status = GateStatus.blocked
                logger.error("GATE → BLOCKED: IC < %.3f (negative predictive power)", IC_BLOCKED_THRESHOLD)
            elif self._consecutive_above_recovery >= IC_RECOVERY_DAYS:
                self._gate_status = GateStatus.active
                logger.info("GATE → ACTIVE: IC recovered above %.3f for %d days",
                            IC_RECOVERY_THRESHOLD, IC_RECOVERY_DAYS)

        elif self._gate_status == GateStatus.blocked:
            if self._consecutive_above_recovery >= IC_RECOVERY_DAYS:
                self._gate_status = GateStatus.degraded   # Recover to degraded first
                logger.info("GATE → DEGRADED (recovering from BLOCKED)")

    def get_gate_status(self) -> GateStatus:
        return self._gate_status

    def get_current_ic(self) -> float:
        return self._current_ic

    def get_ic_series(self) -> pd.Series:
        """Return rolling IC history as a pandas Series."""
        if not self._ic_history:
            return pd.Series(dtype=float)
        dates, values = zip(*self._ic_history)
        return pd.Series(values, index=pd.to_datetime(list(dates)), name="ic")

    def get_rolling_ic(self, window: int = IC_ROLLING_WINDOW) -> float:
        """Return mean IC over the last `window` observations."""
        if not self._ic_history:
            return 0.0
        recent = list(self._ic_history)[-window:]
        return float(np.mean([v for _, v in recent]))

    def should_trade(self) -> bool:
        """Returns True if new positions may be opened."""
        return self._gate_status == GateStatus.active

    def state_dict(self) -> dict:
        """Serialise state for persistence."""
        return {
            "gate_status": self._gate_status.value,
            "current_ic": self._current_ic,
            "ic_history": list(self._ic_history),
            "consecutive_below_degraded": self._consecutive_below_degraded,
            "consecutive_above_recovery": self._consecutive_above_recovery,
        }

    def load_state_dict(self, state: dict) -> None:
        """Restore from serialised state."""
        self._gate_status = GateStatus(state.get("gate_status", "active"))
        self._current_ic = state.get("current_ic", 0.0)
        self._ic_history = deque(state.get("ic_history", []), maxlen=IC_ROLLING_WINDOW * 3)
        self._consecutive_below_degraded = state.get("consecutive_below_degraded", 0)
        self._consecutive_above_recovery = state.get("consecutive_above_recovery", 0)
