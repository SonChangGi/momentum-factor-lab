# momentum-factor-lab

Practical momentum factor research/backtesting lab for broad US stocks and ETFs.

## What it does

- Builds a source-aware candidate universe of **3,500 US-listed symbols** by default: 2,500 stocks and 1,000 ETFs from packaged public-source seeds.
- Supports optional public-source refresh from SEC company tickers and Nasdaq Trader symbol directories.
- Downloads daily adjusted prices from yfinance in chunks, with bounded Stooq fallback and source/provenance reporting.
- Compares **22 explainable momentum factors** across traditional, recent, composite, trend, risk-adjusted, drawdown, breakout, reversal, acceleration, consistency, and robust-return families.
- Backtests each factor as a long-only **top-20 portfolio** at each rebalance with one-day execution delay and transaction/slippage assumptions.
- Selects a best factor using validation-first risk-adjusted scoring, not in-sample return alone.
- Generates a readable PDF report and Excel workbook with data-source coverage, factor formulas, validation audit, benchmark-relative metrics, sensitivity, robustness, and gated model-portfolio outputs: live tradable recommendations only when all tradability gates pass, otherwise zero-weight research signals with row-level liquidity and capacity evidence.

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
  --selected-factor mom_12_1 \
  --max-price-symbols 80 \
  --stooq-fallback-limit 3 \
  --output-dir outputs/live-smoke \
  --report-dir reports/live-smoke
```

Live tradable recommendations require `--selected-factor`, fresh live data, an uncapped requested price universe, point-in-time universe evidence, and liquidity evidence. When any tradability requirement is missing, the run exports `research_signals` with zero weights and explicit blockers instead of tradable recommendations.

For a run to emit `recommendations` rather than `research_signals`, it must also pass row-level checks:

- full uncapped price coverage from a broad 2,000+ candidate universe, or an explicitly approved tradable universe;
- explicit point-in-time universe provenance/attestation via `--point-in-time-universe-provenance`;
- non-missing 63-day price/volume/dollar-volume evidence for every recommended row, with at least `--min-liquidity-observations` observations;
- configured capacity inputs (`--target-aum` and `--max-adv-participation`) with every target position inside the 63-day ADV participation limit.

Without those inputs, current free/public live runs are intentionally research-only. The project does not place trades or connect to brokers.

## Outputs

Generated artifacts are ignored by git:

- `reports/...pdf` — narrative report with charts, tables, assumptions, factor comparison, selected factor, data coverage, formula validation, gated output type, tradability blockers, row-level liquidity/capacity diagnostics, and limitations.
- `reports/...xlsx` — workbook with config/assumptions, universe, data sources, factor definitions, factor validation, latest factor scores, top-20 historical factor scores, metrics, benchmark-relative metrics, gated output sheet (`recommendations` or `research_signals`), exclusions, robustness, and sensitivity.
- `outputs/...json` — canonical run-results object used to keep PDF and Excel aligned.

## Public/free data sources

- SEC company tickers exchange JSON: `https://www.sec.gov/files/company_tickers_exchange.json`
- Nasdaq Trader symbol directories: `http://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt`, `http://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt`
- yfinance free/public daily adjusted prices.
- Stooq daily CSV fallback for bounded missing-symbol attempts.

## Limitations and disclaimer

This lab uses current listed symbols and free/public data unless the user supplies separate point-in-time provenance. Historical backtests can contain survivorship bias, delisting omissions, ETF inception bias, adjusted-price/provider differences, rate-limit gaps, endpoint-liquidity bias, and historical-membership gaps. Outputs are research artifacts and model-portfolio examples unless the explicit tradability gate passes; they are not personalized financial, tax, legal, or investment advice.
