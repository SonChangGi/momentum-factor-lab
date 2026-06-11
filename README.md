# momentum-factor-lab

Practical momentum factor research/backtesting lab for broad US individual stocks.

## What it does

- Builds a source-aware candidate universe of **2,900+ US-listed individual stocks** by default from packaged public-source seeds; ETFs are excluded from candidate holdings.
- Supports optional public-source refresh from SEC company tickers and Nasdaq Trader symbol directories.
- User-supplied `--universe` symbols are fail-closed: they are intersected with packaged/public stock metadata, so unknown symbol-only inputs are not assumed to be individual stocks.
- Downloads daily adjusted prices from yfinance in chunks, with bounded Stooq fallback and source/provenance reporting; benchmark ETF prices may be fetched only for benchmark-relative metrics.
- Compares **55 explainable momentum factors** across traditional, recent, composite, trend, risk-adjusted, drawdown, breakout, reversal, acceleration, consistency, and robust-return families. The full formula/definition catalog is maintained in [`docs/factor-catalog.md`](docs/factor-catalog.md) and mirrored into the `factor_definitions` report sheet.
- Backtests each factor as a long-only **top-20 portfolio** at each rebalance with one-day execution delay and transaction/slippage assumptions.
- Selects a best factor using validation-first risk-adjusted scoring, not in-sample return alone.
- Generates a readable PDF report and Excel workbook with data-source coverage, symbol-level data-quality diagnostics, factor formulas, validation audit, benchmark-relative metrics, sensitivity, robustness, and gated model-portfolio recommendations or zero-weight research signals with explicit fail-closed limitations, row-level data-quality, liquidity, and capacity evidence.

## Quick start

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m momentum_factor_lab.cli run --offline-sample --output-dir outputs/sample --report-dir reports/sample
```

If you want the terminal to explain and collect common inputs such as start/end
date, top-N holdings, max position weight, universe, liquidity filters, and
output folders, use the interactive wizard:

```bash
python -m momentum_factor_lab.cli wizard
```

Press Enter to keep a default. The wizard validates inputs, shows a final
configuration review, and then runs the same factor calculation, backtest, and
report pipeline as the scriptable `run` command. For repeatable automation,
continue using `run` with explicit flags.

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

## Korean GitHub Pages dashboard

The project can also publish a Korean static dashboard for daily monitoring.
The dashboard is designed for GitHub Pages: it uses generated HTML/CSS/JS plus a
compact JSON payload, so no web server is required.

Build a dashboard from an existing run-results JSON file:

```bash
python -m momentum_factor_lab.cli dashboard \
  --run-results 'outputs/sample/run_results_*.json' \
  --site-dir docs
```

Run the saved daily configuration and rebuild the site:

```bash
python -m momentum_factor_lab.cli scheduled-dashboard \
  --config .github/momentum-dashboard-config.json \
  --site-dir docs
```

The committed workflow `.github/workflows/daily-dashboard.yml` has both
`workflow_dispatch` and scheduled runs. The primary schedule is 23:17 UTC
(08:17 KST), with 08:47 and 09:17 KST fallback windows that skip automatically
when the dashboard already executed after 08:00 KST for that Korean calendar
day. It rebuilds `docs/` so GitHub Pages can serve the latest dashboard.
Website controls such as recent period, Top-N, selected factor, and max
position weight are client-side viewing controls; the next scheduled run inputs
are stored in `.github/momentum-dashboard-config.json`.

If the scheduled automation fails or GitHub Actions is delayed, use the
dashboard's **최신 데이터 업데이트 실행** button. The public static page does
not embed a GitHub token; it opens the authenticated GitHub Actions manual-run
screen instead. Sign in with a GitHub account that has repository write access
(저장소 쓰기 권한), press **Run workflow**, and the same pipeline will rerun
from the current branch using the most recent U.S. daily close data available
from the free providers at that moment (그 시점의 가장 최근 데이터):
price collection, factor backtest, stock/weight calculation,
`docs/data/dashboard.json` rebuild, and Pages deployment. The equivalent CLI is:

```bash
gh workflow run daily-dashboard.yml --repo SonChangGi/momentum-factor-lab --ref main
```

Manual runs never skip because of the 08:00 KST freshness guard, but they can
still finish with no `docs/` diff when providers have not published a newer
close or the regenerated dashboard is identical. In that case the workflow exits
without a new commit; confirm the Actions status plus the dashboard 기준일 and
최근 실행 시각 on the page.

By default, live runs do **not** impose an absolute `--max-price-symbols` cap: the requested price universe is the full candidate universe for the selected profile, plus the benchmark comparator. `--max-price-symbols` is still available for explicit smoke/debug runs; when used, reports mark the subset coverage as an execution limitation rather than silently treating it as full-universe evidence.

Live runs emit the primary `recommendations` output only when every tradability requirement passes: fresh live data, an explicitly predeclared factor-selection policy (`--factor-selection-mode predeclared --selected-factor ... --frozen-policy-path ...`) fixed before the run, no explicit price-symbol cap, complete requested coverage, structured point-in-time universe evidence such as `source=... as_of=YYYY-MM-DD symbol_count=... hash=...`, broad or explicitly approved tradable-universe provenance, row-level data-quality pass, row-level liquidity pass, and configured capacity pass. Otherwise the run fails closed into a zero-weight `research_signals` output and lists the unmet requirements in `execution_limitations` / `tradability_blockers`.

By default, `factor_selection_mode=research_validation` ranks factors for research but is not a tradable policy. Passing `--selected-factor` alone does not silently promote the run to practical recommendations; the mode must also be `predeclared` and `--frozen-policy-path` must point to a JSON artifact whose selected factor and mode match the run configuration. The daily dashboard config uses `configs/factor-selection-policy.mom_9_1.v1.json` so the chosen factor is auditable by policy ID and SHA-256 hash. In-run `walk_forward` remains a research diagnostic unless a future version adds independently frozen policy artifacts. Recommendation weights default to `score_size_liquidity`, blending selected-factor score with best-effort market cap when available and 63-day ADV/liquidity proxy otherwise. Hard blockers include:

- missing structured point-in-time universe evidence/provenance;
- subset caps, missing symbols, or partial provider coverage;
- missing or sparse volume/liquidity evidence and failed capacity checks from `--target-aum` / `--max-adv-participation`;
- fallback close-price sources whose adjustment semantics can differ from yfinance adjusted prices;
- missing prices, excessive missing prices, non-positive prices, stale prices, insufficient history, below-minimum prices, and full-history/recent extreme adjusted daily-return anomalies.

The project does not place trades or connect to brokers. Relevant data-quality controls include `--data-quality-lookback-days`, `--max-price-missing-ratio`, `--max-volume-missing-ratio`, `--max-extreme-daily-return`, and `--min-liquidity-observations`. Price-integrity, provider-adjustment, liquidity, and capacity failures are hard stops for current recommendations and remain visible in row-level diagnostics.

## Outputs

Generated artifacts are ignored by git:

- `reports/...pdf` — narrative report with charts, tables, assumptions, factor comparison, selected factor, data coverage, symbol-level data-quality diagnostics, formula validation, recommendation output type, execution limitations, row-level liquidity/capacity diagnostics, and caveats.
- `reports/...xlsx` — workbook with config/assumptions, universe, data sources, `data_quality`, factor definitions, factor validation, latest factor scores with eligibility scope, eligibility-aware top-20 historical factor scores, metrics, benchmark-relative metrics, recomputed cost-stress metrics, primary `recommendations` sheet when tradable, otherwise `research_signals`, exclusions, robustness, and sensitivity.
- `outputs/...json` — canonical strict JSON run-results object used to keep PDF and Excel aligned; non-finite values are converted to JSON nulls rather than NaN/Infinity.

## Public/free data sources

- SEC company tickers exchange JSON: `https://www.sec.gov/files/company_tickers_exchange.json`
- Nasdaq Trader symbol directories: `https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt`, `https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt`
- yfinance free/public daily adjusted prices.
- Stooq daily CSV fallback for missing-symbol attempts; omitted `--stooq-fallback-limit` retries all missing symbols, while `--stooq-fallback-limit 0` disables this fallback.
- Optional FinanceDataReader fallback for still-missing symbols when installed via `.[live]`; omitted `--finance-datareader-fallback-limit` retries all remaining missing symbols, while `0` disables it.

## Limitations and disclaimer

This lab uses current listed individual-stock symbols and free/public data unless the user supplies separate point-in-time provenance. Historical backtests can contain survivorship bias, delisting omissions, benchmark ETF inception/adjustment caveats, adjusted-price/provider differences, rate-limit gaps, endpoint-liquidity bias, and historical-membership gaps. ETFs are not candidate holdings; benchmark ETFs such as SPY may appear only as comparators. Outputs are either gated model-portfolio recommendations or zero-weight research signals, not personalized financial, tax, legal, or investment advice.
