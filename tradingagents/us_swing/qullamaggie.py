"""A testable interpretation of Qullamaggie's long Breakout and EP setups.

The published setups involve visual judgment. Numeric thresholds beyond the
author's explicit gap, prior move, and timing rules are research hypotheses,
not claims that these are his exact system or that they are profitable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import floor, isfinite
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OpeningBar:
    time: datetime  # timezone-aware America/New_York timestamp, start of bar
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class SetupConfig:
    min_price: float = 5.0
    min_dollar_volume: float = 5_000_000.0
    breakout_prior_gain: float = 0.30
    breakout_base_days: int = 15
    breakout_max_base_depth: float = 0.30
    breakout_near_high: float = 0.05
    ep_min_gap: float = 0.10
    ep_min_opening_volume_ratio: float = 0.10
    max_stop_adr_multiple: float = 1.0
    risk_fraction: float = 0.005
    max_position_fraction: float = 0.20


DEFAULT_CONFIG = SetupConfig()


@dataclass(frozen=True)
class Candidate:
    symbol: str
    setup: str
    session: date
    reference_high: float | None
    reason: str


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    setup: str
    session: date
    entry: float
    stop: float
    shares: int
    risk_dollars: float


def _valid_bar(bar: Bar | OpeningBar) -> bool:
    prices = (bar.open, bar.high, bar.low, bar.close)
    return (
        all(isfinite(p) and p > 0 for p in prices)
        and bar.low <= min(bar.open, bar.close) <= bar.high
        and bar.low <= max(bar.open, bar.close) <= bar.high
        and isfinite(bar.volume)
        and bar.volume >= 0
    )


def _history(history: list[Bar], session: date) -> None:
    if any(not _valid_bar(bar) for bar in history):
        raise ValueError("invalid OHLCV history")
    days = [bar.day for bar in history]
    if days != sorted(set(days)) or any(day >= session for day in days):
        raise ValueError("history must be unique, sorted, and strictly before session")


def average_daily_range(history: list[Bar], days: int = 20) -> float:
    """Mean (high-low)/previous close, based only on completed sessions."""
    if len(history) < days + 1:
        raise ValueError("insufficient history for ADR")
    return (
        sum(
            (history[i].high - history[i].low) / history[i - 1].close
            for i in range(len(history) - days, len(history))
        )
        / days
    )


def _liquid(history: list[Bar], config: SetupConfig) -> bool:
    recent = history[-20:]
    return (
        len(recent) == 20
        and recent[-1].close >= config.min_price
        and sum(bar.close * bar.volume for bar in recent) / 20 >= config.min_dollar_volume
    )


def _opening_session(opening: OpeningBar, session: date) -> None:
    if opening.time.tzinfo is None or opening.time.utcoffset() is None:
        raise ValueError("opening bar timestamp must be timezone aware")
    eastern = opening.time.astimezone(NEW_YORK)
    if eastern.date() != session or (eastern.hour, eastern.minute) != (9, 30):
        raise ValueError("opening bar must start at 09:30 America/New_York on session")


def breakout_candidate(
    symbol: str, history: list[Bar], session: date, config: SetupConfig = DEFAULT_CONFIG
) -> Candidate | None:
    """Pre-open screen: prior surge, consolidation and proximity to base high.

    Uses a fixed-length base and an earlier 1-3 month comparison window.
    Tightening is approximated by a smaller mean daily range in the second
    half of the base. These are deliberately exposed parameters for research.
    """
    _history(history, session)
    base_days = config.breakout_base_days
    if base_days < 10 or len(history) < base_days + 63 or not _liquid(history, config):
        return None
    base = history[-base_days:]
    before = history[-base_days - 63 : -base_days]
    peak_before = max(bar.high for bar in before)
    low_before = min(bar.low for bar in before)
    base_high = max(bar.high for bar in base)
    base_low = min(bar.low for bar in base)
    ranges = [(bar.high - bar.low) / bar.close for bar in base]
    middle = len(ranges) // 2
    if not (
        peak_before / low_before - 1 >= config.breakout_prior_gain
        and base_low >= low_before
        and (base_high - base_low) / base_high <= config.breakout_max_base_depth
        and base[-1].close >= base_high * (1 - config.breakout_near_high)
        and sum(ranges[middle:]) / len(ranges[middle:])
        < sum(ranges[:middle]) / len(ranges[:middle])
    ):
        return None
    return Candidate(symbol, "BREAKOUT", session, base_high, "prior surge and tight base")


def episodic_pivot_candidate(
    symbol: str,
    history: list[Bar],
    session: date,
    opening: OpeningBar,
    catalyst: str | None,
    config: SetupConfig = DEFAULT_CONFIG,
) -> Candidate | None:
    """Intraday EP screen; catalyst must have been known by the opening bar."""
    _history(history, session)
    if not _liquid(history, config) or not catalyst:
        return None
    _opening_session(opening, session)
    if not _valid_bar(opening):
        raise ValueError("invalid opening OHLCV")
    avg_volume = sum(bar.volume for bar in history[-20:]) / 20
    if (
        opening.open / history[-1].close - 1 < config.ep_min_gap
        or avg_volume <= 0
        or opening.volume / avg_volume < config.ep_min_opening_volume_ratio
    ):
        return None
    return Candidate(symbol, "EP", session, None, catalyst)


def opening_range_plan(
    candidate: Candidate,
    history: list[Bar],
    opening: OpeningBar,
    next_bar: OpeningBar,
    equity: float,
    config: SetupConfig = DEFAULT_CONFIG,
) -> TradePlan | None:
    """Buy a break of the first 5-minute high during the following 5-minute bar.

    The opening low is the initial stop. A bar that crosses both entry and stop
    is conservatively discarded since OHLC alone cannot establish event order.
    Orders that gap beyond the allowable stop distance are likewise discarded.
    This function creates a plan; it never sends an order.
    """
    _history(history, candidate.session)
    _opening_session(opening, candidate.session)
    if next_bar.time.tzinfo is None or next_bar.time.utcoffset() is None:
        raise ValueError("intraday timestamps must be timezone aware")
    if next_bar.time.astimezone(NEW_YORK).date() != candidate.session:
        raise ValueError("intraday bars must be in candidate session")
    if (next_bar.time - opening.time).total_seconds() != 300:
        raise ValueError("expected consecutive 5-minute bars")
    if not _valid_bar(opening) or not _valid_bar(next_bar) or not isfinite(equity) or equity <= 0:
        raise ValueError("invalid intraday bars or equity")
    trigger = max(opening.high, candidate.reference_high or 0)
    if next_bar.high <= trigger or next_bar.low <= opening.low:
        return None
    entry = max(next_bar.open, trigger)
    stop = opening.low
    if (
        entry <= stop
        or (entry - stop) / entry > average_daily_range(history) * config.max_stop_adr_multiple
    ):
        return None
    shares = min(
        floor(equity * config.risk_fraction / (entry - stop)),
        floor(equity * config.max_position_fraction / entry),
    )
    if shares < 1:
        return None
    return TradePlan(
        candidate.symbol,
        candidate.setup,
        candidate.session,
        entry,
        stop,
        shares,
        shares * (entry - stop),
    )
