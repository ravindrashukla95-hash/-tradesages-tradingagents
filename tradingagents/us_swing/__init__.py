"""Deterministic US equity swing setup research, independent of LLM decisions."""

from .qullamaggie import (  # noqa: F401
    Bar,
    Candidate,
    OpeningBar,
    SetupConfig,
    TradePlan,
    breakout_candidate,
    episodic_pivot_candidate,
    opening_range_plan,
)
