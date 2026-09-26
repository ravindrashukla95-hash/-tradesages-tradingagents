"""Recent-window, single-symbol research replay for the long Breakout setup.

This is a trade-level diagnostic, not a portfolio backtest. EPs need archived,
timestamped catalysts and are intentionally excluded from this price-only run.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

from tradingagents.dataflows.errors import VendorError
from tradingagents.dataflows.vendors.yahoo.us_swing import YFinanceProvider
from tradingagents.us_swing.qullamaggie import (
    Bar,
    OpeningBar,
    TradePlan,
    breakout_candidate,
    opening_range_plan,
)


@dataclass(frozen=True)
class Outcome:
    entry_date: date
    exit_date: date | None
    entry: float
    exit_reason: str
    shares: int
    realized_pnl: float
    r_multiple: float | None


def replay(plan: TradePlan, daily: list[Bar], intraday: dict[date, list[OpeningBar]]) -> Outcome:
    """Partial at fourth close; then break-even stop and 10-day close trail.

    A close below the 10-day simple average exits at the *next* open. Gaps
    through stops fill at the open. Open positions are reported but not scored.
    No spread, fees, slippage, or portfolio allocation is modeled.
    """
    day_idx = next(i for i, bar in enumerate(daily) if bar.day == plan.session)
    rest = plan.shares
    realized = 0.0
    stop = plan.stop
    pending_trail = False
    for i in range(day_idx, len(daily)):
        bar = daily[i]
        if i == day_idx:
            # The entry bar was checked by opening_range_plan; only bars after
            # 09:35 can trigger the entry-day stop.
            session_bars = intraday.get(bar.day, [])
            if len(session_bars) < 3:
                raise ValueError("entry session needs bars after the entry candle")
            hit = any(b.low <= stop for b in session_bars[2:])
            fill = stop
        else:
            if pending_trail:
                realized += rest * (bar.open - plan.entry)
                return _closed(plan, bar.day, "10-day close trail", realized)
            hit = bar.low <= stop
            fill = min(bar.open, stop) if hit else stop
        if hit:
            realized += rest * (fill - plan.entry)
            return _closed(plan, bar.day, "stop", realized)
        if i - day_idx == 3:
            if rest > 1:
                trimmed = rest // 2
                realized += trimmed * (bar.close - plan.entry)
                rest -= trimmed
            stop = max(stop, plan.entry)
        if i >= 9 and i - day_idx >= 3:
            sma10 = mean(day.close for day in daily[i - 9 : i + 1])
            pending_trail = bar.close < sma10
    return Outcome(
        plan.session, None, plan.entry, "open at window end", plan.shares, realized, None
    )


def _closed(plan: TradePlan, day: date, reason: str, pnl: float) -> Outcome:
    return Outcome(plan.session, day, plan.entry, reason, plan.shares, pnl, pnl / plan.risk_dollars)


def evaluate_symbol(
    symbol: str,
    daily: list[Bar],
    intraday: dict[date, list[OpeningBar]],
    start: date,
    end: date,
    equity: float,
) -> dict:
    """No overlapping positions in the same symbol; signals after exit only."""
    outcomes: list[Outcome] = []
    candidates = 0
    plans = 0
    occupied_until: date | None = None
    for bar in daily:
        if not start <= bar.day <= end or (occupied_until and bar.day <= occupied_until):
            continue
        history = [prior for prior in daily if prior.day < bar.day]
        candidate = breakout_candidate(symbol, history, bar.day)
        if candidate is None:
            continue
        candidates += 1
        session_bars = intraday.get(bar.day, [])
        if (
            len(session_bars) < 3
            or (session_bars[0].time.hour, session_bars[0].time.minute) != (9, 30)
            or (session_bars[1].time.hour, session_bars[1].time.minute) != (9, 35)
        ):
            continue
        plan = opening_range_plan(candidate, history, session_bars[0], session_bars[1], equity)
        if plan is None:
            continue
        plans += 1
        result = replay(plan, daily, intraday)
        outcomes.append(result)
        occupied_until = result.exit_date or end
    closed = [outcome for outcome in outcomes if outcome.r_multiple is not None]
    return {
        "symbol": symbol,
        "start": str(start),
        "end": str(end),
        "candidate_days": candidates,
        "entry_plans": plans,
        "closed_trades": len(closed),
        "open_trades": len(outcomes) - len(closed),
        "win_rate": sum(o.realized_pnl > 0 for o in closed) / len(closed) if closed else None,
        "mean_r": mean(o.r_multiple for o in closed) if closed else None,
        "total_realized_pnl": sum(o.realized_pnl for o in closed),
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", required=True, help="Comma-separated, fixed research universe")
    parser.add_argument("--equity", type=float, default=20_000)
    parser.add_argument("--days", type=int, default=59, help="Calendar days, at most 59")
    args = parser.parse_args()
    if not 1 <= args.days <= 59 or args.equity <= 0:
        parser.error("days must be 1..59 and equity positive")
    symbols = list(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    if not symbols:
        parser.error("at least one symbol is required")
    now = datetime.now(ZoneInfo("America/New_York"))
    end = now.date() if now.hour >= 16 else now.date() - timedelta(days=1)
    start = max(end - timedelta(days=args.days), now.date() - timedelta(days=59))
    provider = YFinanceProvider()
    reports = []
    for symbol in symbols:
        try:
            daily, intraday = provider.load_window(symbol, start, end)
            reports.append(evaluate_symbol(symbol, daily, intraday, start, end, args.equity))
        except (VendorError, ValueError) as exc:
            reports.append({"symbol": symbol, "error": str(exc)})
    print(
        json.dumps(
            {
                "provider": "yfinance",
                "research_window": [str(start), str(end)],
                "setup": "BREAKOUT",
                "costs_modeled": False,
                "reports": reports,
            },
            default=str,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
