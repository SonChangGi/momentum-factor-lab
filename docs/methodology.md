# Momentum Factor Lab Methodology

This project compares explainable momentum factors on a current liquid US stock/ETF universe. It is designed for practical research review, not automated trading or personalized advice.

## Factor families

The first implementation includes traditional 12-1, 6-1, 3-month, multi-horizon, volatility-adjusted, risk-adjusted, dual momentum, moving-average trend, drawdown-aware, and reversal-adjusted momentum variants.

## Backtest assumptions

Signals are formed from data available before the rebalance date and are applied with a conservative one-trading-day execution delay. Transaction cost and slippage are deducted on rebalance turnover. The default portfolio is long-only and balanced, with top 10-20 names and single-holding caps.

## Robustness gate

The selected factor is chosen from validation / out-of-sample evidence rather than in-sample return alone. Reports include score components, robustness slices, selected-factor parameter sensitivity, SPY benchmark-relative metrics, turnover, drawdown, and data-quality limitations. Monthly long-form factor scores are exported so the selected factor and its alternatives are auditable in Excel.

## Data limitations

The first pass uses free/public data and a current liquid universe. This can introduce survivorship bias, ETF inception bias, missing delisted names, provider adjusted-price quirks, and historical-universe membership gaps. Live current recommendations require a fresh successful live-data run; offline sample output is clearly labeled sample/offline.

## Non-advice disclaimer

Outputs are research artifacts and model-portfolio examples, not personalized financial, tax, legal, or investment advice.
