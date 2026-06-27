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


def _call_gemini(prompt: str, max_retries: int = 3) -> dict[str, Any]:
    """Call Gemini API with exponential backoff. Returns parsed JSON dict."""
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


def _call_groq(prompt: str, max_retries: int = 3) -> dict[str, Any]:
    """Call Groq API as fallback. Uses llama-3.3-70b-versatile with JSON mode."""
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
            with httpx.Client(timeout=30.0) as client:
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
        except (httpx.HTTPStatusError, httpx.TimeoutException, KeyError, json.JSONDecodeError) as exc:
            wait = 2 ** attempt
            logger.warning("Groq attempt %d/%d failed: %s — retrying in %ds", attempt + 1, max_retries, exc, wait)
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
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


def parse_investment_goal(nl_text: str) -> InvestmentGoal:
    """Parse a natural-language investment goal into a structured InvestmentGoal.

    Tries Groq first (primary), falls back to Gemini, then to conservative defaults.
    """
    # Try Groq first (primary)
    try:
        raw = _call_groq(nl_text)
        goal = _parse_raw_to_goal(raw)
        logger.info("Parsed goal via Groq: %s", goal.model_dump())
        return goal
    except Exception as exc:
        logger.warning("Groq parser failed (%s) — trying Gemini fallback", exc)

    # Try Gemini as fallback
    try:
        raw = _call_gemini(nl_text)
        goal = _parse_raw_to_goal(raw)
        logger.info("Parsed goal via Gemini: %s", goal.model_dump())
        return goal
    except Exception as exc:
        logger.warning("Gemini parser also failed (%s) — using conservative defaults", exc)

    # Final fallback: conservative defaults
    logger.error("All NL parsers failed — using conservative defaults")
    return _DEFAULT_GOAL

