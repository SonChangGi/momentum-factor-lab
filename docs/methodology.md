# Momentum Factor Lab methodology

## Universe construction

The default candidate universe is packaged as `momentum_factor_lab/resources/default_universe.csv` and contains 2,900+ current US-listed individual stocks. ETFs are excluded from candidate holdings. The seed is built from public listing-style sources and ordered toward large/liquid stocks before broader stocks.

User-supplied symbol lists are intentionally fail-closed: a symbol-only custom input is not treated as an individual stock unless it resolves to packaged/public stock metadata. Common ETF/ETN/fund tickers and fund-like instrument names are denied, and refresh-mode source rows preserve any Nasdaq Trader ETF flag before combined stock-only filtering.

Runtime separates:

1. **candidate universe** — broad source-aware symbol list;
2. **requested price universe** — stock-candidate list requested for live pricing; by default this is uncapped, while optional `--max-price-symbols` is reserved for explicit smoke/debug subset runs; benchmark symbols may be fetched separately for comparison;
3. **eligible price universe** — stock-candidate symbols with enough price history, fresh prices, minimum price, and per-date rolling liquidity evidence for model-portfolio backtests.

Only eligible stock-candidate symbols can enter factor backtests or model-portfolio output rows. Benchmark ETFs such as SPY may be present in raw price data solely for benchmark-relative metrics and are excluded from factor scores, backtest weights, sensitivity, and recommendations. Current live runs emit the primary `recommendations` output only when all practical tradability requirements pass; otherwise they fail closed into zero-weight `research_signals` with candidate/requested/eligible/exclusion counts, data-quality diagnostics, liquidity evidence, and capacity warnings.

The practical execution checklist requires live-data freshness, an explicitly predeclared/frozen factor-selection policy, no explicit price-symbol cap, complete requested price coverage from requested stock-candidate symbols into eligible price symbols, broad or explicitly approved tradable-universe provenance, structured point-in-time universe provenance, row-level data-quality pass, row-level liquidity pass, and row-level capacity pass. By default, `research_validation` selects a factor for research ranking only and is blocked from tradable recommendation output; `walk_forward` is also same-run research diagnostics unless the factor was frozen before the live run. `--factor-selection-mode predeclared --selected-factor ...` remains available as an intentional frozen/predeclared override. Broad packaged/refresh stock universes should meet the configured 2,000-symbol minimum; smaller user-supplied stock universes are tradable only when marked as approved tradable universes and backed by point-in-time provenance. Row-level hard checks reject missing prices, excessive missing prices, non-positive prices, stale prices, insufficient history, below-minimum prices, provider-adjustment-incompatible close-price fallbacks, insufficient liquidity evidence, failed liquidity floors, failed capacity checks, and extreme adjusted daily-return anomalies. Research-only rows force tradable/proposed weights to zero. Practical PIT provenance should include structured source, as-of date, symbol count, and hash/snapshot evidence, not only a free-text date.

## Data collection

- Listing metadata can use the packaged stock-only seed or optional public-source refresh. Public refresh filters ETF/test-issue rows out of the candidate universe.
- yfinance is the primary daily adjusted-price provider and is downloaded in configurable chunks.
- Stooq daily CSV is the first fallback for missing symbols. By default, every yfinance-missing symbol is retried; `--stooq-fallback-limit 0` disables this fallback and positive limits are smoke/debug bounds. Stooq fallback rows are labeled separately because close-price/adjustment semantics can differ from yfinance.
- FinanceDataReader is an optional second fallback for still-missing symbols when installed via the `live` extra. By default, every remaining missing symbol is retried; `--finance-datareader-fallback-limit 0` disables this fallback and positive limits are smoke/debug bounds. FinanceDataReader fallback rows are also labeled separately when used.
- Source summary sheets include cache, retry, partial-failure, subset-run, and provider notes.
- `data_quality` exports one row per requested symbol, including source labels, first/last price dates, recent missing-price and missing-volume ratios, non-positive price counts, recent and full-history extreme adjusted daily-return counts, stale-days, exclusion reasons, and pass/fail status. Recommended/research-signal rows inherit these diagnostics; hard price-integrity checks reject hard price-integrity failures, fallback close-price sources, volume/liquidity gaps, and failed capacity checks before any current recommendations can be emitted.
- Free/public current-universe sources are not treated as survivorship-free historical membership. Point-in-time provenance can be recorded for gating, but the lab does not independently validate external membership data.

## Factor library

The factor registry is `FactorSpec` based. Each factor has a name, category, formula, description, validation notes, and function. The current library has 55 factors; the full formula and definition table is kept in `docs/factor-catalog.md` and exported in the `factor_definitions` report sheet:

- traditional skipped return: 12-1, 9-1, 6-1;
- recent momentum: 3m, 1m;
- composite multi-horizon;
- volatility/risk/downside-risk adjusted;
- dual and moving-average trend;
- time-series trend;
- drawdown-aware and 52-week-high proximity;
- 63-day breakout;
- reversal-adjusted;
- acceleration;
- consistency;
- low-vol momentum;
- relative-strength percentile;
- trend quality;
- gap-resistant clipped-return momentum;
- robust median/winsorized variants;
- volatility/downside/ulcer-adjusted variants;
- moving-average slope/stack variants;
- multiple breakout and acceleration horizons;
- range-position and path-efficiency quality variants.

## Formula validation

Momentum factors are checked three ways:

1. registry metadata must include formula/category/description/validation notes;
2. runtime audit checks shape/index, finite coverage, and no-lookahead perturbation for every factor;
3. deterministic tests validate core formula helpers and every registered factor’s no-lookahead behavior.

The runtime audit is exported to PDF, Excel, and JSON as `factor_validation`.

## Backtest and scoring

Each factor is backtested as a long-only top-20 portfolio by default. Portfolio targets are generated from the previous trading day’s factor signal and applied with a one-trading-day execution delay. Turnover, transaction cost, and slippage are included. Drift-aware turnover preserves liquidation turnover even when a held symbol has missing trade-date price evidence, so stale/gappy data does not erase exit costs.

Factor selection uses validation-first composite scoring across Sharpe, Sortino, Calmar, max drawdown, CAGR, turnover, and train/validation stability. Benchmark-relative metrics include excess return, tracking error, information ratio, and beta to the benchmark; benchmark prices are comparator-only and non-investable in this stock-only project.

Backtest portfolios are diagnostics for factor comparison and remain comparable capped top-N portfolios. Daily returns and turnover now use the same drifted holdings state between rebalances: targets are formed from the previous trading day signal, applied with a one-day delay, drift with price movement, and are compared to the same drifted state for turnover/costs. Current `recommendations` are then sized separately with `score_size_liquidity` weights: selected-factor score, best-effort market cap when available, and 63-day average dollar volume as a size/liquidity proxy when market cap is unavailable. Live runs export `recommendations` only when current ranked rows pass every tradability gate; point-in-time universe evidence, fallback-source compatibility, and configured capacity inputs (`target_aum` plus `max_adv_participation`) are hard gates rather than advisory labels. Cost-stress exports recompute return/risk metrics from realized turnover at each stress cost rate; they are not just descriptive turnover × bps totals.

## Reporting scalability

Excel cannot safely store every symbol × month × factor row for a 2,000+ universe. Therefore:

- `factor_scores` stores latest all-symbol/all-factor scores with eligibility scope columns so raw ineligible diagnostics are distinguishable from current model-portfolio-eligible scores;
- `factor_score_history_top20` stores eligibility-aware monthly top-20-per-factor history;
- full huge matrices are intentionally not written to Excel.

Selected-factor sensitivity reports factor-parameter variants when supported by the factor family and labels unsupported families as base-factor plus portfolio-parameter coverage only.
