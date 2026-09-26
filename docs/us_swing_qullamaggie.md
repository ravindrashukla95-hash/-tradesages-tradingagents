# TradeSages US Swing: Qullamaggie research v1

This module builds deterministic, long-only **Breakout** and **Episodic Pivot**
screens and a five-minute opening-range trade plan. It is an initial research
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

## Offline example

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
python -m tradingagents.us_swing.scan \
  --daily daily.csv --intraday bars.csv --symbol NVDA \
  --session 2026-09-25 --equity 20000 \
  --catalyst 'earnings release known before 09:30 ET'
```

The output is a JSON array of candidates and optional trade plans. A null plan
means the trigger, stop-distance, or sizing conditions failed. The CLI accepts
an operator-provided catalyst; it does not infer the catalyst from future news.

## Build sequence

1. **Done:** deterministic candidates, opening-range plan, explicit data contract.
2. Next: ThetaData adapter for historical US equities and minute bars; validate
   feed permissions and adjusted-price consistency. Credentials stay outside git.
3. Next: timestamped earnings/news source, full order and portfolio simulation,
   realistic fill/cost model, delisted universe, walk-forward and regime splits.
4. Only after research: paper execution, daily risk controls and review of live
   versus simulated fills. TradingAgents analysts may add context but cannot
   override deterministic sizing/risk checks.

The repository's existing `tradingagents/backtest.py` evaluates LLM decisions
at ticker/date cells; it is not an order/portfolio simulator. Keep strategy
performance separate until an actual fill and ledger simulator exists.
