# TradeSages TradingAgents development roadmap

## Project boundary

The first product has two US equity desks: Swing (multi-day positions) and Intraday (same-day positions). Each has its own capital allocation, ledger, limits, decisions, and performance report. The shared services are market data, feature calculations, research orchestration, risk controls, order management, and audit logging. Futures and options are outside the first release.

TradingAgents proposes trade intents. Deterministic services calculate features, size positions, enforce limits, and manage orders. No LLM output can directly place an order.

## Fixed upstream baseline

- Repository: `TauricResearch/TradingAgents`
- Release tag: `refs/tags/v0.5.1` (annotated tag)
- Peeled release commit: `35543d0248bf89fcb92b17a15858ad0c0e940687`
- Development branch: `tradesages/develop`
- License: Apache-2.0; retain upstream notices.

Upstream also has a **branch** named `v0.5.1` at `90be56b9b2ff2431853b81bfaec9497c65646b1f`. Do not use the ambiguous short ref when reproducing the baseline.

## Stages and acceptance gates

| Stage | Work | Gate to advance |
| --- | --- | --- |
| 0. Pin and inventory | Preserve the tagged upstream code, map existing agents and data paths, record environment and license. | Exact commit recorded; clean development branch; baseline smoke checks recorded. |
| 1. Reproduce upstream | Install isolated dependencies, run selected upstream tests and one low-cost sample research run; capture model, prompt, data, and configuration versions. | Repeatable run and known baseline failures documented. No broker connection. |
| 2. Common data and features | Add a ThetaData adapter for entitled US equity history and live data, event-time snapshots, corporate actions, market calendar, freshness checks, and deterministic features. Keep separate fundamentals/news sources. | Historical replay sees only data available at decision time; gaps and stale data fail closed. |
| 3. Swing desk | Universe screening; existing fundamental, market, news, sentiment, bull/bear, trader and portfolio workflow; structured intent with multi-day horizon, invalidation, and review time. | End-to-end historical intent for a small fixed universe with traceable evidence and no future leakage. |
| 4. Intraday desk | Opening scans, VWAP/range/volume/volatility features, short bounded agent workflow, event and latency limits, same-day exits. | Intraday decisions use timestamped snapshots; measured latency fits the decision interval; flat at session end in replay. |
| 5. Comparative research | Build a separate fill and portfolio simulator; run walk-forward tests across regimes with commissions, spreads, slippage, rejected/unfilled orders, corporate actions, LLM costs, and a no-agent baseline. | Out-of-sample results and sensitivity analysis justify each desk independently. |
| 6. Paper platform | Persistent account and position ledger, independent risk engine, OMS, paper broker, dashboard, alerting, reconciliation, kill switch, and audit log. | Multi-week paper operation reconciles decisions, orders, fills, cash, and positions; failure drills pass. |
| 7. Controlled live | Broker adapter, approvals and scoped permissions, small limits, monitoring, rollback, and operational runbook. | Live readiness review after paper evidence and broker/data entitlements are verified; begin with human approval. |

## Immediate implementation order

1. Finish Stage 0 inventory and establish a remote repository for this development branch.
2. Reproduce upstream tests in a pinned Python environment (Stage 1).
3. Define the snapshot and trade-intent schemas before modifying agent prompts.
4. Build Stage 2 data and replay before judging trading performance.

The upstream `tradingagents/backtest.py` evaluates independent ticker/date decisions. Its module explicitly says it is **not a portfolio simulator** and has no filled orders, quantity, or cash ledger. Stage 5 therefore requires a separate execution simulator before reporting strategy returns or drawdowns.

## Stage 0 check (2026-09-25 UTC)

- The development branch was created from the peeled release commit above.
- Python 3.12.14 compiled `tradingagents` and `cli` with `compileall` successfully.
- The current Codex runtime has no `pytest` installed; dependency installation and test execution belong to Stage 1.
- No ThetaData credentials, LLM keys, broker accounts, or orders were used.

## Decisions to record before Stage 2

- Exact ThetaData subscription products, historical coverage, live entitlements, redistribution rights, and rate limits for the intended deployment.
- Broker and account type for paper and eventual live US equities.
- Capital allocations and risk budgets for each desk. Defaults in research must never be mistaken for live limits.
