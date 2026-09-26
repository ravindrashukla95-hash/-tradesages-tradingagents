import json
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from tradingagents.us_swing.qullamaggie import (
    Bar,
    Candidate,
    OpeningBar,
    SetupConfig,
    breakout_candidate,
    episodic_pivot_candidate,
    opening_range_plan,
)
from tradingagents.us_swing.scan import main

SESSION = date(2026, 9, 25)
ET = timezone(timedelta(hours=-4))


def history() -> list[Bar]:
    # 64 earlier days include a genuine 40% move. A subsequent 15-day base
    # tightens and finishes at its high, entirely before the signal session.
    first = [
        Bar(date(2026, 6, 1) + timedelta(days=i), 100, 101, 99, 100, 100_000) for i in range(64)
    ]
    first[-1] = Bar(first[-1].day, 139, 140, 138, 139, 100_000)
    base = [
        Bar(date(2026, 8, 5) + timedelta(days=i), 138, 140, 136 if i < 7 else 138, 139, 100_000)
        for i in range(15)
    ]
    return first + base


def minute(n: int, o: float, h: float, low: float, close: float, volume=12_000) -> OpeningBar:
    return OpeningBar(
        datetime(2026, 9, 25, 9, 30, tzinfo=ET) + timedelta(minutes=5 * n),
        o,
        h,
        low,
        close,
        volume,
    )


def test_breakout_screen_uses_only_completed_history():
    bars = history()
    candidate = breakout_candidate("TEST", bars, SESSION)
    assert candidate is not None
    assert candidate.setup == "BREAKOUT"
    assert candidate.reference_high == 140
    with pytest.raises(ValueError, match="strictly before"):
        breakout_candidate("TEST", bars + [Bar(SESSION, 140, 150, 139, 149, 100_000)], SESSION)


def test_ep_requires_contemporaneous_catalyst_gap_and_early_volume():
    bars = history()
    opening = minute(0, 154, 156, 153, 155)
    assert episodic_pivot_candidate("TEST", bars, SESSION, opening, "earnings") is not None
    assert episodic_pivot_candidate("TEST", bars, SESSION, opening, None) is None
    assert (
        episodic_pivot_candidate("TEST", bars, SESSION, minute(0, 150, 152, 149, 151), "earnings")
        is None
    )
    assert (
        episodic_pivot_candidate(
            "TEST", bars, SESSION, minute(0, 154, 156, 153, 155, 500), "earnings"
        )
        is None
    )


def test_opening_range_risk_cap_and_ambiguous_bar():
    bars = history()
    candidate = Candidate("TEST", "EP", SESSION, None, "earnings")
    first = minute(0, 154, 156, 153, 155)
    plan = opening_range_plan(candidate, bars, first, minute(1, 155, 157, 154, 157), 20_000)
    assert plan is not None
    assert (plan.entry, plan.stop, plan.shares) == (156, 153, 25)
    assert plan.risk_dollars == 75
    assert opening_range_plan(candidate, bars, first, minute(1, 155, 157, 152, 156), 20_000) is None
    assert (
        opening_range_plan(
            candidate,
            bars,
            first,
            minute(1, 156, 157, 154, 157),
            20_000,
            SetupConfig(max_stop_adr_multiple=0.001),
        )
        is None
    )


def test_breakout_requires_base_high_break_in_second_bar():
    bars = history()
    candidate = breakout_candidate("TEST", bars, SESSION)
    assert candidate is not None
    first = minute(0, 138, 139, 137, 138)
    assert (
        opening_range_plan(candidate, bars, first, minute(1, 139, 139.5, 138, 139), 20_000) is None
    )


def test_csv_scanner_handles_premarket_and_future_daily_rows(tmp_path, monkeypatch, capsys):
    daily = tmp_path / "daily.csv"
    intraday = tmp_path / "bars.csv"
    daily.write_text(
        "symbol,date,open,high,low,close,volume\n"
        + "".join(
            f"TEST,{b.day},{b.open},{b.high},{b.low},{b.close},{b.volume}\n" for b in history()
        )
        + "TEST,2026-09-25,999,1000,998,999,100000\n"
    )
    intraday.write_text(
        "symbol,timestamp,open,high,low,close,volume\n"
        "TEST,2026-09-25T09:25:00-04:00,151,152,150,151,1000\n"
        "TEST,2026-09-25T09:30:00-04:00,154,156,153,155,12000\n"
        "TEST,2026-09-25T09:35:00-04:00,155,157,154,157,12000\n"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "scan",
            "--daily",
            str(daily),
            "--intraday",
            str(intraday),
            "--symbol",
            "TEST",
            "--session",
            "2026-09-25",
            "--equity",
            "20000",
            "--catalyst",
            "earnings",
        ],
    )
    main()
    results = json.loads(capsys.readouterr().out)
    assert {result["candidate"]["setup"] for result in results} == {"BREAKOUT", "EP"}
    assert results[0]["plan"]["shares"] == 25
