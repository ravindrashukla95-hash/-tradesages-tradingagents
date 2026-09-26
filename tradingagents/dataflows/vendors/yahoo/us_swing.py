"""Temporary yfinance market-data provider for recent US swing research."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.errors import NoMarketDataError, VendorError, VendorRateLimitError
from tradingagents.us_swing.qullamaggie import Bar, OpeningBar

NY = ZoneInfo("America/New_York")


class YFinanceProvider:
    """Fetch daily history and the first two regular-session five-minute bars.

    A ticker factory and clock can be supplied for repeatable offline tests.
    Intraday requests are restricted to the recent Yahoo-supported window.
    """

    def __init__(
        self,
        ticker_factory: Callable[[str], object] = yf.Ticker,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.ticker_factory = ticker_factory
        self.clock = clock or (lambda: datetime.now(NY))

    def load(self, symbol: str, session: date) -> tuple[list[Bar], list[OpeningBar]]:
        now = self.clock().astimezone(NY)
        if not symbol or not symbol.strip():
            raise ValueError("symbol is required")
        if session > now.date():
            raise ValueError("cannot scan a future session")
        if session < now.date() - timedelta(days=59):
            raise ValueError("yfinance five-minute bars are limited to recent sessions (~60 days)")
        if session == now.date() and now.time() < time(9, 40):
            raise ValueError("wait until both five-minute opening bars are complete")

        ticker = self.ticker_factory(symbol)
        # auto_adjust=False retains dividend-unadjusted OHLC; do not mix this
        # price basis with adjusted CSV bars in the same research run.
        try:
            daily = ticker.history(
                start=session - timedelta(days=170),
                end=session + timedelta(days=1),
                interval="1d",
                auto_adjust=False,
                prepost=False,
                actions=False,
                raise_errors=True,
            )
            intraday = ticker.history(
                start=session,
                end=session + timedelta(days=1),
                interval="5m",
                auto_adjust=False,
                prepost=False,
                actions=False,
                raise_errors=True,
            )
        except YFRateLimitError as exc:
            raise VendorRateLimitError("Yahoo Finance rate limited the US swing request") from exc
        except Exception as exc:
            raise VendorError(f"Yahoo Finance request failed for {symbol}: {exc}") from exc
        if daily is None or daily.empty:
            raise NoMarketDataError(symbol, detail="no daily history")
        if intraday is None or intraday.empty:
            raise NoMarketDataError(symbol, detail=f"no five-minute bars on {session}")

        history = [
            Bar(day, *values)
            for stamp, values in self._rows(daily)
            if (day := stamp.date()) < session
        ]
        opening = [
            OpeningBar(stamp.to_pydatetime(), *values)
            for stamp, values in self._rows(intraday, intraday=True)
            if stamp.date() == session and (stamp.hour, stamp.minute) in {(9, 30), (9, 35)}
        ]
        opening.sort(key=lambda bar: bar.time)
        if len(opening) != 2 or len({bar.time for bar in opening}) != 2:
            raise ValueError(f"both completed 09:30 and 09:35 ET bars are required for {symbol}")
        if len(history) < 78:
            raise ValueError(f"at least 78 prior daily bars are required for {symbol}")
        return history, opening

    def load_window(
        self, symbol: str, start: date, end: date
    ) -> tuple[list[Bar], dict[date, list[OpeningBar]]]:
        """Fetch a recent research window in two requests, not one per session.

        The daily series includes the warmup period before ``start``. Intraday
        bars include the regular session so entry-day stops can be replayed.
        """
        now = self.clock().astimezone(NY)
        if not symbol or not symbol.strip() or end < start or end > now.date():
            raise ValueError("invalid symbol or research window")
        if start < now.date() - timedelta(days=59):
            raise ValueError("yfinance five-minute bars are limited to recent sessions (~60 days)")
        if end == now.date() and now.time() < time(9, 40):
            raise ValueError("wait until both five-minute opening bars are complete")
        ticker = self.ticker_factory(symbol)
        try:
            daily = ticker.history(
                start=start - timedelta(days=170),
                end=end + timedelta(days=1),
                interval="1d",
                auto_adjust=False,
                prepost=False,
                actions=False,
                raise_errors=True,
            )
            intraday = ticker.history(
                start=start,
                end=end + timedelta(days=1),
                interval="5m",
                auto_adjust=False,
                prepost=False,
                actions=False,
                raise_errors=True,
            )
        except YFRateLimitError as exc:
            raise VendorRateLimitError("Yahoo Finance rate limited the US swing window") from exc
        except Exception as exc:
            raise VendorError(f"Yahoo Finance window failed for {symbol}: {exc}") from exc
        if daily is None or daily.empty or intraday is None or intraday.empty:
            raise NoMarketDataError(symbol, detail="daily or five-minute window is empty")
        daily_bars = [
            Bar(stamp.date(), *values) for stamp, values in self._rows(daily) if stamp.date() <= end
        ]
        openings: dict[date, list[OpeningBar]] = {}
        for stamp, values in self._rows(intraday, intraday=True):
            if start <= stamp.date() <= end and time(9, 30) <= stamp.time() < time(16):
                openings.setdefault(stamp.date(), []).append(
                    OpeningBar(stamp.to_pydatetime(), *values)
                )
        return daily_bars, openings

    @staticmethod
    def _rows(frame: pd.DataFrame, intraday: bool = False):
        required = ("Open", "High", "Low", "Close", "Volume")
        if any(column not in frame.columns for column in required):
            raise ValueError("Yahoo OHLCV response is missing required columns")
        if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
            raise ValueError("Yahoo timestamps must be unique and ordered")
        for stamp, row in frame.iterrows():
            if pd.isna(row[list(required)]).any():
                raise ValueError("Yahoo OHLCV contains missing values")
            if intraday and stamp.tzinfo is None:
                raise ValueError("Yahoo five-minute timestamps must be timezone aware")
            eastern = stamp.tz_convert(NY) if stamp.tzinfo else stamp
            yield eastern, tuple(float(row[column]) for column in required)
