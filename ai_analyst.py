"""
ai_analyst.py — Interpret financial data using DeepSeek (OpenAI-compatible API).

Design principle: Python handles numbers, the LLM handles interpretation.
This module sends PRE-COMPUTED metrics and signals to the LLM for
natural-language economic interpretation only.

Phase 1: Placeholder — will be implemented in a later phase.
"""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def get_client():
    """
    Get an OpenAI-compatible client configured for DeepSeek.

    Reads DEEPSEEK_API_KEY and DEEPSEEK_BASE_URL from environment/.env.

    Returns:
        An openai.OpenAI client, or None if the API key is not configured.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    if not api_key:
        return None

    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url)


def generate_interpretation(
    metrics: dict,
    signals: list[dict],
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Generate an economic interpretation of financial data via DeepSeek.

    This is a placeholder for Phase 1. In future phases this function will:
      - Accept pre-computed metrics and detected signals.
      - Send them to DeepSeek with a structured prompt asking for
        economic interpretation, NOT calculations.
      - Return the LLM's natural-language analysis.

    Args:
        metrics: Dict of computed financial metrics.
        signals: List of detected anomaly signals.
        model: DeepSeek model name (defaults to DEEPSEEK_MODEL env var
               or 'deepseek-chat').

    Returns:
        Natural-language interpretation string, or None if unavailable.
    """
    client = get_client()
    if client is None:
        return None

    model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # Placeholder — to be implemented in Phase 2+
    # Will call client.chat.completions.create(...)

    return (
        "AI interpretation will be implemented in a future phase. "
        "The DeepSeek API client is configured and ready."
    )
