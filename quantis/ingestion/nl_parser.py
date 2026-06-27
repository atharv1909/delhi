"""InvestEasy — NL Investment Goal Parser.

Converts free-text investment goals → structured InvestmentGoal dataclass.
Uses Groq API as primary, Gemini API as fallback. Both use JSON mode.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from quantis.api.schemas import InvestmentGoal, RiskTolerance
from quantis.config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_SYSTEM_PROMPT = """You are a financial goal extraction engine for Indian retail investors.
Extract investment parameters from the user's natural language input and return ONLY valid JSON.
All monetary amounts should be converted to INR (₹1 lakh = 100000 INR).
Return target should be a fraction (0.15 for 15%). Max drawdown should be a fraction (0.10 for 10%).
Risk tolerance must be one of: conservative, moderate, aggressive.
Horizon should be in trading days (1 year ≈ 252 days).
If a field is not mentioned, use sensible defaults:
  return_target: 0.12, max_drawdown: 0.15, sectors_excluded: [], capital_inr: 500000,
  horizon_days: 252, risk_tolerance: "moderate".

Return JSON with these exact keys:
{
  "return_target": <number 0-2>,
  "max_drawdown": <number 0-1>,
  "sectors_excluded": [<string>],
  "capital_inr": <number>,
  "horizon_days": <integer>,
  "risk_tolerance": "<conservative|moderate|aggressive>"
}
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "return_target": {"type": "number", "minimum": 0, "maximum": 2},
        "max_drawdown": {"type": "number", "minimum": 0, "maximum": 1},
        "sectors_excluded": {"type": "array", "items": {"type": "string"}},
        "capital_inr": {"type": "number", "minimum": 1000},
        "horizon_days": {"type": "integer", "minimum": 1, "maximum": 3650},
        "risk_tolerance": {"type": "string", "enum": ["conservative", "moderate", "aggressive"]},
    },
    "required": ["return_target", "max_drawdown", "sectors_excluded", "capital_inr", "horizon_days", "risk_tolerance"],
}

_DEFAULT_GOAL = InvestmentGoal(
    return_target=0.12,
    max_drawdown=0.15,
    sectors_excluded=[],
    capital_inr=500_000,
    horizon_days=252,
    risk_tolerance=RiskTolerance.moderate,
)


def _call_gemini(prompt: str, max_retries: int = 1) -> dict[str, Any]:
    """Call Gemini API with short timeout. Returns parsed JSON dict."""
    api_key = os.environ.get("GEMINI_API_KEY", "") or GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "responseSchema": _SCHEMA,
        },
        "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
    }

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.post(
                    _GEMINI_URL,
                    params={"key": api_key},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
        except Exception as exc:
            if attempt == max_retries - 1:
                raise


def _call_groq(prompt: str, max_retries: int = 1) -> dict[str, Any]:
    """Call Groq API with short timeout. Uses llama-3.3-70b-versatile with JSON mode."""
    api_key = os.environ.get("GROQ_API_KEY", "") or GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "max_tokens": 1024,
    }

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.post(
                    _GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return json.loads(text)
        except Exception as exc:
            if attempt == max_retries - 1:
                raise


def _parse_raw_to_goal(raw: dict[str, Any]) -> InvestmentGoal:
    """Convert raw JSON dict to InvestmentGoal with validation."""
    return InvestmentGoal(
        return_target=float(raw.get("return_target", 0.12)),
        max_drawdown=float(raw.get("max_drawdown", 0.15)),
        sectors_excluded=[s.strip().title() for s in raw.get("sectors_excluded", [])],
        capital_inr=float(raw.get("capital_inr", 500_000)),
        horizon_days=int(raw.get("horizon_days", 252)),
        risk_tolerance=RiskTolerance(raw.get("risk_tolerance", "moderate")),
    )


def _rule_based_parse(nl_text: str) -> InvestmentGoal:
    import re
    text = nl_text.lower()
    
    ret_target = 0.12
    max_dd = 0.15
    capital = 500_000.0
    horizon = 252
    risk = RiskTolerance.moderate
    excluded = []
    
    ret_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:return|cagr|profit|growth)?', text)
    if ret_match:
        val = float(ret_match.group(1))
        if val > 2.0:
            val /= 100.0
        if 0.01 <= val <= 2.0:
            ret_target = val
            
    if any(k in text for k in ['aggressive', 'high risk', 'risky', 'growth', 'max']):
        risk = RiskTolerance.aggressive
        max_dd = 0.25
    elif any(k in text for k in ['conservative', 'low risk', 'safe', 'capital protection']):
        risk = RiskTolerance.conservative
        max_dd = 0.08
    elif 'moderate' in text:
        risk = RiskTolerance.moderate
        
    cap_match = re.search(r'(\d+(?:\.\d+)?)\s*(lakh|lac|l|cr|crore|k|thousand)?', text)
    if cap_match and 'cagr' not in cap_match.group(0) and '%' not in cap_match.group(0):
        num = float(cap_match.group(1))
        unit = cap_match.group(2)
        if unit in ['lakh', 'lac', 'l']:
            capital = num * 100_000
        elif unit in ['cr', 'crore']:
            capital = num * 10_000_000
        elif unit in ['k', 'thousand']:
            capital = num * 1,000
        elif num >= 1000:
            capital = num
            
    hor_match = re.search(r'(\d+)\s*(year|yr|month|mo|day)', text)
    if hor_match:
        num = int(hor_match.group(1))
        unit = hor_match.group(2)
        if unit.startswith('y'):
            horizon = num * 252
        elif unit.startswith('m'):
            horizon = int(num * 21)
        elif unit.startswith('d'):
            horizon = num
            
    sectors = ['banking', 'it', 'energy', 'fmcg', 'pharma', 'auto', 'nbfc', 'metals', 'infra']
    for s in sectors:
        if f"no {s}" in text or f"exclude {s}" in text or f"avoid {s}" in text or f"without {s}" in text:
            excluded.append(s.title())
            
    return InvestmentGoal(
        return_target=ret_target,
        max_drawdown=max_dd,
        sectors_excluded=excluded,
        capital_inr=capital,
        horizon_days=horizon,
        risk_tolerance=risk,
    )


def parse_investment_goal(nl_text: str) -> InvestmentGoal:
    """Parse a natural-language investment goal into a structured InvestmentGoal.

    Tries Groq first (primary), falls back to Gemini, then to instant rule-based parsing.
    """
    if not nl_text or not nl_text.strip():
        return _DEFAULT_GOAL

    try:
        raw = _call_groq(nl_text)
        goal = _parse_raw_to_goal(raw)
        logger.info("Parsed goal via Groq: %s", goal.model_dump())
        return goal
    except Exception as exc:
        logger.warning("Groq parser failed (%s) — trying Gemini fallback", exc)

    try:
        raw = _call_gemini(nl_text)
        goal = _parse_raw_to_goal(raw)
        logger.info("Parsed goal via Gemini: %s", goal.model_dump())
        return goal
    except Exception as exc:
        logger.warning("Gemini parser also failed (%s) — using rule-based parser", exc)

    goal = _rule_based_parse(nl_text)
    logger.info("Parsed goal via Rule-Based extractor: %s", goal.model_dump())
    return goal


