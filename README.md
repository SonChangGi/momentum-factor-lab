# momentum-factor-lab

Practical momentum factor research/backtesting lab for current liquid US stocks and ETFs.

## What it does

- Builds a broad, explainable momentum factor library.
- Backtests factors with no-lookahead signal alignment and transaction/slippage assumptions.
- Selects a best factor using validation-first risk-adjusted scoring, not in-sample return alone.
- Generates a readable PDF report and Excel workbook with monthly historical factor data, benchmark-relative metrics, parameter sensitivity, robustness evidence, and model-portfolio recommendation weights.

## Quick start

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m momentum_factor_lab.cli run --offline-sample --output-dir outputs/sample --report-dir reports/sample
```

Optional live-data run:

```bash
python -m pip install -e '.[live]'
python -m momentum_factor_lab.cli run --live --output-dir outputs/live --report-dir reports/live
```

If live data is unavailable or stale, current recommendation weights are marked unavailable/stale and offline sample output is not presented as current live advice.

## Outputs

Generated artifacts are ignored by git:

- `reports/...pdf` — narrative report with charts, tables, assumptions, factor comparison, selected factor, recommendations, and limitations.
- `reports/...xlsx` — workbook with config/assumptions, universe, monthly long-form factor scores, latest selected-factor scores, metrics, score components, benchmark-relative metrics, recommendations, exclusions, robustness, and parameter-sensitivity sheets.
- `outputs/...json` — canonical run-results object used to keep PDF and Excel aligned.

## Limitations and disclaimer

This first-pass lab uses a current liquid US stock/ETF universe and free/public data. Historical backtests can contain survivorship bias, delisting omissions, ETF inception bias, adjusted-price quirks, and historical-membership gaps. Outputs are research artifacts and model-portfolio examples, not personalized financial, tax, legal, or investment advice.
