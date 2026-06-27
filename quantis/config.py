"""InvestEasy — Central Configuration."""
import os
from pathlib import Path

from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "saved_models"
CACHE_DIR = ROOT_DIR / ".cache"

load_dotenv(ROOT_DIR / ".env")

for _d in (DATA_DIR, MODELS_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── API Keys ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
SMALLEST_API_KEY: str = os.environ.get("SMALLEST_API_KEY", "")
COINBASE_API_KEY: str = os.environ.get("COINBASE_API_KEY", "")
COINBASE_API_SECRET: str = os.environ.get("COINBASE_API_SECRET", "")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379")
DATABASE_URL: str = os.environ.get("DATABASE_URL", f"sqlite:///{ROOT_DIR}/investeasy.db")


# ── Market Constants ───────────────────────────────────────────────────────────
RISK_FREE_RATE_ANNUAL: float = 0.071          # India 10-yr G-sec
RISK_FREE_RATE_DAILY: float = RISK_FREE_RATE_ANNUAL / 252
TRADING_DAYS_YEAR: int = 252
NSE_SUFFIX: str = ".NS"

NIFTY50_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "TITAN.NS", "SUNPHARMA.NS", "ULTRACEMCO.NS", "WIPRO.NS", "NTPC.NS",
    "ONGC.NS", "POWERGRID.NS", "M&M.NS", "HCLTECH.NS", "BAJAJFINSV.NS",
    "COALINDIA.NS", "TATAMOTORS.NS", "ADANIENT.NS", "JSWSTEEL.NS",
    "TATASTEEL.NS", "TECHM.NS", "NESTLEIND.NS", "CIPLA.NS", "DIVISLAB.NS",
    "APOLLOHOSP.NS", "DRREDDY.NS", "BRITANNIA.NS", "EICHERMOT.NS",
    "HEROMOTOCO.NS", "GRASIM.NS", "HINDALCO.NS", "BPCL.NS", "TATACONSUM.NS",
    "INDUSINDBK.NS", "SBILIFE.NS", "HDFCLIFE.NS", "UPL.NS",
    "SHREECEM.NS", "ADANIPORTS.NS", "BAJAJ-AUTO.NS",
]

NIFTY50_INDEX = "^NSEI"
INDIA_VIX = "^INDIAVIX"

# ── Sector Mapping ─────────────────────────────────────────────────────────────
SECTOR_MAP: dict[str, str] = {
    "RELIANCE.NS": "Energy", "ONGC.NS": "Energy", "BPCL.NS": "Energy",
    "TCS.NS": "IT", "INFY.NS": "IT", "WIPRO.NS": "IT",
    "HCLTECH.NS": "IT", "TECHM.NS": "IT",
    "HDFCBANK.NS": "Banking", "ICICIBANK.NS": "Banking", "SBIN.NS": "Banking",
    "KOTAKBANK.NS": "Banking", "AXISBANK.NS": "Banking", "INDUSINDBK.NS": "Banking",
    "BAJFINANCE.NS": "NBFC", "BAJAJFINSV.NS": "NBFC",
    "HINDUNILVR.NS": "FMCG", "ITC.NS": "FMCG", "NESTLEIND.NS": "FMCG",
    "BRITANNIA.NS": "FMCG", "TATACONSUM.NS": "FMCG",
    "SUNPHARMA.NS": "Pharma", "CIPLA.NS": "Pharma", "DIVISLAB.NS": "Pharma",
    "DRREDDY.NS": "Pharma", "APOLLOHOSP.NS": "Healthcare",
    "LT.NS": "Infra", "ADANIPORTS.NS": "Infra", "POWERGRID.NS": "Utilities",
    "NTPC.NS": "Utilities", "COALINDIA.NS": "Metals",
    "TATASTEEL.NS": "Metals", "JSWSTEEL.NS": "Metals", "HINDALCO.NS": "Metals",
    "MARUTI.NS": "Auto", "TATAMOTORS.NS": "Auto", "M&M.NS": "Auto",
    "BAJAJ-AUTO.NS": "Auto", "HEROMOTOCO.NS": "Auto", "EICHERMOT.NS": "Auto",
    "ASIANPAINT.NS": "Paints", "TITAN.NS": "Consumer", "ULTRACEMCO.NS": "Cement",
    "SHREECEM.NS": "Cement", "GRASIM.NS": "Cement",
    "BHARTIARTL.NS": "Telecom", "ADANIENT.NS": "Conglomerate",
    "SBILIFE.NS": "Insurance", "HDFCLIFE.NS": "Insurance", "UPL.NS": "Agri",
}

# ── Model Configs ──────────────────────────────────────────────────────────────
MAMBA_D_MODEL: int = 64
MAMBA_D_STATE: int = 16
MAMBA_D_CONV: int = 4
MAMBA_EXPAND: int = 2
MAMBA_SEQ_LEN: int = 60
MAMBA_INPUT_FEATURES: int = 20

KAN_WIDTH = [84, 64, 32, 1]
KAN_GRID_SIZE: int = 5
KAN_SPLINE_ORDER: int = 3
KAN_EPOCHS: int = 100
KAN_LR: float = 1e-3
KAN_EARLY_STOP: int = 10

LGBM_PARAMS = {
    "n_estimators": 500, "learning_rate": 0.03, "num_leaves": 63,
    "max_depth": 6, "feature_fraction": 0.8, "bagging_fraction": 0.8,
    "bagging_freq": 5, "min_child_samples": 20, "objective": "regression",
    "metric": "rmse", "first_metric_only": True, "n_jobs": -1, "verbose": -1,
}

HMM_N_COMPONENTS: int = 4
HMM_N_ITER: int = 100
HMM_N_INIT: int = 10
HMM_COVARIANCE_TYPE: str = "diag"

# ── Portfolio Config ───────────────────────────────────────────────────────────
MAX_SINGLE_STOCK_WEIGHT: float = 0.20
MAX_SECTOR_WEIGHT: float = 0.35
MIN_LIQUIDITY_THRESHOLD: int = 100_000

MC_N_PATHS: int = 10_000
VAR_CONFIDENCE: float = 0.95

KELLY_REGIME_FACTORS = {
    "bull": 1.0, "ranging": 0.5, "bear": 0.25, "high_vol": 0.0,
}

# ── Efficacy Monitor ───────────────────────────────────────────────────────────
IC_DEGRADED_THRESHOLD: float = 0.02
IC_BLOCKED_THRESHOLD: float = 0.00
IC_DEGRADED_DAYS: int = 5
IC_RECOVERY_THRESHOLD: float = 0.05
IC_RECOVERY_DAYS: int = 3
IC_ROLLING_WINDOW: int = 20

# ── Walk-Forward ───────────────────────────────────────────────────────────────
WF_TRAIN_DAYS: int = 252
WF_TEST_DAYS: int = 63
WF_STEP_DAYS: int = 21
WF_EMBARGO_DAYS: int = 21
