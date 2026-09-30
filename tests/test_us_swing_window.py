from datetime import date, datetime, timedelta, timezone

from tradingagents.us_swing.qullamaggie import Bar, OpeningBar, TradePlan
from tradingagents.us_swing.window import replay

ET = timezone(timedelta(hours=-4))
SESSION = date(2026, 9, 10)


def series() -> list[Bar]:
    prior = [Bar(SESSION - timedelta(days=10 - i), 100, 101, 99, 100, 100_000) for i in range(10)]
    future = [
        (103, 104, 102, 103),
        (104, 107, 103, 106),
        (107, 109, 106, 108),
        (109, 111, 108, 110),
        (106, 107, 104, 105),
        (104, 105, 101, 102),
        (103, 104, 101, 103),
    ]
    return prior + [
        Bar(SESSION + timedelta(days=i), *ohlc, 100_000) for i, ohlc in enumerate(future)
    ]


def opening():
    values = [(103, 104, 102, 103), (103, 104, 102, 103), (103, 104, 101, 103)]
    return {
        SESSION: [
            OpeningBar(
                datetime(2026, 9, 10, 9, 30, tzinfo=ET) + timedelta(minutes=5 * i),
                *ohlc,
                1000,
            )
            for i, ohlc in enumerate(values)
        ]
    }


def test_replay_partial_sale_and_next_open_trail():
    plan = TradePlan("TEST", "BREAKOUT", SESSION, 100, 98, 4, 8)
    result = replay(plan, series(), opening())
    assert result.exit_reason == "10-day close trail"
    assert result.exit_date == SESSION + timedelta(days=6)
    assert result.realized_pnl == 26
    assert result.r_multiple == 3.25


def test_replay_gap_through_stop_fills_at_open():
    plan = TradePlan("TEST", "BREAKOUT", SESSION, 100, 98, 4, 8)
    bars = series()
    bars[11] = Bar(SESSION + timedelta(days=1), 95, 97, 94, 96, 100_000)
    result = replay(plan, bars, opening())
    assert result.exit_reason == "stop"
    assert result.realized_pnl == -20
    assert result.r_multiple == -2.5
