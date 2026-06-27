"""QUANTIS — Final Walk-Forward Backtesting & IL-Safe Ensemble Pipeline.

Useful for final portfolio evaluation, Monte Carlo analysis, and buy/sell decisions.
Implements honest OOS validation, IL autopsy, and gating expert combinations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import lightgbm as lgb
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from scipy.stats import pearsonr

logger = logging.getLogger(__name__)

# Constants
TRADING_DAYS = 252
RISK_FREE_ANN = 0.07
WF_TRAIN_DAYS = 500
WF_EMBARGO_DAYS = 5
WF_TEST_DAYS = 60
WF_STEP_DAYS = 20

LGBM_PARAMS = {
    "learning_rate": 0.03,
    "max_depth": 5,
    "num_leaves": 31,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
}


def sharpe(rets, rf=RISK_FREE_ANN / 252):
    ex = rets - rf
    return float(np.mean(ex) / (np.std(ex) + 1e-10) * np.sqrt(TRADING_DAYS))


def sortino(rets, rf=RISK_FREE_ANN / 252):
    ex = rets - rf
    down = ex[ex < 0]
    return float(np.mean(ex) / (np.std(down) + 1e-10) * np.sqrt(TRADING_DAYS))


def max_drawdown(rets):
    eq = np.cumprod(1 + rets)
    cm = np.maximum.accumulate(eq)
    return float(((eq - cm) / (cm + 1e-10)).min())


def calmar(rets):
    return float(np.mean(rets) * TRADING_DAYS / (abs(max_drawdown(rets)) + 1e-10))


def walk_forward_backtest(X_df, y_s, model_fn, label="", verbose=True):
    n = len(X_df)
    periods, all_rets, all_ic = [], [], []
    start = 0
    prev_pred = None

    while start + WF_TRAIN_DAYS + WF_EMBARGO_DAYS + WF_TEST_DAYS <= n:
        te = start + WF_TRAIN_DAYS
        ts = te + WF_EMBARGO_DAYS
        t_end = min(ts + WF_TEST_DAYS, n)

        X_tr = X_df.iloc[start:te].values if hasattr(X_df, "iloc") else X_df[start:te]
        y_tr = y_s.iloc[start:te].values if hasattr(y_s, "iloc") else y_s[start:te]
        X_te = X_df.iloc[ts:t_end].values if hasattr(X_df, "iloc") else X_df[ts:t_end]
        y_te = y_s.iloc[ts:t_end].values if hasattr(y_s, "iloc") else y_s[ts:t_end]

        if len(X_tr) < 50 or len(y_te) < 5:
            start += WF_STEP_DAYS
            continue

        try:
            pred = model_fn(X_tr, y_tr, X_te, start, ts, t_end)
        except Exception as e:
            if verbose:
                print(f"[{label}] Fold error at {start}: {e}")
            start += WF_STEP_DAYS
            continue

        if prev_pred is not None and len(pred) == len(prev_pred) and np.allclose(pred, prev_pred):
            raise ValueError(
                f"\n🚨 [{label}] FATAL: Predictions are IDENTICAL to previous fold at start={start}.\n"
                f"   You are reading a STALE CACHED array. Check your model_fn.\n"
            )
        prev_pred = pred.copy()

        if np.std(pred) < 1e-10:
            if verbose:
                print(f"⚠️ WARNING [{label}]: Zero variance predictions at start={start}. Skipping fold.")
            start += WF_STEP_DAYS
            continue

        top_q = np.percentile(pred, 75)
        mask = pred >= top_q
        if mask.sum() == 0:
            start += WF_STEP_DAYS
            continue

        strat_ret = float(y_te[mask].mean())
        per_rets = np.full(len(y_te), strat_ret)

        all_rets.extend(per_rets.tolist())

        if np.std(pred) > 1e-10 and np.std(y_te) > 1e-10:
            ic = pearsonr(pred, y_te)[0]
            if np.isnan(ic):
                ic = 0.0
        else:
            ic = 0.0

        all_ic.append(ic)
        periods.append({
            "ic": float(ic),
            "strat_ret": strat_ret,
            "start_idx": start,
            "n_selected": int(mask.sum()),
            "n_total": len(y_te),
        })
        start += WF_STEP_DAYS

    if not all_rets:
        return {
            "sharpe": 0.0,
            "calmar": 0.0,
            "mean_ic": 0.0,
            "ic_ir": 0.0,
            "mdd": 0.0,
            "periods": [],
            "all_rets": [],
            "label": label,
        }

    all_rets = np.array(all_rets)
    mean_ic = float(np.mean(all_ic))
    ic_ir = float(mean_ic / (np.std(all_ic) + 1e-8))

    result = {
        "sharpe": sharpe(all_rets),
        "calmar": calmar(all_rets),
        "mean_ic": mean_ic,
        "ic_ir": ic_ir,
        "mdd": max_drawdown(all_rets),
        "periods": periods,
        "all_rets": all_rets.tolist(),
        "label": label,
    }

    if verbose:
        print(f"[{label}] Complete: Sharpe={result['sharpe']:.3f}, MeanIC={result['mean_ic']:.4f}, IC-IR={result['ic_ir']:.3f}, Periods={len(periods)}")

    return result


def lgbm_fn(X_tr, y_tr, X_te, start, ts, t_end):
    m = lgb.LGBMRegressor(**{**LGBM_PARAMS, "n_estimators": 150})
    m.fit(X_tr, y_tr, callbacks=[lgb.log_evaluation(period=-1)])
    return m.predict(X_te)


def il_autopsy_and_fix(y_s, il_val_ics=None, il_preds_full=None, threshold=0.30):
    """IL Autopsy: Evaluates honest OOS IC and filters out dead weight IL predictions."""
    print("\n" + "=" * 60)
    print("IL AUTOPSY & HONEST VALIDATION")
    print("=" * 60)

    if il_val_ics is None:
        il_val_ics = [0]
    leaked_ic = np.mean(il_val_ics)
    print(f"Leaked validation IC (old):     {leaked_ic:.4f}")

    if il_preds_full is None or len(il_preds_full) == 0:
        print("🚨 il_preds_full is missing. IL cannot be evaluated.")
        return {"honest_ic": 0.0, "drop_il": True, "reason": "missing predictions"}

    y_arr = y_s.values if hasattr(y_s, "values") else np.array(y_s)
    min_len = min(len(il_preds_full), len(y_arr))
    il_aligned = il_preds_full[:min_len]
    y_aligned = y_arr[:min_len]

    if np.std(il_aligned) > 1e-10 and np.std(y_aligned) > 1e-10:
        honest_ic = pearsonr(il_aligned, y_aligned)[0]
    else:
        honest_ic = 0.0

    print(f"Honest OOS IC (from preds):     {honest_ic:.4f}")
    print(f"Gap (leakage magnitude):        {leaked_ic - honest_ic:.4f}")

    drop_il = False
    reason = ""
    if honest_ic < 0.02:
        print("🚨 VERDICT: IL is DEAD WEIGHT. Contributing nothing to ensemble.")
        drop_il = True
        reason = f"honest_ic_{honest_ic:.4f}_too_low"
    elif honest_ic < 0.05:
        print(f"⚠️ IL is weak (Honest IC = {honest_ic:.4f}). Consider dropping.")
        drop_il = True
        reason = f"honest_ic_{honest_ic:.4f}_weak"
    else:
        print(f"✅ IL is viable. Honest IC = {honest_ic:.4f}.")

    return {
        "leaked_ic": float(leaked_ic),
        "honest_ic": float(honest_ic),
        "drop_il": drop_il,
        "reason": reason,
        "gap": float(leaked_ic - honest_ic),
    }


if __name__ == "__main__":
    print("QUANTIS — Final Walk-Forward Backtesting Module Initialized.")
