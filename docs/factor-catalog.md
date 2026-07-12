# Momentum factor catalog

이 문서는 core 및 advanced factor registry에서 기계적으로 생성됩니다.

- Total factors: **64**
- Independent selection-eligible factors: **61**
- Compatibility aliases: **3**
- Definition and implementation digest: `2ac253604053fce7e5aadc61c85a23ca1afe60146bf66cdaf2c9f467d9216ae6`
- `P[t]` is adjusted close at signal date `t`; rolling windows use trading sessions.
- Benchmark symbols are comparator-only and never candidate holdings.

## Category coverage

| Category | Count | Factor names |
| --- | ---: | --- |
| acceleration | 6 | `acceleration`, `short_acceleration`, `decay_adjusted`, `accel_1m_vs_3m`, `accel_3m_vs_6m`, `accel_6m_vs_12m` |
| asymmetry | 1 | `up_down_capture_6m` |
| breakout | 3 | `breakout_63d`, `breakout_126d`, `breakout_20d` |
| composite | 1 | `multi_horizon` |
| cross_sectional | 3 | `relative_strength_6m`, `residual_12_1`, `excess_ir_6m` |
| drawdown | 4 | `drawdown_aware`, `high_52w`, `high_26w`, `ulcer_adjusted` |
| quality | 6 | `consistency`, `persistent_12_1`, `trend_quality`, `price_efficiency`, `smooth_return_6m`, `high_persistence_6m` |
| range | 2 | `range_position`, `range_position_252d` |
| recent | 8 | `mom_10d`, `mom_6m_unskipped`, `mom_3m`, `mom_2m`, `mom_2_1`, `mom_6m`, `mom_12m`, `mom_1m` |
| reversal | 1 | `reversal_adjusted` |
| risk_adjusted | 8 | `vol_adjusted`, `risk_adjusted`, `downside_risk_adjusted`, `low_vol_momentum`, `stability_adjusted`, `vol_adjusted_3m`, `vol_adjusted_12m`, `downside_adjusted_12m` |
| robust | 7 | `gap_resistant`, `winsorized_skip`, `median_return_3m`, `median_return_6m`, `winsorized_3m`, `winsorized_12m`, `jump_excluded_6m` |
| tail_risk | 1 | `tail_resilient_6m` |
| traditional | 5 | `mom_12_1`, `mom_9_1`, `mom_6_1`, `mom_12_2`, `mom_3_1` |
| trend | 6 | `dual_momentum`, `ma_trend`, `time_series_trend`, `ma_slope_50`, `price_vs_ma200`, `ma_stack_quality` |
| volume | 2 | `volume_confirmed_mom_6m`, `signed_volume_pressure_3m` |

## Full definitions

| # | Factor | Category | Formula | Description | History | Selection | Alias | Limitations | References |
| ---: | --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| 1 | `mom_12_1` | traditional | `P[t-21] / P[t-273] - 1` | Traditional 12-1 cross-sectional total return momentum. | 274 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1111/j.1540-6261.1993.tb04702.x](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) |
| 2 | `mom_9_1` | traditional | `P[t-21] / P[t-210] - 1` | Nine-month skipped return momentum. | 211 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1111/j.1540-6261.1993.tb04702.x](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) |
| 3 | `mom_6_1` | traditional | `P[t-21] / P[t-147] - 1` | Traditional 6-1 cross-sectional total return momentum. | 148 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1111/j.1540-6261.1993.tb04702.x](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) |
| 4 | `mom_12_2` | traditional | `P[t-42] / P[t-294] - 1` | Twelve-month momentum with a two-month skip to reduce reversal contamination. | 295 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1111/j.1540-6261.1993.tb04702.x](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) |
| 5 | `mom_3_1` | traditional | `P[t-21] / P[t-84] - 1` | Traditional 3-1 skipped return momentum. | 85 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1111/j.1540-6261.1993.tb04702.x](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) |
| 6 | `mom_10d` | recent | `P[t] / P[t-10] - 1` | Ten-trading-day short-horizon momentum with high-turnover warning. | 11 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 7 | `mom_6m_unskipped` | recent | `P[t] / P[t-126] - 1` | Six-month recent momentum without a skip window. | 127 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 8 | `mom_3m` | recent | `P[t] / P[t-63] - 1` | Three-month recent momentum without skip month. | 64 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 9 | `mom_2m` | recent | `P[t] / P[t-42] - 1` | Two-month short-horizon momentum for fast leadership changes. | 43 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 10 | `mom_2_1` | recent | `P[t-21] / P[t-63] - 1` | Two-month momentum that skips the most recent month. | 64 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 11 | `mom_6m` | recent | `P[t-10] / P[t-136] - 1` | Six-month momentum ending ten trading days before the signal date to avoid very recent reversal noise. | 137 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 12 | `mom_12m` | recent | `P[t] / P[t-252] - 1` | Twelve-month simple momentum without skip month. | 253 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 13 | `mom_1m` | recent | `P[t] / P[t-21] - 1` | One-month short-horizon momentum. | 22 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 14 | `multi_horizon` | composite | `0.15*1m + 0.25*3m(skip5) + 0.30*6m(skip10) + 0.30*12m(skip21)` | Weighted 1/3/6/12-month multi-horizon momentum composite. | 274 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 15 | `vol_adjusted` | risk_adjusted | `6m(skip10) / annualized_vol_63d` | Six-month momentum scaled by recent annualized volatility. | 137 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 16 | `risk_adjusted` | risk_adjusted | `annualized_mean_return_126d / annualized_vol_126d` | Rolling Sharpe-like annualized return divided by volatility. | 127 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 17 | `downside_risk_adjusted` | risk_adjusted | `6m(skip10) / annualized_downside_vol_126d` | Momentum scaled by downside volatility only. | 137 | independent | — | Zero downside deviation remains unavailable rather than using an invented denominator floor.; Current risk overlay extends through the signal date while the momentum numerator ends at t-10. | — |
| 18 | `dual_momentum` | trend | `eligible_percentile_rank(6m(skip10)) where P > MA200; otherwise unavailable` | Eligible-universe relative momentum with an absolute MA200 trend gate. | 200 | independent | — | MA200 is an absolute-trend proxy, not excess return over a risk-free asset.; Legacy factor key retained for output compatibility. | [https://doi.org/10.2139/ssrn.2042750](https://doi.org/10.2139/ssrn.2042750) |
| 19 | `ma_trend` | trend | `P/MA200 - 1 + 0.5*(MA50/MA200 - 1)` | Trend persistence from price/MA200 and MA50/MA200 structure. | 200 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 20 | `time_series_trend` | trend | `I(P>MA20)+I(MA20>MA100)+I(MA100>MA200)` | Discrete time-series trend stack across short/intermediate/long averages. | 200 | independent | — | Moving-average hierarchy, not sign- or volatility-scaled time-series momentum.; Legacy factor key retained for output compatibility. | [https://doi.org/10.1016/j.jfineco.2011.11.003](https://doi.org/10.1016/j.jfineco.2011.11.003) |
| 21 | `drawdown_aware` | drawdown | `6m(skip10) + P/rolling_high_126 - 1` | Six-month momentum penalized by recent drawdown from rolling high. | 137 | independent | — | Adds raw skipped return and current drawdown without cross-sectional component standardization. | — |
| 22 | `high_52w` | drawdown | `P / rolling_high_252 - 1` | Closeness to 52-week high; less negative is stronger. | 252 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1111/j.1540-6261.2004.00695.x](https://doi.org/10.1111/j.1540-6261.2004.00695.x) |
| 23 | `high_26w` | drawdown | `P / rolling_high_126 - 1` | Closeness to a 26-week high for intermediate breakout confirmation. | 126 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 24 | `breakout_63d` | breakout | `P/prior_rolling_high_63 - 1 + 0.5*1m` | Recent breakout above the prior 63-session high with one-month confirmation. | 64 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 25 | `breakout_126d` | breakout | `P/prior_rolling_high_126 - 1 + 0.5*3m` | Intermediate breakout above the prior 126-session high with three-month confirmation. | 127 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 26 | `reversal_adjusted` | reversal | `12-1 momentum - 0.35*1m momentum` | 12-1 momentum adjusted for short-term reversal risk. | 274 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 27 | `acceleration` | acceleration | `annualized_log_rate(0,63) - annualized_log_rate(63,126)` | Non-overlapping three-versus-six-month annualized log-return acceleration. | 190 | excluded | accel_3m_vs_6m | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1016/j.physa.2020.125367](https://doi.org/10.1016/j.physa.2020.125367) |
| 28 | `short_acceleration` | acceleration | `annualized_log_rate(0,21) - annualized_log_rate(21,63)` | Non-overlapping one-versus-three-month annualized log-return acceleration. | 85 | excluded | accel_1m_vs_3m | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1016/j.physa.2020.125367](https://doi.org/10.1016/j.physa.2020.125367) |
| 29 | `decay_adjusted` | acceleration | `6m(skip10) - 0.25*abs(1m momentum)` | Six-month momentum penalized when very recent moves look overextended. | 137 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 30 | `consistency` | quality | `6m(skip10) * positive_daily_return_ratio_126d(skip10)` | Rewards skipped six-month momentum earned consistently over the same formation window. | 137 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 31 | `persistent_12_1` | quality | `12m(skip21) * positive_daily_return_ratio_252d(skip21)` | Long-horizon skipped momentum scaled by the share of positive daily returns in the skipped formation window. | 274 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 32 | `low_vol_momentum` | risk_adjusted | `6m(skip10) - annualized_vol_63d` | Momentum penalized by high recent volatility. | 137 | independent | — | Subtracts annualized volatility from a six-month return without cross-sectional component standardization. | — |
| 33 | `stability_adjusted` | risk_adjusted | `6m(skip10) / (1 + annualized_vol_126d)` | Six-month momentum damped by one-year realized volatility from price returns. | 137 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 34 | `relative_strength_6m` | cross_sectional | `cross-sectional percentile_rank(6m(skip10))` | Six-month relative-strength percentile within the eligible universe. | 137 | excluded | mom_6m | Monotonic rank transform of mom_6m; retained for output compatibility. | — |
| 35 | `trend_quality` | quality | `P/MA126 - 1 + rolling_mean_return_126/rolling_vol_126` | Combines trend slope with smoothness of returns. | 127 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 36 | `gap_resistant` | robust | `compound daily returns clipped to [-8%, +8%] over 126d` | Momentum using clipped daily returns to reduce single-gap dominance. | 127 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 37 | `winsorized_skip` | robust | `compound daily returns clipped to [-5%, +5%] over 126d after 10d skip` | Skipped six-month momentum using winsorized daily returns to reduce gap dominance. | 137 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 38 | `price_efficiency` | quality | `6m(skip10) * \|6m(skip10)\| / sum_126(\|daily_return shifted10\|)` | Rewards skipped six-month momentum that traveled a direct, low-chop path over the same formation window. | 137 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 39 | `range_position` | range | `6m(skip10) + (P-low_126)/(high_126-low_126) - 0.5` | Combines six-month momentum with where price sits inside its trailing range. | 137 | independent | — | Adds a current range-position overlay to skipped return without component standardization. | — |
| 40 | `range_position_252d` | range | `12m(skip21) + (P-low_252)/(high_252-low_252) - 0.5` | Combines long-horizon skipped momentum with position inside a 52-week range. | 274 | independent | — | Adds a current range-position overlay to skipped return without component standardization. | — |
| 41 | `median_return_3m` | robust | `median(daily_return, 63d) * 63` | Three-month median daily return momentum to reduce outlier sensitivity. | 64 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 42 | `median_return_6m` | robust | `median(daily_return, 126d) * 126` | Six-month median daily return momentum to reduce outlier sensitivity. | 127 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 43 | `winsorized_3m` | robust | `compound clipped [-8%, +8%] daily returns over 63d` | Three-month winsorized compounded momentum. | 64 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 44 | `winsorized_12m` | robust | `compound clipped [-8%, +8%] daily returns over 252d` | Twelve-month winsorized compounded momentum. | 253 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 45 | `vol_adjusted_3m` | risk_adjusted | `3m simple momentum / annualized_vol_63d` | Three-month momentum scaled by recent annualized volatility. | 64 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 46 | `vol_adjusted_12m` | risk_adjusted | `12-1 momentum / annualized_vol_126d` | Twelve-minus-one momentum scaled by intermediate volatility. | 274 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 47 | `downside_adjusted_12m` | risk_adjusted | `12-1 momentum / annualized_downside_vol_252d` | Twelve-minus-one momentum scaled by downside volatility. | 274 | independent | — | Zero downside deviation remains unavailable rather than using an invented denominator floor.; Current risk overlay extends through the signal date while the momentum numerator ends at t-21. | — |
| 48 | `ma_slope_50` | trend | `MA50[t] / MA50[t-21] - 1` | One-month slope of the 50-day moving average. | 71 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 49 | `price_vs_ma200` | trend | `P / MA200 - 1` | Distance of price above/below the 200-day moving average. | 200 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 50 | `ma_stack_quality` | trend | `I(P>MA20)+I(MA20>MA50)+I(MA50>MA100)+I(MA100>MA200)` | Four-step moving-average stack quality score. | 200 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 51 | `breakout_20d` | breakout | `P/prior_rolling_high_20 - 1 + 0.5*10d` | Short breakout above the prior 20-session high with ten-day confirmation. | 21 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 52 | `accel_1m_vs_3m` | acceleration | `annualized_log_rate(0,21) - annualized_log_rate(21,63)` | Acceleration from the preceding three-month rate to the recent one-month rate. | 85 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1016/j.physa.2020.125367](https://doi.org/10.1016/j.physa.2020.125367) |
| 53 | `accel_3m_vs_6m` | acceleration | `annualized_log_rate(0,63) - annualized_log_rate(63,126)` | Acceleration from the preceding six-month rate to the recent three-month rate. | 190 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1016/j.physa.2020.125367](https://doi.org/10.1016/j.physa.2020.125367) |
| 54 | `accel_6m_vs_12m` | acceleration | `annualized_log_rate(0,126) - annualized_log_rate(126,252)` | Acceleration from the preceding twelve-month rate to the recent six-month rate. | 379 | independent | — | Research ranking signal; not a full academic portfolio replication. | [https://doi.org/10.1016/j.physa.2020.125367](https://doi.org/10.1016/j.physa.2020.125367) |
| 55 | `ulcer_adjusted` | drawdown | `6m(skip10) / sqrt(mean(drawdown_126^2, 126d))` | Momentum scaled by Ulcer-style drawdown severity. | 251 | independent | — | Zero Ulcer denominator remains unavailable rather than using an invented floor.; Small positive denominators can produce large raw scores; portfolios use ranks, not score-proportional weights. | — |
| 56 | `smooth_return_6m` | quality | `6m simple momentum - rolling_std_daily_return_126d` | Six-month return momentum penalized by daily return roughness. | 127 | independent | — | Subtracts one-day return volatility from a six-month cumulative return without unit standardization. | — |
| 57 | `residual_12_1` | cross_sectional | `sum_252(return shifted21) - beta_252_to_date_eligible_leave_one_out_equal_weight_peers * sum_252(peer_return shifted21)` | Twelve-minus-one beta-adjusted momentum versus date-level eligible leave-one-out peers. | 274 | independent | — | Single leave-one-out equal-weight peer proxy, not a multi-factor residual regression.; Arithmetic daily-return sum omits alpha and idiosyncratic-volatility standardization.; Legacy factor key retained for output compatibility. | [https://doi.org/10.1016/j.jempfin.2011.01.003](https://doi.org/10.1016/j.jempfin.2011.01.003) |
| 58 | `excess_ir_6m` | cross_sectional | `annualized_mean(excess_return_vs_date_eligible_leave_one_out_peers_126d) / annualized_tracking_error_126d` | Six-month information-ratio style momentum versus date-level eligible leave-one-out peers. | 127 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 59 | `up_down_capture_6m` | asymmetry | `mean_126(return \| leave_one_out_peer_return>0, n>=21) - abs(mean_126(return \| leave_one_out_peer_return<0, n>=21))` | Conditional return asymmetry versus eligible leave-one-out peers, with both regimes observed. | 127 | independent | — | Return difference, not benchmark up/down capture ratios.; Both regimes require at least 21 finite stock-return observations.; Legacy factor key retained for output compatibility. | — |
| 60 | `tail_resilient_6m` | tail_risk | `6m(skip10) + q05(daily_return,126d)` | Six-month skipped momentum penalized by poor left-tail daily returns. | 137 | independent | — | Adds a one-day return quantile to a six-month cumulative return without component standardization.; Current tail overlay extends through the signal date while the momentum numerator ends at t-10. | — |
| 61 | `jump_excluded_6m` | robust | `sum_126(daily_return shifted10) - max_126(daily_return shifted10)` | Formation-window momentum that removes the single largest daily jump to reduce one-day gap dominance. | 137 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 62 | `high_persistence_6m` | quality | `mean_63(I(P >= 0.98*rolling_high_126))` | Fraction of recent days spent near a six-month high, capturing persistent leadership rather than one-day proximity. | 188 | independent | — | Research ranking signal; not a full academic portfolio replication. | — |
| 63 | `volume_confirmed_mom_6m` | volume | `6m(skip10) * (1 + clip(log(mean_dollar_volume_21 / prior_mean_dollar_volume_105), -0.5, 0.5))` | Six-month price momentum scaled by recent, non-overlapping dollar-volume confirmation. | 136 | independent | — | Volume confirmation proxy, not a canonical portfolio replication. | [https://doi.org/10.1111/0022-1082.00280](https://doi.org/10.1111/0022-1082.00280) |
| 64 | `signed_volume_pressure_3m` | volume | `sum_63(sign(return) * price * volume) / sum_63(price * volume)` | Three-month signed dollar-volume pressure, bounded between -1 and 1. | 64 | independent | — | Signed-volume pressure is a transparent research proxy. | — |

## Shared validation contract

- All factor panels preserve the input date and symbol axes.
- Signal-date scores use no observations after the signal date.
- Compatibility aliases remain visible but receive no independent composite score.
- Missing required inputs remain missing; they are not imputed with cross-factor medians.
- Actual current targets use only the final observed input row and current eligibility.
