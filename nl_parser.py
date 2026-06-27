"""QUANTIS — NL Investment Goal Parser using Gemini API.

Converts free-text investment goals → structured InvestmentGoal dataclass.
Uses Gemini 1.5 Flash (free tier) with JSON mode for deterministic extraction.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from quantis.api.schemas import InvestmentGoal, RiskTolerance
from quantis.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)

_SYSTEM_PROMPT = """You are a financial goal extraction engine for Indian retail investors.
Extract investment parameters from the user's natural language input and return ONLY valid JSON.
All monetary amounts should be converted to INR (₹1 lakh = 100000 INR).
Return target should be a fraction (0.15 for 15%). Max drawdown should be a fraction (0.10 for 10%).
Risk tolerance must be one of: conservative, moderate, aggressive.
Horizon should be in trading days (1 year ≈ 252 days).
If a field is not mentioned, use sensible defaults:
  return_target: 0.12, max_drawdown: 0.15, sectors_excluded: [], capital_inr: 500000,
  horizon_days: 252, risk_tolerance: "moderate".
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


def _call_gemini(prompt: str, max_retries: int = 3) -> dict[str, Any]:
    """Call Gemini API with exponential backoff. Returns parsed JSON dict."""
    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
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
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    _GEMINI_URL,
                    params={"key": api_key},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
        except (httpx.HTTPStatusError, httpx.TimeoutException, KeyError, json.JSONDecodeError) as exc:
            wait = 2 ** attempt
            logger.warning("Gemini attempt %d/%d failed: %s — retrying in %ds", attempt + 1, max_retries, exc, wait)
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                raise


def parse_investment_goal(nl_text: str) -> InvestmentGoal:
    """Parse a natural-language investment goal into a structured InvestmentGoal.

    Falls back to conservative defaults on total API failure.
    """
    try:
        raw = _call_gemini(nl_text)
        goal = InvestmentGoal(
            return_target=float(raw.get("return_target", 0.12)),
            max_drawdown=float(raw.get("max_drawdown", 0.15)),
            sectors_excluded=[s.strip().title() for s in raw.get("sectors_excluded", [])],
            capital_inr=float(raw.get("capital_inr", 500_000)),
            horizon_days=int(raw.get("horizon_days", 252)),
            risk_tolerance=RiskTolerance(raw.get("risk_tolerance", "moderate")),
        )
        logger.info("Parsed goal: %s", goal.model_dump())
        return goal

    except Exception as exc:
        logger.error("NL parser total failure (%s) — using conservative defaults", exc)
        return _DEFAULT_GOAL
