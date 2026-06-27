<div align="center">

<img src="./assets/hero-banner.svg" width="100%" alt="TradeEasy" />

<br/>

<a href="#overview"><strong>Overview</strong></a> ·
<a href="#core-capabilities"><strong>Core Capabilities</strong></a> ·
<a href="#how-it-works"><strong>How It Works</strong></a> ·
<a href="#key-differentiators"><strong>Key Differentiators</strong></a> ·
<a href="#built-for-indian-markets"><strong>Built for Indian Markets</strong></a> ·
<a href="#disclaimer"><strong>Disclaimer</strong></a>

</div>

<br/>

## Overview

TradeEasy is a quant intelligence platform that converts natural-language investment goals into fully reasoned, continuously monitored portfolios for Indian retail investors.

- Accepts plain-English investment goals as input (capital, horizon, risk tolerance, sector exclusions)
- Ingests live market data and applies multiple independent forecasting approaches per stock
- Detects current market conditions and adjusts strategy accordingly
- Constructs portfolios using formal risk-return optimization, not heuristic stock-picking
- Continuously monitors its own forecasting accuracy and restricts trading when reliability drops
- Surfaces the reasoning behind every recommendation, not just the output

<br/>

## Core Capabilities

| Capability | Description |
|---|---|
| Natural-language intake | Parses free-text goals into structured constraints (capital, drawdown tolerance, excluded sectors, horizon) |
| Multi-model forecasting | Evaluates each stock through several independent, structurally different forecasting approaches |
| Market regime detection | Classifies current market conditions (trending, ranging, high-volatility) before trusting any forecast |
| Adaptive signal weighting | Reweights trust in each forecasting approach based on which has performed best in the current regime |
| Self-monitoring accuracy gate | Tracks whether recent predictions matched outcomes; automatically scales back or pauses trading on drift |
| Portfolio optimization | Solves for risk-adjusted allocation across holdings, accounting for tail risk, not just average-case outcomes |
| Historical stress-testing | Validates proposed portfolios against real past periods of market turbulence |
| Scenario / shock simulation | Models how an external shock propagates through related holdings before it happens live |
| Full explainability | Attributes each recommendation to the specific signals that drove it |

<br/>

<div align="center">
<img src="./assets/pipeline-diagram.svg" width="100%" alt="How a request moves through TradeEasy" />
</div>

<br/>

## How It Works

**1. Input parsing**
- User goal is converted into structured constraints: capital, target return, max drawdown, excluded sectors, time horizon, risk tolerance

**2. Market regime detection**
- Current market state is classified before any forecast is trusted
- Position sizing and signal trust are adjusted based on the detected regime

**3. Multi-model forecasting**
- Each stock is independently scored by several forecasting approaches with different structural strengths (pattern/momentum detection, multi-signal nonlinear relationships, long-horizon sequence modeling)
- Model outputs are combined dynamically — weighting shifts toward whichever approach has been most reliable in the current regime, rather than a fixed average

**4. Self-monitoring**
- Recent predictions are checked against realized outcomes on a rolling basis
- If predictive accuracy degrades, the system automatically reduces position sizing
- If accuracy degrades severely, new trades are paused until reliability is restored

<div align="center">
<img src="./assets/confidence-gate.svg" width="100%" alt="TradeEasy monitoring its own predictive accuracy and pausing when it drifts" />
</div>

**5. Portfolio construction**
- Final allocation is solved as a constrained optimization problem (expected return vs. tail risk), not a top-N stock list
- Constraints include max single-position size, sector caps, and user-specified exclusions

**6. Validation**
- Proposed portfolio is back-tested across multiple historical periods, including past stress events
- User-triggered shock scenarios show projected impact on the specific portfolio before any capital is at risk

<br/>

## Key Differentiators

- **Self-monitoring accuracy gate** — tracks its own predictive reliability in real time and restricts trading automatically on drift, rather than only reporting predictions
- **Genuine multi-model disagreement** — combines structurally different forecasting approaches with dynamic, regime-conditioned weighting, not a static average
- **Full attribution on every output** — each recommendation is traceable to the specific signals that produced it
- **Tail-risk-aware portfolio construction** — optimizes for worst-realistic-case outcomes, not just average-case return

<br/>

## Built for Indian Markets

- NSE/BSE-native data handling, including circuit-breaker behavior and settlement timing
- Standard lot-size constraints applied in position sizing
- Institutional flow data (FII/DII) incorporated as a market signal
- Nifty 50 used as the standing benchmark for all performance comparisons

<br/>

---

## Disclaimer

<div align="center">
<sub>TradeEasy is a research and education-oriented project. It does not constitute investment advice. All figures shown in this document are illustrative.</sub>
</div>
