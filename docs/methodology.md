# Momentum Factor Lab methodology

## Universe construction

The default candidate universe is packaged as `momentum_factor_lab/resources/default_universe.csv` and contains 2,400+ current US-listed individual stocks. ETFs are excluded from candidate holdings. The seed is built from public listing-style sources and ordered toward large/liquid stocks before broader stocks.

User-supplied symbol lists are intentionally fail-closed: a symbol-only custom input is not treated as an individual stock unless it resolves to packaged/public stock metadata. Common ETF/ETN/fund tickers and fund-like instrument names are denied, and refresh-mode source rows preserve any Nasdaq Trader ETF flag before combined stock-only filtering.

Runtime separates:

1. **candidate universe** — broad source-aware symbol list;
2. **requested price universe** — stock-candidate list after optional `--max-price-symbols` cap; benchmark symbols may be fetched separately for comparison;
3. **eligible price universe** — stock-candidate symbols with enough price history, fresh prices, minimum price, and liquidity/volume evidence.

Only eligible stock-candidate symbols can enter factor backtests or model-portfolio output rows. Benchmark ETFs such as SPY may be present in raw price data solely for benchmark-relative metrics and are excluded from factor scores, backtest weights, sensitivity, and recommendations. Current live tradable recommendations are emitted only when all tradability requirements pass; otherwise the output is labeled `research_signals`, weights are zeroed, and reports include candidate/requested/eligible/exclusion counts, tradability blockers, liquidity evidence, and capacity warnings.

The tradability gate separates live-data freshness from actual tradable output. A run must have a predeclared factor, full uncapped requested stock-candidate price coverage with eligible symbols covering the requested stock price symbols, point-in-time universe provenance, row-level liquidity pass, and row-level capacity pass. Broad packaged/refresh stock universes must meet the configured 2,000-symbol minimum; smaller user-supplied stock universes stay research-only unless explicitly marked as approved tradable universes and backed by point-in-time provenance. Row-level liquidity requires the configured minimum number of non-null 63-day price, volume, and dollar-volume observations.

## Data collection

- Listing metadata can use the packaged stock-only seed or optional public-source refresh. Public refresh filters ETF/test-issue rows out of the candidate universe.
- yfinance is the primary daily adjusted-price provider and is downloaded in configurable chunks.
- Stooq daily CSV is a bounded fallback for missing symbols. It is labeled separately because close-price/adjustment semantics can differ from yfinance.
- Source summary sheets include cache, retry, partial-failure, subset-run, and provider notes.
- Free/public current-universe sources are not treated as survivorship-free historical membership. Point-in-time provenance can be recorded for gating, but the lab does not independently validate external membership data.

## Factor library

The factor registry is `FactorSpec` based. Each factor has a name, category, formula, description, validation notes, and function. The current library has 55 factors:

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

Each factor is backtested as a long-only top-20 portfolio by default. Portfolio targets are generated from the previous trading day’s factor signal and applied with a one-trading-day execution delay. Turnover, transaction cost, and slippage are included.

Factor selection uses validation-first composite scoring across Sharpe, Sortino, Calmar, max drawdown, CAGR, turnover, and train/validation stability. Benchmark-relative metrics include excess return, tracking error, information ratio, and beta to the benchmark; benchmark prices are comparator-only and non-investable in this stock-only project.

Backtest portfolios are research diagnostics. Live tradable recommendations require the separate tradability gate, predeclared-factor controls, point-in-time universe evidence, and configured capacity inputs (`target_aum` plus `max_adv_participation`) before rows are exported as `recommendations` rather than zero-weight `research_signals`.

## Reporting scalability

Excel cannot safely store every symbol × month × factor row for a 2,000+ universe. Therefore:

- `factor_scores` stores latest all-symbol/all-factor scores;
- `factor_score_history_top20` stores monthly top-20-per-factor history;
- full huge matrices are intentionally not written to Excel.
