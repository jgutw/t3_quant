# t3_quant Design Rules
Permanent constraints. Derived from Categories 1 + 2 + account limits.

## Risk
- Hard daily loss $750 (auto-liq). Soft lock $500.
- All signals route through DailyRiskManager.
- Size from stop distance and remaining daily budget.
- Never enter so close to the stop that a normal adverse move immediately threatens the hard limit.

## Mean-Reversion Entry
- Entry region is a band, not a half-line.
- Band sits strictly above the stop-loss.
- Stop and take-profit are coupled.
- Fixed costs create a lower “do-not-enter” zone.

## Evaluation (Mesfin + Bailey/LdP)
- OOS T-stat ≥ 2.0
- Minimum 30 trades
- Positive after realistic round-trip costs
- Consistent sign across calendar years
- Record number of trials N for every multi-variant experiment
- Report both raw and Deflated Sharpe / deflated PF
- Require low PBO before promoting any variant

## Trend on MES
- Short-horizon trend on MES is structurally closed (Kurth et al.).
- Do not continue filter engineering on MES trend.
- Same architectures may be re-tested later on MGC/SIL.

## Gross Edge
Expected gross move must exceed round-trip commission + slippage before further development.

## Current Highest-Conviction Candidate
Single-asset Overnight → Intraday fade on MES, implemented with the entry-band and stop-coupling rules above, evaluated under the deflated metrics standard.

## Regime Rules (Category 3)
- Pure static trend on MES remains closed.
- Any new MES directional experiment must incorporate an explicit regime-transition or changepoint concept (Wood et al. template).
- Full GP-LSTM, multi-scale MS-GARCH, or 27-expert mixtures are out of scope for the current account size and ops constraints.
- Volatility-regime labels may be used only as risk overlays or size scalars, not as primary alpha signals, unless a later experiment proves otherwise under Deflated Sharpe + PBO.
- Prefer the lightest detector that can express “after a break, allow short-lived reversion or go flat; otherwise slow directional or flat”.
