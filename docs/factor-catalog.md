# Momentum factor catalog

This catalog is generated from `momentum_factor_lab.factors.FACTOR_SPECS` and documents the live factor library used in reports and JSON/XLSX exports.

- Total factors: **55**
- Categories: **13**
- Price notation: `P[t]` is the adjusted close on signal date `t`; `P[t-k]` is the adjusted close `k` trading days earlier; `MA_n` is an `n`-trading-day moving average; rolling windows use trading-day counts.
- Skip notation: `6m(skip10)` means the return ending 10 trading days before the signal date, reducing short-term reversal/lookahead contamination.
- All factors are cross-sectional ranking signals for the eligible stock-candidate universe; benchmark ETFs are comparator-only and are excluded from factor ranks and recommendations.

## Category coverage

| Category | Count | Factor names |
| --- | ---: | --- |
| acceleration | 6 | `acceleration`, `short_acceleration`, `decay_adjusted`, `accel_1m_vs_3m`, `accel_3m_vs_6m`, `accel_6m_vs_12m` |
| breakout | 3 | `breakout_63d`, `breakout_126d`, `breakout_20d` |
| composite | 1 | `multi_horizon` |
| cross_sectional | 1 | `relative_strength_6m` |
| drawdown | 4 | `drawdown_aware`, `high_52w`, `high_26w`, `ulcer_adjusted` |
| quality | 4 | `consistency`, `trend_quality`, `price_efficiency`, `smooth_return_6m` |
| range | 2 | `range_position`, `range_position_252d` |
| recent | 8 | `mom_10d`, `mom_6m_unskipped`, `mom_3m`, `mom_2m`, `mom_2_1`, `mom_6m`, `mom_12m`, `mom_1m` |
| reversal | 1 | `reversal_adjusted` |
| risk_adjusted | 8 | `vol_adjusted`, `risk_adjusted`, `downside_risk_adjusted`, `low_vol_momentum`, `stability_adjusted`, `vol_adjusted_3m`, `vol_adjusted_12m`, `downside_adjusted_12m` |
| robust | 6 | `gap_resistant`, `winsorized_skip`, `median_return_3m`, `median_return_6m`, `winsorized_3m`, `winsorized_12m` |
| traditional | 5 | `mom_12_1`, `mom_9_1`, `mom_6_1`, `mom_12_2`, `mom_3_1` |
| trend | 6 | `dual_momentum`, `ma_trend`, `time_series_trend`, `ma_slope_50`, `price_vs_ma200`, `ma_stack_quality` |

## Full factor definitions

| # | Factor | Category | Formula / definition | Purpose | Validation notes |
| ---: | --- | --- | --- | --- | --- |
| 1 | `mom_12_1` | traditional | `P[t-21] / P[t-273] - 1` | Traditional 12-1 cross-sectional total return momentum. | Manual shifted-return and no-lookahead tests. |
| 2 | `mom_9_1` | traditional | `P[t-21] / P[t-210] - 1` | Nine-month skipped return momentum. | Manual shifted-return and no-lookahead tests. |
| 3 | `mom_6_1` | traditional | `P[t-21] / P[t-147] - 1` | Traditional 6-1 cross-sectional total return momentum. | Manual shifted-return and no-lookahead tests. |
| 4 | `mom_12_2` | traditional | `P[t-42] / P[t-294] - 1` | Twelve-month momentum with a two-month skip to reduce reversal contamination. | Independent raw-shift golden tests. |
| 5 | `mom_3_1` | traditional | `P[t-21] / P[t-84] - 1` | Traditional 3-1 skipped return momentum. | Independent shifted-return and no-lookahead tests. |
| 6 | `mom_10d` | recent | `P[t] / P[t-10] - 1` | Ten-trading-day short-horizon momentum with high-turnover warning. | Literal golden-vector simple-return tests and turnover warning audit. |
| 7 | `mom_6m_unskipped` | recent | `P[t] / P[t-126] - 1` | Six-month recent momentum without a skip window. | Independent raw-shift golden tests. |
| 8 | `mom_3m` | recent | `P[t] / P[t-63] - 1` | Three-month recent momentum without skip month. | Simple-return fixture tests. |
| 9 | `mom_2m` | recent | `P[t] / P[t-42] - 1` | Two-month short-horizon momentum for fast leadership changes. | Independent raw-shift golden tests. |
| 10 | `mom_2_1` | recent | `P[t-21] / P[t-63] - 1` | Two-month momentum that skips the most recent month. | Independent raw-shift golden tests. |
| 11 | `mom_6m` | recent | `P[t] / P[t-126] - 1` | Six-month simple momentum without skip month. | Independent simple-return and no-lookahead tests. |
| 12 | `mom_12m` | recent | `P[t] / P[t-252] - 1` | Twelve-month simple momentum without skip month. | Independent simple-return and no-lookahead tests. |
| 13 | `mom_1m` | recent | `P[t] / P[t-21] - 1` | One-month short-horizon momentum. | Simple-return fixture tests. |
| 14 | `multi_horizon` | composite | `0.15*1m + 0.25*3m(skip5) + 0.30*6m(skip10) + 0.30*12m(skip21)` | Weighted 1/3/6/12-month multi-horizon momentum composite. | Component helper tests plus output audit. |
| 15 | `vol_adjusted` | risk_adjusted | `6m(skip10) / annualized_vol_63d` | Six-month momentum scaled by recent annualized volatility. | Division-by-zero and finite coverage audit. |
| 16 | `risk_adjusted` | risk_adjusted | `annualized_mean_return_126d / annualized_vol_126d` | Rolling Sharpe-like annualized return divided by volatility. | Rolling mean/vol helper tests. |
| 17 | `downside_risk_adjusted` | risk_adjusted | `6m(skip10) / annualized_downside_vol_126d` | Momentum scaled by downside volatility only. | Downside fixture tests and finite audit. |
| 18 | `dual_momentum` | trend | `6m relative momentum penalized when price < MA200` | Relative momentum penalized when absolute trend is below the 200-day average. | Trend penalty and no-lookahead audit. |
| 19 | `ma_trend` | trend | `P/MA200 - 1 + 0.5*(MA50/MA200 - 1)` | Trend persistence from price/MA200 and MA50/MA200 structure. | Moving-average fixture tests. |
| 20 | `time_series_trend` | trend | `I(P>MA20)+I(MA20>MA100)+I(MA100>MA200)` | Discrete time-series trend stack across short/intermediate/long averages. | Bounded 0..3 output audit. |
| 21 | `drawdown_aware` | drawdown | `6m(skip10) + P/rolling_high_126 - 1` | Six-month momentum penalized by recent drawdown from rolling high. | Drawdown sign and no-lookahead audit. |
| 22 | `high_52w` | drawdown | `P / rolling_high_252 - 1` | Closeness to 52-week high; less negative is stronger. | Manual rolling-high fixture tests. |
| 23 | `high_26w` | drawdown | `P / rolling_high_126 - 1` | Closeness to a 26-week high for intermediate breakout confirmation. | Independent rolling-high golden tests. |
| 24 | `breakout_63d` | breakout | `P/rolling_high_63 - 1 + 0.5*1m` | Recent breakout pressure with one-month confirmation. | Rolling-high plus 1m fixture tests. |
| 25 | `breakout_126d` | breakout | `P/rolling_high_126 - 1 + 0.5*3m` | Intermediate breakout pressure with three-month confirmation. | Independent rolling-high golden tests. |
| 26 | `reversal_adjusted` | reversal | `12-1 momentum - 0.35*1m momentum` | 12-1 momentum adjusted for short-term reversal risk. | Component helper tests plus no-lookahead audit. |
| 27 | `acceleration` | acceleration | `3m momentum - 0.5*6-1 momentum` | Momentum acceleration toward recent leadership. | Manual acceleration fixture tests. |
| 28 | `short_acceleration` | acceleration | `1m momentum - 0.5*3m momentum` | Short-horizon acceleration signal for very recent leadership surges. | Independent raw-shift golden tests. |
| 29 | `decay_adjusted` | acceleration | `6m(skip10) - 0.25*abs(1m momentum)` | Six-month momentum penalized when very recent moves look overextended. | Independent raw-shift golden tests. |
| 30 | `consistency` | quality | `6m(skip10) * rolling_positive_return_ratio_126d` | Rewards momentum earned consistently across days. | Positive-ratio fixture tests. |
| 31 | `low_vol_momentum` | risk_adjusted | `6m(skip10) - annualized_vol_63d` | Momentum penalized by high recent volatility. | Low-vol ranking fixture tests. |
| 32 | `stability_adjusted` | risk_adjusted | `6m(skip10) / (1 + annualized_vol_126d)` | Six-month momentum damped by one-year realized volatility from price returns. | Independent volatility golden tests. |
| 33 | `relative_strength_6m` | cross_sectional | `cross-sectional percentile_rank(6m(skip10))` | Six-month relative-strength percentile within the eligible universe. | Cross-sectional rank audit. |
| 34 | `trend_quality` | quality | `P/MA126 - 1 + rolling_mean_return_126/rolling_vol_126` | Combines trend slope with smoothness of returns. | Rolling helper and finite audit. |
| 35 | `gap_resistant` | robust | `compound clipped daily returns over 126d` | Momentum using clipped daily returns to reduce single-gap dominance. | Clipped-return fixture tests. |
| 36 | `winsorized_skip` | robust | `compound clipped daily returns over 126d after 10d skip` | Skipped six-month momentum using winsorized daily returns to reduce gap dominance. | Independent clipped-return golden tests. |
| 37 | `price_efficiency` | quality | `6m(skip10) * \|P/P[t-126]-1\| / sum_126(\|daily_return\|)` | Rewards six-month momentum that traveled a direct, low-chop price path. | Path-efficiency fixture tests and division-by-zero audit. |
| 38 | `range_position` | range | `6m(skip10) + (P-low_126)/(high_126-low_126) - 0.5` | Combines six-month momentum with where price sits inside its trailing range. | Rolling-range fixture tests and flat-range audit. |
| 39 | `range_position_252d` | range | `12m(skip21) + (P-low_252)/(high_252-low_252) - 0.5` | Combines long-horizon skipped momentum with position inside a 52-week range. | Independent rolling-range golden tests. |
| 40 | `median_return_3m` | robust | `median(daily_return, 63d) * 63` | Three-month median daily return momentum to reduce outlier sensitivity. | Median-return golden-vector and outlier-gap tests. |
| 41 | `median_return_6m` | robust | `median(daily_return, 126d) * 126` | Six-month median daily return momentum to reduce outlier sensitivity. | Median-return golden-vector and no-lookahead tests. |
| 42 | `winsorized_3m` | robust | `compound clipped [-8%, +8%] daily returns over 63d` | Three-month winsorized compounded momentum. | Winsorized golden-vector and outlier-gap tests. |
| 43 | `winsorized_12m` | robust | `compound clipped [-8%, +8%] daily returns over 252d` | Twelve-month winsorized compounded momentum. | Winsorized no-lookahead and edge-case tests. |
| 44 | `vol_adjusted_3m` | risk_adjusted | `3m simple momentum / annualized_vol_63d` | Three-month momentum scaled by recent annualized volatility. | Division-by-zero and finite coverage audit. |
| 45 | `vol_adjusted_12m` | risk_adjusted | `12-1 momentum / annualized_vol_126d` | Twelve-minus-one momentum scaled by intermediate volatility. | Division-by-zero and no-lookahead audit. |
| 46 | `downside_adjusted_12m` | risk_adjusted | `12-1 momentum / annualized_downside_vol_252d` | Twelve-minus-one momentum scaled by downside volatility. | Downside risk edge-case tests. |
| 47 | `ma_slope_50` | trend | `MA50[t] / MA50[t-21] - 1` | One-month slope of the 50-day moving average. | Moving-average slope fixture tests. |
| 48 | `price_vs_ma200` | trend | `P / MA200 - 1` | Distance of price above/below the 200-day moving average. | Moving-average fixture tests. |
| 49 | `ma_stack_quality` | trend | `I(P>MA20)+I(MA20>MA50)+I(MA50>MA100)+I(MA100>MA200)` | Four-step moving-average stack quality score. | Bounded 0..4 output and no-lookahead audit. |
| 50 | `breakout_20d` | breakout | `P/rolling_high_20 - 1 + 0.5*10d` | Short breakout proximity with ten-day confirmation. | Rolling-high golden-vector tests. |
| 51 | `accel_1m_vs_3m` | acceleration | `1m momentum - 3m momentum` | Acceleration from three-month to one-month leadership. | Manual acceleration fixture tests. |
| 52 | `accel_3m_vs_6m` | acceleration | `3m momentum - 6m momentum` | Acceleration from six-month to three-month leadership. | Manual acceleration fixture tests. |
| 53 | `accel_6m_vs_12m` | acceleration | `6m momentum - 12m momentum` | Acceleration from twelve-month to six-month leadership. | Manual acceleration fixture tests. |
| 54 | `ulcer_adjusted` | drawdown | `6m(skip10) / sqrt(mean(drawdown_126^2, 126d))` | Momentum scaled by Ulcer-style drawdown severity. | Drawdown denominator and finite audit. |
| 55 | `smooth_return_6m` | quality | `6m simple momentum - rolling_std_daily_return_126d` | Six-month return momentum penalized by daily return roughness. | Smoothness edge-case tests. |
