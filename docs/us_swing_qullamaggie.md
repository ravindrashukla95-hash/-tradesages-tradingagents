# TradeSages US Swing: Qullamaggie research v1

This module builds deterministic, long-only **Breakout** and **Episodic Pivot**
screens and a five-minute opening-range trade plan. Testing uses **yfinance**
by default; ThetaData is reserved for the final data integration. It is an initial research
implementation. It does not submit orders, forecast win rate, or claim to
reproduce all of Kristjan Kullamägi's discretionary decisions.

## Source and rule mapping

Primary source: https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/
and https://qullamaggie.com/how-to-master-a-setup-episodic-pivots/ .

| Setup | Published description | v1 interpretation to test |
| --- | --- | --- |
| Breakout | Large prior move, orderly 2-week to 2-month base, opening-range break | Prior 63-session window gains at least 30% from its low to high; latest 15-session base is at most 30% deep, close within 5% of base high, mean daily range tightens in latter half; second five-minute bar breaks both opening and base high |
| Episodic Pivot | News/earnings surprise, 10%+ opening gap and exceptional early volume | A supplied contemporaneous catalyst, opening gap at least 10%, first five-minute volume at least 10% of prior 20-session average daily volume; second five-minute bar breaks opening high |
| Risk | Stop at low of day; keep stop distance within ADR/ATR; cap account risk | Initial stop at first five-minute low, distance at most 1x prior 20-day ADR; 0.5% account risk and 20% capital cap |

The base depth, tightness calculation, early-volume threshold, liquidity floors,
five-minute choice, account risk and position cap are **TradeSages hypotheses**.
The author describes alternatives, including one-minute or later opening ranges.
All thresholds are configurable via `SetupConfig`.

## Test with yfinance

```bash
python -m tradingagents.us_swing.scan \
  --symbol NVDA --session 2026-09-25 --equity 20000 \
  --catalyst 'earnings release known before 09:30 ET'
```

The scanner fetches daily history and the 09:30/09:35 ET five-minute bars.
The EP catalyst remains a contemporaneous, manually supplied fact; Yahoo price
data alone cannot establish whether a gap was caused by a qualifying surprise.
If no valid candidate exists, `setups` is empty. This command is for *recent
completed sessions only*. yfinance documents a roughly 60-day intraday history
limit: https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html .
The provider rejects dates more than 59 calendar days old and does not return
the current session until both opening bars have completed. Yahoo data availability
and adjustments still require verification before drawing performance conclusions.

### Recent-window trade outcomes

```bash
python -m tradingagents.us_swing.window \
  --symbols NVDA,TSLA,PLTR --days 59 --equity 20000
```

Supply a **fixed, declared ticker list** so the report does not silently change
its universe. It downloads each symbol's daily warmup and recent five-minute
bars, counts Breakout candidates and entry plans, and replays completed trades.
The window starts no earlier than the provider's 59-day limit. Outcomes use an
initial stop at the opening low, sell half on the fourth session close, move
the stop to break even, and sell the remainder at the next open after the
first close below the 10-day simple moving average. A gap below the stop fills
at the open. Open trades are excluded from win rate and mean R.

These are **single-symbol diagnostics**. They do not model spread, slippage,
fees, competing signals, cash use across symbols, or a point-in-time universe.
The price-only runner excludes Episodic Pivot because contemporaneous catalyst
records are required. A Yahoo HTTP 429 error is reported as an error, not as
a zero-signal session or a performance result.

## Offline CSV alternative

Export point-in-time US equity data into two files:

```text
daily.csv: symbol,date,open,high,low,close,volume
bars.csv: symbol,timestamp,open,high,low,close,volume
```

`timestamp` must include a US Eastern UTC offset (for example,
`2026-09-25T09:30:00-04:00`); include only regular-session bars in `bars.csv`.
Prices should be on a consistent split-adjustment basis. Historical research
also requires a point-in-time universe with delisted stocks, contemporaneous
news/earnings timestamps, and modeled spread/slippage/corporate actions.

```bash
python -m tradingagents.us_swing.scan --provider csv \
  --daily daily.csv --intraday bars.csv --symbol NVDA \
  --session 2026-09-25 --equity 20000 \
  --catalyst 'earnings release known before 09:30 ET'
```

The output contains a provider name and an array of candidates and optional trade plans. A null plan
means the trigger, stop-distance, or sizing conditions failed. The CLI accepts
an operator-provided catalyst; it does not infer the catalyst from future news.

## Build sequence

1. **Done:** deterministic candidates, opening-range plan, explicit data contract.
2. Next: test the universe and strategy logic with yfinance's recent daily and
   five-minute bars. Add timestamped earnings/news and an order/portfolio
   simulation with realistic fills, costs, delisted symbols and regime splits.
3. Final data integration: ThetaData adapter for historical US equities and
   minute bars, with feed permissions and adjusted-price consistency checked.
   Credentials stay outside git.
4. After research: paper execution, daily risk controls and review of live
   versus simulated fills. TradingAgents analysts may add context but cannot
   override deterministic sizing/risk checks.

The repository's existing `tradingagents/backtest.py` evaluates LLM decisions
at ticker/date cells; it is not an order/portfolio simulator. Keep strategy
performance separate until an actual fill and ledger simulator exists.
