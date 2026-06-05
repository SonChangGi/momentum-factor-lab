# momentum-factor-lab

Practical momentum factor research/backtesting lab for broad US stocks and ETFs.

## What it does

- Builds a source-aware candidate universe of **3,500 US-listed symbols** by default: 2,500 stocks and 1,000 ETFs from packaged public-source seeds.
- Supports optional public-source refresh from SEC company tickers and Nasdaq Trader symbol directories.
- Downloads daily adjusted prices from yfinance in chunks, with bounded Stooq fallback and source/provenance reporting.
- Compares **22 explainable momentum factors** across traditional, recent, composite, trend, risk-adjusted, drawdown, breakout, reversal, acceleration, consistency, and robust-return families.
- Backtests each factor as a long-only **top-20 portfolio** at each rebalance with one-day execution delay and transaction/slippage assumptions.
- Selects a best factor using validation-first risk-adjusted scoring, not in-sample return alone.
- Generates a readable PDF report and Excel workbook with data-source coverage, factor formulas, validation audit, benchmark-relative metrics, sensitivity, robustness, and model-portfolio recommendation weights.

## Quick start

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m momentum_factor_lab.cli run --offline-sample --output-dir outputs/sample --report-dir reports/sample
```

Optional live-data smoke run:

```bash
python -m pip install -e '.[live]'
python -m momentum_factor_lab.cli run \
  --live \
  --max-price-symbols 80 \
  --stooq-fallback-limit 3 \
  --output-dir outputs/live-smoke \
  --report-dir reports/live-smoke
```

Full candidate-universe live runs omit `--max-price-symbols`, but free data providers can be slow, partial, or rate-limited. Any capped run is explicitly labeled as a subset run in JSON/PDF/Excel.

## Outputs

Generated artifacts are ignored by git:

- `reports/...pdf` — narrative report with charts, tables, assumptions, factor comparison, selected factor, data coverage, formula validation, recommendations, and limitations.
- `reports/...xlsx` — workbook with config/assumptions, universe, data sources, factor definitions, factor validation, latest factor scores, top-20 historical factor scores, metrics, benchmark-relative metrics, recommendations, exclusions, robustness, and sensitivity.
- `outputs/...json` — canonical run-results object used to keep PDF and Excel aligned.

## Public/free data sources

- SEC company tickers exchange JSON: `https://www.sec.gov/files/company_tickers_exchange.json`
- Nasdaq Trader symbol directories: `http://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt`, `http://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt`
- yfinance free/public daily adjusted prices.
- Stooq daily CSV fallback for bounded missing-symbol attempts.

## Limitations and disclaimer

This lab uses current listed symbols and free/public data. Historical backtests can contain survivorship bias, delisting omissions, ETF inception bias, adjusted-price/provider differences, rate-limit gaps, and historical-membership gaps. Outputs are research artifacts and model-portfolio examples, not personalized financial, tax, legal, or investment advice.
