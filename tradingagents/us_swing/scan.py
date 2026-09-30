"""US swing scanner using yfinance for testing or supplied point-in-time CSV."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingagents.dataflows.errors import VendorError
from tradingagents.dataflows.vendors.yahoo.us_swing import YFinanceProvider
from tradingagents.us_swing.qullamaggie import (
    Bar,
    OpeningBar,
    breakout_candidate,
    episodic_pivot_candidate,
    opening_range_plan,
)


def load_daily(path: Path, symbol: str, session: date) -> list[Bar]:
    with path.open(newline="") as stream:
        rows = csv.DictReader(stream)
        return [
            Bar(
                date.fromisoformat(row["date"]),
                *(float(row[key]) for key in ("open", "high", "low", "close", "volume")),
            )
            for row in rows
            if row["symbol"] == symbol and date.fromisoformat(row["date"]) < session
        ]


def load_opening(path: Path, symbol: str, session: date) -> list[OpeningBar]:
    with path.open(newline="") as stream:
        rows = csv.DictReader(stream)
        bars = []
        for row in rows:
            if row["symbol"] != symbol:
                continue
            stamp = datetime.fromisoformat(row["timestamp"])
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("intraday timestamps must include a UTC offset")
            eastern = stamp.astimezone(ZoneInfo("America/New_York"))
            if eastern.date() == session and (eastern.hour, eastern.minute) in {(9, 30), (9, 35)}:
                bars.append(
                    OpeningBar(
                        stamp,
                        *(float(row[key]) for key in ("open", "high", "low", "close", "volume")),
                    )
                )
    return sorted(bars, key=lambda bar: bar.time)[:2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("yfinance", "csv"), default="yfinance")
    parser.add_argument("--daily", type=Path, help="Required with --provider csv")
    parser.add_argument("--intraday", type=Path, help="Required with --provider csv")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--session", required=True, type=date.fromisoformat)
    parser.add_argument("--equity", required=True, type=float)
    parser.add_argument("--catalyst", help="Known by the open; required to qualify an EP")
    args = parser.parse_args()
    if args.provider == "csv":
        if args.daily is None or args.intraday is None:
            parser.error("--provider csv requires --daily and --intraday")
        history = load_daily(args.daily, args.symbol, args.session)
        opening = load_opening(args.intraday, args.symbol, args.session)
    else:
        if args.daily is not None or args.intraday is not None:
            parser.error("--daily and --intraday require --provider csv")
        try:
            history, opening = YFinanceProvider().load(args.symbol, args.session)
        except (ValueError, VendorError) as exc:
            parser.error(str(exc))
    if len(opening) != 2:
        parser.error("the first two regular-session 5-minute bars are required")
    candidates = [breakout_candidate(args.symbol, history, args.session)]
    candidates.append(
        episodic_pivot_candidate(args.symbol, history, args.session, opening[0], args.catalyst)
    )
    result = []
    for candidate in filter(None, candidates):
        plan = opening_range_plan(candidate, history, opening[0], opening[1], args.equity)
        result.append({"candidate": asdict(candidate), "plan": asdict(plan) if plan else None})
    print(json.dumps({"provider": args.provider, "setups": result}, default=str, indent=2))


if __name__ == "__main__":
    main()
