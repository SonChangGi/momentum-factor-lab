# Code Review: Momentum Risk Blockers

Date: 2026-06-05 Asia/Seoul
Mode: read-only review; no product feature implementation.
Final recommendation: REQUEST CHANGES
Architectural status: BLOCK for treating current PDF/XLSX/JSON as live tradable recommendations.

> Historical note (superseded 2026-06-08): this review captured the
> pre-remediation state. The current implementation now defaults to an
> uncapped live requested universe, emits a single primary `recommendations`
> output, uses `execution_limitations` for advisory evidence gaps, reserves
> `tradability_blockers` for fail-closed hard blockers, and retries missing
> live symbols through Stooq plus optional FinanceDataReader fallback.

## Independent review lane evidence

- code-reviewer lane `019e94e9-0ac4-7c91-8bdc-3b4e0de3f247`: REQUEST CHANGES.
- architect lane `019e94e9-0b97-7b11-a218-a3c170ee4de3`: BLOCK for tradable recommendations; WATCH only if explicitly research-only.
- team runtime attempt: `omx team 1:code-reviewer ...` failed safely because the leader worktree is dirty; no team state was started and no files were changed by team workers.

## Fresh verification evidence

- `.venv/bin/python -m pytest -q` -> 45 passed.
- `.venv/bin/python -m ruff check .` -> All checks passed.
- Artifact inspection passed for `outputs/live-2000/run_results_20260604T074259.json` and `reports/live-2000/momentum_factor_analysis_20260604T074259.xlsx`:
  - recommendation_status: `current_live_subset_run_2000_of_3500`
  - current_recommendations_available: `true`
  - subset_run: `true`
  - candidate_universe_size: 3500
  - eligible_price_universe_size: 1794
  - selected_factor: `breakout_63d`
  - factor_validation_status: `pass`
  - recommendations: 20 rows, weight sum 1.0

## Blocking findings

### CRITICAL-1: subset live run is still marked current/tradable

Evidence:
- `momentum_factor_lab/data.py:96-105` selects the first `max_price_symbols` symbols from the ordered candidate universe; it is not a random or full-universe run.
- `momentum_factor_lab/workflow.py:287-295` returns `("current_live", True)` for fresh live data without checking `subset_run`.
- `momentum_factor_lab/workflow.py:319-324` appends `_subset_run_2000_of_3500` to the status but does not flip `current_available` to false or suppress weights.
- `outputs/live-2000/run_results_20260604T074259.json` has `recommendation_status=current_live_subset_run_2000_of_3500`, `current_recommendations_available=true`, `subset_run=true`, and 20 nonzero weights.

Risk: The top-20 ranking is conditional on a non-representative 2,000-symbol prefix. Omitted symbols among the remaining 1,500 candidates can displace the selected names.

Recommended fix: Treat capped runs as research/smoke only: `current_recommendations_available=false`, suppress/zero tradable weights, and require full-universe or explicitly user-defined tradable universe coverage before emitting current tradable recommendations.

### CRITICAL-2: factor selection is data-snooped into current recommendations

Evidence:
- `momentum_factor_lab/workflow.py:305-315` computes backtests for every factor through the run end date, chooses `selected_factor = score_components.index[0]`, then uses the same latest selected-factor score to generate recommendations.
- `momentum_factor_lab/workflow.py:81-94` uses one composite ranking over all 22 factors; this is not nested/walk-forward model selection.

Risk: The current recommendation benefits from knowing which factor worked best across the same 2023-2026 sample. This is model-selection look-ahead/data snooping even if individual factor formulas are no-lookahead.

Recommended fix: Use pre-declared/frozen factor selection, or nested/walk-forward selection where each recommendation date only uses factor-selection evidence available before that date.

### HIGH-1: `breakout_63d` selection is under-validated for 2023-2026 regime overfit

Evidence:
- `outputs/live-2000/run_results_20260604T074259.json` config starts at `2023-01-01`; selected factor is `breakout_63d`.
- `momentum_factor_lab/factors.py:93-94` defines `breakout_63d` as `P/rolling_high_63 - 1 + 0.5*1m`, a short-horizon risk-on/breakout design.
- `momentum_factor_lab/workflow.py:194-234` has no breakout-specific parameter sensitivity branch; the live artifact sensitivity sheet has only base/top_n/max_weight variants.
- Artifact score components show `breakout_63d` narrowly ahead of `mom_1m` (`0.7662` vs `0.7597`).

Risk: The winner may reflect a recent AI/semiconductor/risk-on regime rather than a robust momentum factor.

Recommended fix: Add longer cross-regime history, rolling/walk-forward OOS, multiple-comparison controls, and breakout-specific sensitivity over breakout windows/confirmation weights/cost grids before tradable use.

### HIGH-2: point-in-time universe/liquidity look-ahead remains

Positive evidence:
- `momentum_factor_lab/backtest.py:56-72` uses prior-day signal and one-day effective weight shift.
- `momentum_factor_lab/factors.py:203-256` validates factor shape/coverage/no-lookahead perturbation.

Blocking evidence:
- `momentum_factor_lab/data.py:409-434` applies minimum history, latest price, freshness, and trailing 63-day liquidity once at run end.
- `momentum_factor_lab/data.py:441-443` then uses the filtered current eligible columns across the whole historical backtest.

Risk: Historical backtests benefit from today’s survival, price, and liquidity profile.

Recommended fix: Use point-in-time membership and liquidity masks per rebalance date; tests should prove future volume/membership changes cannot alter past holdings.

### HIGH-3: cost and turnover model is too simplified for high-turnover tradability

Evidence:
- `momentum_factor_lab/backtest.py:60-65` computes turnover as `target - last_target`, not target versus drifted pre-trade portfolio weights.
- `momentum_factor_lab/backtest.py:69-72` forward-fills static weights and shifts them one day; it does not model daily drifted holdings or share-level execution.
- `momentum_factor_lab/metrics.py:66-79` averages the whole turnover event series; `_metrics_for_backtests` passes the same turnover series to train/validation slices.
- Live artifact selected-factor average turnover is ~1.7897 per event.

Risk: Costs and turnover penalties can be materially understated or misaligned for a high-turnover breakout strategy.

Recommended fix: Track drifted pre-trade weights/holdings, slice-aligned turnover/costs, and scenario costs/impact by liquidity.

### HIGH-4: top-20 liquidity/capacity is not sufficient for real-money sizing

Evidence:
- `momentum_factor_lab/config.py:21` default `min_avg_dollar_volume` is only $5,000,000.
- `momentum_factor_lab/data.py:428-434` checks only trailing 63-day average volume/dollar volume at the run endpoint.
- `momentum_factor_lab/portfolio.py:15-20` creates equal 5% top-20 weights.
- `momentum_factor_lab/report.py:87-89,170` exports recommendation weights without ADV, capacity, notional, participation, or AUM diagnostics.

Risk: A 5% position may be feasible or impossible depending on AUM and each name’s ADV; the artifact cannot answer capacity.

Recommended fix: Add AUM, ADV, max participation, trade notional, capacity flags, and recommendation-level liquidity diagnostics before tradable output.

### HIGH-5: adjusted price and survivorship/delisting issues are disclosed but not structurally controlled

Evidence:
- `momentum_factor_lab/data.py:248-253` yfinance uses `auto_adjust=True`; `data.py:320-345,387-395` Stooq fallback uses Close with compatibility caveat.
- `momentum_factor_lab/universe.py:130-166` uses current packaged/current user symbols.
- `docs/methodology.md:5` states the default universe is current US-listed symbols.
- `momentum_factor_lab/disclaimers.py:1-4` discloses survivorship/delisting/adjusted-price limitations.

Risk: Disclosure is accurate but not mitigation; returns can be biased by missing delisted names, ETF inception gaps, current membership, and mixed price adjustment semantics.

Recommended fix: Use point-in-time survivorship-free data and delisting returns for institutional backtest claims, or hard-gate such runs as research-only.

### MEDIUM-1: report wording still blurs research artifacts and tradable recommendations

Evidence:
- `momentum_factor_lab/report.py:139-148` puts status, portfolio construction, and disclaimers together on the executive summary.
- `momentum_factor_lab/report.py:170` titles the table `Current / Sample Top-20 Recommendations`.
- `README.md:13,41-42` describes “model-portfolio recommendation weights.”
- Artifact recommendations have 5% weights despite subset status.

Risk: Disclaimers are present, but a user can still interpret the PDF/XLSX/JSON as actionable current weights.

Recommended fix: Split research rankings from tradable order/recommendation outputs; for subset/current-limited runs, rename to research signals and suppress tradable weights.

## Deterministic synthesis

- code-reviewer recommendation: REQUEST CHANGES
- architect status: BLOCK
- final recommendation: REQUEST CHANGES

These artifacts are acceptable as research diagnostics only. They are not merge-ready as a live tradable recommendation system.
