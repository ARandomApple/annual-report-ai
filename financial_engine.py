"""
financial_engine.py — Compute financial metrics and detect signals.

Design principle: Python handles numbers, the LLM handles interpretation.
This module will extract line items from structured financial data and
compute derived metrics without calling any AI.

Phase 1: Placeholder — will be implemented in a later phase.
"""


def compute_metrics(financial_data: dict) -> dict:
    """
    Compute financial metrics from extracted line items.

    This is a placeholder for Phase 1. In future phases this function will:
      - Accept structured financial data extracted from the PDF.
      - Calculate growth rates, margins, returns, and leverage ratios.
      - Return a dict of computed metrics.

    Args:
        financial_data: Dict of financial line items keyed by name.

    Returns:
        Dict of computed metrics.
    """
    # Placeholder — to be implemented in Phase 2+
    return {
        "status": "not_implemented",
        "message": "Financial metrics engine will be implemented in a future phase.",
    }


def detect_signals(financial_data: dict, metrics: dict) -> list[dict]:
    """
    Detect anomaly signals from financial data and metrics.

    This is a placeholder for Phase 1. In future phases this function will:
      - Compare related line items for warning patterns.
      - Detect signals like: revenue vs inventory divergence,
        profit vs cash flow divergence, margin pressure, etc.
      - Return a list of signals with severity and description.

    Args:
        financial_data: Dict of financial line items keyed by name.
        metrics: Dict of computed metrics from compute_metrics().

    Returns:
        List of signal dicts, each with 'name', 'severity', 'description'.
    """
    # Placeholder — to be implemented in Phase 2+
    return [
        {
            "status": "not_implemented",
            "message": "Signal detection engine will be implemented in a future phase.",
        }
    ]
