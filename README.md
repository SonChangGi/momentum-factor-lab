# momentum-factor-lab

Practical momentum factor research/backtesting lab for broad US individual stocks.

## What it does

- Builds a source-aware candidate universe of **2,400+ US-listed individual stocks** by default from packaged public-source seeds; ETFs are excluded from candidate holdings.
- Supports optional public-source refresh from SEC company tickers and Nasdaq Trader symbol directories.
- User-supplied `--universe` symbols are fail-closed: they are intersected with packaged/public stock metadata, so unknown symbol-only inputs are not assumed to be individual stocks.
- Downloads daily adjusted prices from yfinance in chunks, with bounded Stooq fallback and source/provenance reporting; benchmark ETF prices may be fetched only for benchmark-relative metrics.
- Compares **55 explainable momentum factors** across traditional, recent, composite, trend, risk-adjusted, drawdown, breakout, reversal, acceleration, consistency, and robust-return families. The full formula/definition catalog is maintained in [`docs/factor-catalog.md`](docs/factor-catalog.md) and mirrored into the `factor_definitions` report sheet.
- Backtests each factor as a long-only **top-20 portfolio** at each rebalance with one-day execution delay and transaction/slippage assumptions.
- Selects a best factor using validation-first risk-adjusted scoring, not in-sample return alone.
- Generates a readable PDF report and Excel workbook with data-source coverage, symbol-level data-quality diagnostics, factor formulas, validation audit, benchmark-relative metrics, sensitivity, robustness, and practical model-portfolio recommendations with explicit execution limitations, row-level data-quality, liquidity, and capacity evidence.

## Quick start

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m momentum_factor_lab.cli run --offline-sample --output-dir outputs/sample --report-dir reports/sample
```

Optional broad live-data run:

```bash
python -m pip install -e '.[live]'
python -m momentum_factor_lab.cli run \
  --live \
  --target-aum 100000 \
  --max-adv-participation 0.05 \
  --output-dir outputs/live-broad \
  --report-dir reports/live-broad
```

By default, live runs do **not** impose an absolute `--max-price-symbols` cap: the requested price universe is the full candidate universe for the selected profile, plus the benchmark comparator. `--max-price-symbols` is still available for explicit smoke/debug runs; when used, reports mark the subset coverage as an execution limitation rather than silently treating it as full-universe evidence.

Live runs emit the primary `recommendations` output whenever current ranked data is available and recommended rows pass hard price-integrity checks. By default, the selected factor is the validation-composite backtest leader; `--selected-factor` is only an explicit frozen-policy override. Recommendation weights default to `score_size_liquidity`, blending selected-factor score with best-effort market cap when available and 63-day ADV/liquidity proxy otherwise. Evidence gaps are exported as `execution_limitations` instead of a separate zero-weight `research_signals` output; the legacy `tradability_blockers` field is reserved for fail-closed hard blockers. Important limitations include:

- missing structured point-in-time universe evidence/provenance such as `source=... as_of=YYYY-MM-DD symbol_count=... hash=...`;
- subset caps, missing symbols, or partial provider coverage;
- missing or sparse volume/liquidity evidence and capacity warnings from `--target-aum` / `--max-adv-participation`;
- fallback close-price sources whose adjustment semantics can differ from yfinance adjusted prices.

Hard price-integrity checks still block current recommendations: missing prices, excessive missing prices, non-positive prices, stale prices, insufficient history, below-minimum prices, and full-history/recent extreme adjusted daily-return anomalies. The project does not place trades or connect to brokers.

Relevant data-quality controls include `--data-quality-lookback-days`, `--max-price-missing-ratio`, `--max-volume-missing-ratio`, `--max-extreme-daily-return`, and `--min-liquidity-observations`. Price-integrity failures are hard stops for current recommendations; volume/liquidity gaps are reported in row-level liquidity/capacity diagnostics and capacity warnings.

## Outputs

Generated artifacts are ignored by git:

- `reports/...pdf` — narrative report with charts, tables, assumptions, factor comparison, selected factor, data coverage, symbol-level data-quality diagnostics, formula validation, recommendation output type, execution limitations, row-level liquidity/capacity diagnostics, and caveats.
- `reports/...xlsx` — workbook with config/assumptions, universe, data sources, `data_quality`, factor definitions, factor validation, latest factor scores with eligibility scope, eligibility-aware top-20 historical factor scores, metrics, benchmark-relative metrics, recomputed cost-stress metrics, primary `recommendations` sheet, exclusions, robustness, and sensitivity.
- `outputs/...json` — canonical strict JSON run-results object used to keep PDF and Excel aligned; non-finite values are converted to JSON nulls rather than NaN/Infinity.

## Public/free data sources

- SEC company tickers exchange JSON: `https://www.sec.gov/files/company_tickers_exchange.json`
- Nasdaq Trader symbol directories: `http://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt`, `http://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt`
- yfinance free/public daily adjusted prices.
- Stooq daily CSV fallback for missing-symbol attempts; omitted `--stooq-fallback-limit` retries all missing symbols, while `--stooq-fallback-limit 0` disables this fallback.
- Optional FinanceDataReader fallback for still-missing symbols when installed via `.[live]`; omitted `--finance-datareader-fallback-limit` retries all remaining missing symbols, while `0` disables it.

## Limitations and disclaimer

This lab uses current listed individual-stock symbols and free/public data unless the user supplies separate point-in-time provenance. Historical backtests can contain survivorship bias, delisting omissions, benchmark ETF inception/adjustment caveats, adjusted-price/provider differences, rate-limit gaps, endpoint-liquidity bias, and historical-membership gaps. ETFs are not candidate holdings; benchmark ETFs such as SPY may appear only as comparators. Outputs are model-portfolio recommendations with limitations, not personalized financial, tax, legal, or investment advice.
