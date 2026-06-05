# Momentum Factor Lab methodology

## Universe construction

The default candidate universe is packaged as `momentum_factor_lab/resources/default_universe.csv` and contains 3,500 current US-listed symbols: 2,500 stocks and 1,000 ETFs. The seed is built from public listing-style sources and ordered so bounded live smoke runs start with major ETFs and large liquid stocks before broader stocks/ETFs.

Runtime separates:

1. **candidate universe** — broad source-aware symbol list;
2. **requested price universe** — candidate list after optional `--max-price-symbols` cap;
3. **eligible price universe** — symbols with enough price history, fresh prices, minimum price, and liquidity/volume evidence.

Only eligible symbols can enter factor backtests or recommendations. Reports include candidate/requested/eligible/exclusion counts and reasons.

## Data collection

- Listing metadata can use the packaged seed or optional public-source refresh.
- yfinance is the primary daily adjusted-price provider and is downloaded in configurable chunks.
- Stooq daily CSV is a bounded fallback for missing symbols. It is labeled separately because close-price/adjustment semantics can differ from yfinance.
- Source summary sheets include cache, retry, partial-failure, subset-run, and provider notes.

## Factor library

The factor registry is `FactorSpec` based. Each factor has a name, category, formula, description, validation notes, and function. The current library has 22 factors:

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
- gap-resistant clipped-return momentum.

## Formula validation

Momentum factors are checked three ways:

1. registry metadata must include formula/category/description/validation notes;
2. runtime audit checks shape/index, finite coverage, and no-lookahead perturbation for every factor;
3. deterministic tests validate core formula helpers and every registered factor’s no-lookahead behavior.

The runtime audit is exported to PDF, Excel, and JSON as `factor_validation`.

## Backtest and scoring

Each factor is backtested as a long-only top-20 portfolio by default. Portfolio targets are generated from the previous trading day’s factor signal and applied with a one-trading-day execution delay. Turnover, transaction cost, and slippage are included.

Factor selection uses validation-first composite scoring across Sharpe, Sortino, Calmar, max drawdown, CAGR, turnover, and train/validation stability. Benchmark-relative metrics include excess return, tracking error, information ratio, and beta to the benchmark.

## Reporting scalability

Excel cannot safely store every symbol × month × factor row for a 2,000+ universe. Therefore:

- `factor_scores` stores latest all-symbol/all-factor scores;
- `factor_score_history_top20` stores monthly top-20-per-factor history;
- full huge matrices are intentionally not written to Excel.
