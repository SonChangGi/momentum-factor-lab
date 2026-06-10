from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd

from .data import build_eligibility_mask
from .metrics import metric_summary
from .workflow import RunResult, write_run_results_json

EXCEL_ROW_LIMIT = 1_048_576


def _metadata_frame(result: RunResult) -> pd.DataFrame:
    rows = list(result.metadata.items()) + list(result.config.to_dict().items())
    return pd.DataFrame(rows, columns=["field", "value"])


def _excel_frequency(frequency: str) -> str:
    return "ME" if frequency == "M" else frequency


def _score_columns(result: RunResult) -> list[str]:
    if not result.factor_scores:
        return []
    columns: list[str] = []
    for scores in result.factor_scores.values():
        for column in scores.columns:
            if column not in columns:
                columns.append(column)
    return columns


def _score_eligibility_mask(result: RunResult) -> pd.DataFrame | None:
    columns = _score_columns(result)
    prices = getattr(result.market_data, "prices", pd.DataFrame())
    volumes = getattr(result.market_data, "volumes", pd.DataFrame())
    if not columns or prices is None or prices.empty:
        return None
    reference_index = next(iter(result.factor_scores.values())).index
    price_frame = prices.reindex(index=reference_index, columns=columns)
    if volumes is None or volumes.empty:
        volume_frame = pd.DataFrame(index=reference_index, columns=columns, dtype=float)
    else:
        volume_frame = volumes.reindex(index=reference_index, columns=columns)
    return build_eligibility_mask(price_frame, volume_frame, result.config)


def _eligibility_row(mask: pd.DataFrame | None, date: pd.Timestamp, symbols: pd.Index) -> pd.Series:
    if mask is None or mask.empty or date not in mask.index:
        return pd.Series(pd.NA, index=symbols, dtype="object")
    return mask.loc[date].reindex(symbols).fillna(False).astype(bool)


def _score_scope(eligible: pd.Series) -> pd.Series:
    if eligible.isna().all():
        return pd.Series("raw_research_diagnostic_eligibility_not_available", index=eligible.index)
    return eligible.map(
        {
            True: "eligible_current_model_portfolio",
            False: "raw_ineligible_research_diagnostic",
        }
    )


def _eligible_scores(scores: pd.Series, eligible: pd.Series) -> pd.Series:
    if eligible.isna().all():
        return scores
    return scores.where(eligible.astype(bool))


def _latest_factor_scores_frame(result: RunResult) -> pd.DataFrame:
    rows = []
    eligibility_mask = _score_eligibility_mask(result)
    for factor, scores in result.factor_scores.items():
        date = pd.Timestamp(scores.index[-1])
        latest_scores = scores.iloc[-1]
        eligible = _eligibility_row(eligibility_mask, date, latest_scores.index)
        latest = latest_scores.dropna().rename("score").reset_index()
        latest.columns = ["symbol", "score"]
        latest["eligible_for_current_model_portfolio"] = latest["symbol"].map(eligible).astype("object")
        latest["score_scope"] = latest["symbol"].map(_score_scope(eligible))
        latest.insert(0, "factor", factor)
        latest.insert(0, "date", date)
        rows.append(latest)
    if not rows:
        return pd.DataFrame(columns=["date", "factor", "symbol", "score", "eligible_for_current_model_portfolio", "score_scope"])
    frame = pd.concat(rows, ignore_index=True)
    if len(frame) >= EXCEL_ROW_LIMIT:
        frame = frame.sort_values(["factor", "score"], ascending=[True, False]).groupby("factor").head(5_000)
    return frame


def _status_panel_frame(result: RunResult) -> pd.DataFrame:
    fields = [
        "recommendation_status",
        "recommendation_output_label",
        "research_only",
        "recommendation_output_available",
        "tradable_output_available",
        "universe_profile",
        "universe_source_mode",
        "factor_selection_mode",
        "selected_factor",
        "validation_selected_factor",
        "selected_factor_selection_source",
        "same_run_factor_selection_blocked_for_tradable",
        "same_sample_selection_blocked_for_tradable",
        "factor_selection_warning",
        "recommendation_weighting_method",
        "recommendation_weight_sum",
        "recommendation_cash_weight",
        "recommendation_weighting_components",
        "recommendation_market_cap_source_counts",
        "recommendation_size_component_source_counts",
        "point_in_time_universe",
        "decision_support_tier",
        "fail_closed",
        "fail_closed_reasons",
        "execution_limitations",
        "data_quality_manifest_available",
        "row_level_data_quality_pass",
        "data_quality_gate",
        "recommendation_data_quality_status_counts",
        "data_quality_status_counts",
        "subset_run",
        "candidate_universe_size",
        "eligible_price_universe_size",
        "multiple_testing_warning",
    ]
    return pd.DataFrame(
        [{"field": field, "value": result.metadata.get(field)} for field in fields],
        columns=["field", "value"],
    )


def _factor_family_leaderboard_frame(result: RunResult) -> pd.DataFrame:
    definitions = result.factor_definitions[["factor", "category"]].copy()
    scores = result.score_components.reset_index(names="factor")
    merged = definitions.merge(scores, on="factor", how="left")
    if merged.empty:
        return pd.DataFrame(columns=["category", "best_factor", "best_composite_score", "factor_count"])
    rows = []
    for category, group in merged.groupby("category", dropna=False):
        ranked = group.sort_values("composite_score", ascending=False)
        best = ranked.iloc[0]
        rows.append(
            {
                "category": category,
                "best_factor": best["factor"],
                "best_composite_score": best.get("composite_score"),
                "factor_count": len(group),
            }
        )
    return pd.DataFrame(rows).sort_values("best_composite_score", ascending=False)


def _factor_overlap_top20_frame(result: RunResult) -> pd.DataFrame:
    if result.selected_factor not in result.factor_scores:
        return pd.DataFrame(columns=["factor", "overlap_with_selected_top20", "consensus_symbols"])
    eligibility_mask = _score_eligibility_mask(result)
    latest_date = pd.Timestamp(result.factor_scores[result.selected_factor].index[-1])
    selected_latest = result.factor_scores[result.selected_factor].loc[latest_date]
    selected_eligible = _eligibility_row(eligibility_mask, latest_date, selected_latest.index)
    selected_top = set(_eligible_scores(selected_latest, selected_eligible).dropna().sort_values(ascending=False).head(20).index)
    rows = []
    symbol_counts: dict[str, int] = {}
    for factor, scores in result.factor_scores.items():
        date = pd.Timestamp(scores.index[-1])
        latest_scores = scores.loc[date]
        eligible = _eligibility_row(eligibility_mask, date, latest_scores.index)
        top = list(_eligible_scores(latest_scores, eligible).dropna().sort_values(ascending=False).head(20).index)
        for symbol in top:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        rows.append(
            {
                "factor": factor,
                "overlap_with_selected_top20": len(selected_top.intersection(top)),
                "top20_symbols": ", ".join(top),
            }
        )
    consensus = ", ".join(symbol for symbol, _ in sorted(symbol_counts.items(), key=lambda item: (-item[1], item[0]))[:20])
    frame = pd.DataFrame(rows).sort_values("overlap_with_selected_top20", ascending=False)
    frame["consensus_symbols"] = consensus
    return frame


def _regime_performance_frame(result: RunResult) -> pd.DataFrame:
    regimes = [
        ("2016_2019", "2016-01-01", "2019-12-31"),
        ("2020", "2020-01-01", "2020-12-31"),
        ("2021_2022", "2021-01-01", "2022-12-31"),
        ("2023_current", "2023-01-01", None),
    ]
    rows: list[dict[str, object]] = []
    for factor, backtest in result.backtests.items():
        for regime, start, end in regimes:
            returns = backtest.returns.loc[start:end] if end else backtest.returns.loc[start:]
            if returns.empty:
                continue
            turnover = backtest.turnover.loc[backtest.turnover.index.intersection(returns.index)]
            costs = backtest.costs.loc[backtest.costs.index.intersection(returns.index)]
            rows.append({"factor": factor, "regime": regime, **metric_summary(returns, turnover, costs)})
    return pd.DataFrame(rows)


def _tradability_gate_frame(result: RunResult) -> pd.DataFrame:
    requirements = result.metadata.get("tradability_requirements", {}) or {}
    limitations = set(result.metadata.get("execution_limitations", result.metadata.get("tradability_blockers", [])) or [])
    return pd.DataFrame(
        [
            {"requirement": name, "passed": bool(passed), "advisory_limitation": name in limitations}
            for name, passed in requirements.items()
        ],
        columns=["requirement", "passed", "advisory_limitation"],
    )


def _liquidity_capacity_frame(result: RunResult) -> pd.DataFrame:
    columns = [
        "rank",
        "symbol",
        "proposed_weight",
        "weighting_method",
        "raw_weight_score",
        "pre_cap_weight",
        "weight_cap",
        "weight_cap_excess",
        "tradable_weight_enabled",
        "research_only_reason",
        "score_component",
        "market_cap",
        "market_cap_source",
        "market_cap_component",
        "liquidity_component",
        "size_component_source",
        "avg_share_volume_63d",
        "avg_dollar_volume_63d",
        "data_quality_status",
        "data_quality_pass",
        "data_quality_warning",
        "data_quality_price_source",
        "data_quality_missing_ratio",
        "data_quality_volume_missing_ratio",
        "data_quality_latest_price",
        "data_quality_stale_days",
        "liquidity_evidence_status",
        "capacity_status",
        "capacity_warning",
        "adv_participation",
        "capacity_utilization",
    ]
    return result.recommendations[[col for col in columns if col in result.recommendations]].copy()


def _factor_history_top_frame(result: RunResult) -> pd.DataFrame:
    rows = []
    frequency = _excel_frequency(result.config.rebalance_frequency)
    eligibility_mask = _score_eligibility_mask(result)
    for factor, scores in result.factor_scores.items():
        sampled = scores.resample(frequency).last()
        for date, row in sampled.iterrows():
            eligible = _eligibility_row(eligibility_mask, pd.Timestamp(date), row.index)
            top = _eligible_scores(row, eligible).dropna().sort_values(ascending=False).head(result.config.top_n)
            if top.empty:
                continue
            frame = top.rename("score").reset_index()
            frame.columns = ["symbol", "score"]
            frame["eligible_for_model_portfolio_at_date"] = frame["symbol"].map(eligible).astype("object")
            frame["score_scope"] = frame["symbol"].map(_score_scope(eligible))
            frame.insert(0, "factor", factor)
            frame.insert(0, "date", date)
            frame["rank"] = range(1, len(frame) + 1)
            rows.append(frame)
    if not rows:
        return pd.DataFrame(columns=["date", "factor", "symbol", "score", "rank"])
    frame = pd.concat(rows, ignore_index=True)
    if len(frame) >= EXCEL_ROW_LIMIT:
        return frame.head(EXCEL_ROW_LIMIT - 1)
    return frame


def write_excel(result: RunResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    eligibility_mask = _score_eligibility_mask(result)
    selected_latest_date = pd.Timestamp(result.factor_scores[result.selected_factor].index[-1])
    selected_raw_scores = result.factor_scores[result.selected_factor].loc[selected_latest_date].sort_values(ascending=False)
    selected_eligible = _eligibility_row(eligibility_mask, selected_latest_date, selected_raw_scores.index)
    selected_scores = pd.DataFrame(
        {
            "symbol": selected_raw_scores.index,
            "selected_factor_score": selected_raw_scores.values,
            "eligible_for_current_model_portfolio": selected_raw_scores.index.map(selected_eligible).astype("object"),
            "score_scope": selected_raw_scores.index.map(_score_scope(selected_eligible)),
        }
    )
    universe = result.market_data.candidate_universe.copy()
    if "symbol" in universe:
        eligible_universe = getattr(result.market_data, "eligible_universe", pd.DataFrame())
        eligible = set(eligible_universe["symbol"]) if "symbol" in eligible_universe else set()
        universe["eligible_stock_price_symbol"] = universe["symbol"].isin(eligible)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _metadata_frame(result).to_excel(writer, sheet_name="config_assumptions", index=False)
        universe.to_excel(writer, sheet_name="universe", index=False)
        result.data_sources.to_excel(writer, sheet_name="data_sources", index=False)
        result.market_data.price_sources.to_excel(writer, sheet_name="price_sources", index=False)
        result.data_quality.to_excel(writer, sheet_name="data_quality", index=False)
        result.factor_definitions.to_excel(writer, sheet_name="factor_definitions", index=False)
        result.factor_validation.to_excel(writer, sheet_name="factor_validation", index=False)
        result.factor_rank_ic.to_excel(writer, sheet_name="factor_rank_ic", index=False)
        result.factor_redundancy.to_excel(writer, sheet_name="factor_redundancy", index=False)
        result.factor_category_summary.to_excel(writer, sheet_name="factor_category_summary", index=False)
        _status_panel_frame(result).to_excel(writer, sheet_name="status_panel", index=False)
        _factor_family_leaderboard_frame(result).to_excel(writer, sheet_name="factor_family_leaderboard", index=False)
        _factor_overlap_top20_frame(result).to_excel(writer, sheet_name="factor_overlap_top20", index=False)
        _regime_performance_frame(result).to_excel(writer, sheet_name="regime_performance", index=False)
        _tradability_gate_frame(result).to_excel(writer, sheet_name="tradability_gate", index=False)
        result.data_sources.to_excel(writer, sheet_name="universe_provenance", index=False)
        _liquidity_capacity_frame(result).to_excel(writer, sheet_name="liquidity_capacity", index=False)
        result.cost_stress.to_excel(writer, sheet_name="cost_stress", index=False)
        result.selection_history.to_excel(writer, sheet_name="selection_history", index=False)
        _latest_factor_scores_frame(result).to_excel(writer, sheet_name="factor_scores", index=False)
        _factor_history_top_frame(result).to_excel(writer, sheet_name="factor_score_history_top20", index=False)
        selected_scores.to_excel(writer, sheet_name="selected_factor_scores", index=False)
        result.metrics.reset_index(names="factor").to_excel(writer, sheet_name="backtest_metrics", index=False)
        result.score_components.reset_index(names="factor").to_excel(writer, sheet_name="score_components", index=False)
        result.benchmark_relative.to_excel(writer, sheet_name="benchmark_relative", index=False)
        pd.DataFrame([result.metadata]).to_excel(writer, sheet_name="selected_factor", index=False)
        result.recommendations.to_excel(
            writer,
            sheet_name=result.metadata.get("recommendation_output_sheet", "recommendations"),
            index=False,
        )
        result.market_data.exclusions.to_excel(writer, sheet_name="exclusions", index=False)
        result.robustness.to_excel(writer, sheet_name="robustness", index=False)
        result.sensitivity.to_excel(writer, sheet_name="sensitivity", index=False)


def _text_page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(11, 8.5))
    fig.suptitle(title, fontsize=18, fontweight="bold")
    y = 0.90
    for line in lines:
        fig.text(0.06, y, line, fontsize=10, va="top", wrap=True)
        y -= 0.045 + 0.012 * (len(line) // 100)
        if y < 0.08:
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
            fig = plt.figure(figsize=(11, 8.5))
            y = 0.92
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _table_page(pdf: PdfPages, title: str, frame: pd.DataFrame, max_rows: int = 18) -> None:
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis("off")
    ax.set_title(title, fontsize=16, fontweight="bold", pad=12)
    display = frame.head(max_rows).copy()
    if display.empty:
        ax.text(0.5, 0.5, "No rows available", ha="center", va="center")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)
        return
    for col in display.columns:
        if pd.api.types.is_float_dtype(display[col]):
            display[col] = display[col].map(lambda x: f"{x:,.4f}")
    table = ax.table(cellText=display.values, colLabels=display.columns, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.35)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _executive_summary_lines(result: RunResult) -> list[str]:
    selected = result.selected_factor
    limitations = result.metadata.get("execution_limitations", result.metadata.get("tradability_blockers", []))
    limitation_text = ", ".join(limitations) if limitations else "none"
    cash_weight = result.metadata.get("recommendation_cash_weight")
    cash_text = f"{cash_weight:.2%}" if isinstance(cash_weight, int | float) else "unavailable"
    return [
        f"Selected factor: {selected}",
        f"Selection rationale: {result.selected_reason}",
        f"Output status: {result.metadata['recommendation_status']}",
        f"Output type: {result.metadata.get('recommendation_output_label', 'Model-portfolio output rows')}",
        f"Execution limitations: {limitation_text}",
        (
            "Output-row weighting policy: "
            f"{result.metadata.get('recommendation_weighting_method', 'unavailable')} | "
            f"cash remainder: {cash_text} | "
            f"{result.metadata.get('research_signal_weight_policy', 'research-only rows are not tradable')}"
        ),
        f"Liquidity/capacity: {result.metadata.get('recommendation_capacity_warning', 'not reported')}",
        f"Data quality: {result.metadata.get('data_quality_status_counts', {})}",
        f"Recommendation data quality: {result.metadata.get('recommendation_data_quality_status_counts', {})}",
        f"Data source: {result.metadata['provider']} | data as of: {result.metadata['data_as_of']} | run: {result.metadata['run_timestamp_utc']}",
        f"Universe: {result.metadata['candidate_universe_size']} stock candidates; {result.metadata['eligible_price_universe_size']} eligible stock price symbols; {result.metadata['excluded_symbols']} exclusions.",
        f"Benchmark price available: {result.metadata.get('benchmark_price_available')} ({result.metadata.get('benchmark_symbol', result.config.benchmark)}) — benchmark is not an investable candidate.",
        f"Portfolio construction: {result.metadata['portfolio_construction']}",
        f"Benchmark: {result.config.benchmark} | Transaction cost/slippage: {result.config.transaction_cost_bps:.1f} bps + {result.config.slippage_bps:.1f} bps.",
        result.metadata["survivorship_bias_caveat"],
        result.metadata["live_data_gate"],
        result.metadata["non_advice_disclaimer"],
    ]


def write_pdf(result: RunResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    selected = result.selected_factor
    with PdfPages(path) as pdf:
        _text_page(
            pdf,
            "Momentum Factor Lab — Executive Summary",
            _executive_summary_lines(result),
        )
        _table_page(pdf, "Data Sources and Coverage", result.data_sources)
        _table_page(pdf, "Symbol-level Price Sources", result.market_data.price_sources, max_rows=24)
        _table_page(pdf, "Data Quality Diagnostics", result.data_quality, max_rows=32)
        _table_page(pdf, "Practical Output Gate Checklist", _tradability_gate_frame(result))
        _table_page(pdf, "Universe Source / Provenance Dashboard", result.data_sources)
        _table_page(pdf, "Factor Family Leaderboard", _factor_family_leaderboard_frame(result))
        _table_page(pdf, "Factor Overlap / Top-20 Consensus", _factor_overlap_top20_frame(result))
        _table_page(pdf, "Cost Stress Scenarios", result.cost_stress)
        _table_page(pdf, "Factor Definitions", result.factor_definitions[["factor", "category", "formula"]], max_rows=45)
        _table_page(pdf, "Factor Validation Audit", result.factor_validation[["factor", "status", "finite_coverage", "no_lookahead_check"]], max_rows=24)
        metric_cols = ["validation_sharpe", "validation_sortino", "validation_calmar", "validation_max_drawdown", "full_avg_turnover"]
        _table_page(pdf, "Factor Comparison — Validation and Risk Metrics", result.metrics[metric_cols].reset_index(names="factor"))
        benchmark_cols = [
            "factor",
            "benchmark",
            "strategy_cagr",
            "benchmark_cagr",
            "annualized_excess_return",
            "tracking_error",
            "information_ratio",
            "beta_to_benchmark",
        ]
        _table_page(pdf, "Benchmark-relative Metrics", result.benchmark_relative[benchmark_cols])
        _table_page(pdf, "Selected-Factor Score Components", result.score_components.reset_index(names="factor"))
        _table_page(pdf, "Selected-Factor Parameter Sensitivity", result.sensitivity)
        _table_page(
            pdf,
            result.metadata.get("recommendation_output_label", "Top model-portfolio output rows"),
            result.recommendations,
            max_rows=result.config.top_n,
        )
        _table_page(pdf, "Robustness Slices", result.robustness[result.robustness["factor"].eq(selected)])

        fig, ax = plt.subplots(figsize=(11, 6.5))
        for name, bt in result.backtests.items():
            if name == selected or name in result.score_components.head(4).index:
                bt.equity.plot(ax=ax, label=name, linewidth=1.3)
        ax.set_title("Equity Curves — Selected and Top Factors")
        ax.set_ylabel("Growth of $1")
        ax.grid(True, alpha=0.3)
        ax.legend()
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(11, 6.5))
        equity = result.backtests[selected].equity
        drawdown = equity / equity.cummax() - 1.0
        drawdown.plot(ax=ax, color="crimson")
        ax.set_title(f"Drawdown — {selected} (MDD {drawdown.min():.1%})")
        ax.set_ylabel("Drawdown")
        ax.grid(True, alpha=0.3)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def write_reports(result: RunResult) -> RunResult:
    stamp = result.metadata["run_timestamp_utc"].replace(":", "").replace("-", "")[:15]
    result.config.output_dir.mkdir(parents=True, exist_ok=True)
    result.config.report_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = result.config.report_dir / f"momentum_factor_report_{stamp}.pdf"
    xlsx_path = result.config.report_dir / f"momentum_factor_analysis_{stamp}.xlsx"
    json_path = result.config.output_dir / f"run_results_{stamp}.json"
    write_pdf(result, pdf_path)
    write_excel(result, xlsx_path)
    write_run_results_json(result, json_path)
    result.output_paths.update({"pdf": str(pdf_path), "xlsx": str(xlsx_path), "json": str(json_path)})
    return result
