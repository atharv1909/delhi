# InvestEasy 🚀
**Regime-Aware Quant Intelligence Platform for Indian Retail Investors (NSE / BSE)**

![InvestEasy Banner](https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=1200&q=80)

---

## 🌟 Overview

**InvestEasy** bridges institutional-grade quantitative finance and Indian retail investors. Instead of static robo-advisors or raw chart tools, InvestEasy accepts **Natural Language investment goals** (or voice input!), ingests live NSE/BSE market data, generates multi-model alpha predictions, detects macro market regimes in real time, and delivers **SEBI-compliant rebalancing trade commands**.

---

## ⚡ Key Features

### 1. 🧠 Dual-Model Natural Language Goal Parsing
- Parse natural language investment goals (e.g. *"I want 15% annual returns with max 10% drawdown over 1 year. Avoid pharma."*) using **Google Gemini 1.5 Pro**, with automatic fallback to **Groq Llama-3-70B**.
- Extracts return targets, risk tolerance, horizon, capital allocation, and excluded sectors automatically.

### 2. 🎙️ Voice-to-Text Integration
- Integrated **Smallest AI Pulse WebSocket API** and browser SpeechRecognition for seamless voice-based goal setting.

### 3. 🔬 Multi-Model Alpha Ensembling (Mixture of Experts)
- **LightGBM Tree Ensemble**: Captures non-linear tabular momentum and volatility interactions.
- **KAN (Kolmogorov-Arnold Networks)**: Spline-based neural function approximation for smooth alpha mapping.
- **Mamba State Space Model**: Long-horizon sequential feature extraction.
- **PatchTST**: Transformer-based time-series forecasting.
- **Imitation Learning RL**: Actor-critic policy network trained on expert trading trajectories.
- **Soft MoE Gating**: Dynamically combines model outputs based on regime confidence and model IC efficacy.

### 4. 🛡️ Real-Time HMM Regime Detection & Gating
- 4-State Gaussian Hidden Markov Model (**Bull Expansion**, **Bear Contraction**, **High Volatility**, **Ranging Consolidation**).
- Dynamically scales portfolio leverage via **Kelly Sizing Caps** (e.g., 100% in Bull, 25% in Bear, 0% equity expansion in High Vol).

### 5. ⚖️ Mean-CVaR Optimization & Monte Carlo Simulation
- Optimizes portfolio weights to minimize Expected Shortfall (CVaR at 95%) while achieving target returns.
- Runs **10,000 empirical regime-switched Monte Carlo paths** to forecast P95, P50 (expected), and P05 tail risk.

### 6. 📋 SEBI-Compliant Trade Commands
- Translates fractional optimal weights into integer share quantities rounded to exact exchange lot sizes.
- Generates clear, executable BUY/SELL instructions ready for Demat / Broker API gateway execution.

---

## 🏗️ Architecture & Package Structure

```text
InvestEasy/
├── quantis/                   # Core Python Package
│   ├── api/                   # FastAPI Endpoints & Routers
│   │   ├── main.py            # Entry point & CORS configuration
│   │   ├── router.py          # Portfolio Analysis & Simulation routes
│   │   └── live_router.py     # Live Market OHLCV Scanner routes
│   ├── ingestion/             # Data & NLP Ingestion
│   │   ├── nl_parser.py       # Gemini & Groq LLM parsing engine
│   │   └── market_data.py     # Live Yahoo Finance / NSE fetcher
│   ├── models/                # Alpha Prediction Models
│   │   ├── lgbm_alpha.py      # LightGBM Alpha predictor + SHAP
│   │   ├── kan_alpha.py       # Kolmogorov-Arnold Network
│   │   ├── mamba_encoder.py   # Mamba State Space representation
│   │   ├── patchtst_alpha.py  # PatchTST Transformer
│   │   └── imitation_learner.py # RL policy weights
│   ├── ensemble/              # Ensemble & Regime Gating
│   │   ├── regime_detector.py # 4-State Gaussian HMM
│   │   └── gating_network.py  # Soft Mixture-of-Experts Gate
│   ├── portfolio/             # Risk & Optimization
│   │   ├── optimizer.py       # Mean-CVaR quadratic programming
│   │   ├── risk_engine.py     # 10,000 path Monte Carlo engine
│   │   └── backtester.py      # Purged walk-forward CV backtester
│   └── config.py              # Unified System Configuration
├── frontend/                  # React 18 + Vite + TypeScript UI
│   ├── src/
│   │   ├── components/        # Dashboard KPIs, SHAP waterfalls, Charts
│   │   ├── pages/             # InputPage, ResultsPage, LivePage
│   │   └── store/             # Zustand global state store
├── saved_models/              # Pre-trained model weights (.pkl, .pt)
├── requirements.txt           # Backend Python dependencies
└── README.md                  # Project Documentation
```

---

## 🚀 Quickstart Guide (Local Setup)

Follow these steps to run InvestEasy locally on your machine.

### Prerequisites
- **Python 3.10+** (Anaconda recommended)
- **Node.js 18+** & `npm`

### 1. Backend Setup

1. Open a terminal in the root directory (`D:\InvestEasy`).
2. Install Python dependencies:
   ```powershell
   python -m pip install -r requirements.txt
   ```
3. Verify API keys in your `.env` file:
   ```env
   GEMINI_API_KEY=your_gemini_key
   GROQ_API_KEY=your_groq_key
   SMALLEST_API_KEY=your_smallest_ai_key
   ```
4. Start the FastAPI backend server:
   ```powershell
   python -m uvicorn quantis.api.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   *The API docs will be available at `http://localhost:8000/docs`.*

### 2. Frontend Setup

1. Open a second terminal inside the frontend directory:
   ```powershell
   cd D:\InvestEasy\frontend
   ```
2. Install Node modules:
   ```powershell
   npm install
   ```
3. Start the Vite React development server:
   ```powershell
   npm run dev
   ```
4. Open your browser and navigate to `http://localhost:5173`.

---

## 💡 Usage Walkthrough

1. **Analyze Portfolio**:
   - Type or speak your goal (e.g., *"15% return target, max 10% drawdown, 1 year horizon, avoid energy sector"*).
   - Add your existing holdings and uninvested cash.
   - Click **Run InvestEasy Analysis**. Watch the real-time background pipeline step through NLP parsing, market data extraction, alpha generation, regime detection, and CVaR optimization.

2. **Explore Results**:
   - Inspect **Regime Gating** status and Kelly sizing caps.
   - Check **SHAP Waterfalls** to see what feature attributions drove each asset's alpha forecast.
   - Analyze the **10,000 Path Monte Carlo chart** comparing Expected vs. CVaR Tail Risk outcomes.
   - Review **Walk-Forward Backtest** metrics (Sharpe, Calmar, Information Coefficient).
   - Execute **SEBI-Compliant Trade Commands** with exact integer share quantities.

3. **Live Market Mode**:
   - Switch to the **◉ Live** tab.
   - Click **Run Live Analysis** to fetch live orderbook snapshots from NSE and run real-time inference across top NIFTY constituents.

---

## 🔒 License & Compliance
InvestEasy is built for demonstration and quantitative analysis. Trade recommendations conform to standard NSE lot sizes and risk limits. Always verify execution orders through licensed brokerage gateways.
