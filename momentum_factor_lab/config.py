from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .universe import DEFAULT_UNIVERSE


@dataclass(slots=True)
class RunConfig:
    start_date: str = "2016-01-01"
    end_date: str | None = None
    rebalance_frequency: str = "ME"
    top_n: int = 20
    max_weight: float = 0.10
    transaction_cost_bps: float = 5.0
    slippage_bps: float = 5.0
    min_history_days: int = 252
    min_avg_dollar_volume: float = 5_000_000.0
    min_avg_volume: float = 0.0
    min_price: float = 5.0
    stale_after_days: int = 7
    benchmark: str = "SPY"
    offline_sample: bool = True
    output_dir: Path = Path("outputs")
    report_dir: Path = Path("reports")
    cache_dir: Path = Path(".cache/momentum_factor_lab")
    max_price_symbols: int | None = None
    price_chunk_size: int = 150
    stooq_fallback_limit: int = 0
    retry_count: int = 1
    retry_backoff_seconds: float = 0.5
    universe_source_mode: str = "packaged"
    selected_factor: str | None = None
    target_aum: float | None = None
    max_adv_participation: float | None = None
    point_in_time_universe_provenance: str | None = None
    approved_tradable_universe: bool = False
    min_tradable_universe_size: int = 2_000
    min_liquidity_observations: int = 63
    universe: list[str] = field(default_factory=lambda: list(DEFAULT_UNIVERSE))

    def validate(self) -> None:
        if self.top_n < 1:
            raise ValueError("top_n must be at least 1")
        if not 0 < self.max_weight <= 1:
            raise ValueError("max_weight must be greater than 0 and no more than 1")
        if self.transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps must be non-negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")
        if self.min_history_days < 1:
            raise ValueError("min_history_days must be at least 1")
        if self.min_avg_dollar_volume < 0:
            raise ValueError("min_avg_dollar_volume must be non-negative")
        if self.min_avg_volume < 0:
            raise ValueError("min_avg_volume must be non-negative")
        if self.min_price < 0:
            raise ValueError("min_price must be non-negative")
        if self.stale_after_days < 0:
            raise ValueError("stale_after_days must be non-negative")
        if self.max_price_symbols is not None and self.max_price_symbols < 1:
            raise ValueError("max_price_symbols must be at least 1 when provided")
        if self.price_chunk_size < 1:
            raise ValueError("price_chunk_size must be at least 1")
        if self.stooq_fallback_limit < 0:
            raise ValueError("stooq_fallback_limit must be non-negative")
        if self.retry_count < 0:
            raise ValueError("retry_count must be non-negative")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        if self.universe_source_mode not in {"packaged", "refresh"}:
            raise ValueError("universe_source_mode must be 'packaged' or 'refresh'")
        if self.selected_factor is not None and not self.selected_factor.strip():
            raise ValueError("selected_factor must be a non-empty factor name when provided")
        if self.target_aum is not None and self.target_aum <= 0:
            raise ValueError("target_aum must be positive when provided")
        if self.max_adv_participation is not None and not 0 < self.max_adv_participation <= 1:
            raise ValueError("max_adv_participation must be in (0, 1] when provided")
        if self.point_in_time_universe_provenance is not None and not self.point_in_time_universe_provenance.strip():
            raise ValueError("point_in_time_universe_provenance must be non-empty when provided")
        if self.min_tradable_universe_size < 1:
            raise ValueError("min_tradable_universe_size must be at least 1")
        if self.min_liquidity_observations < 1:
            raise ValueError("min_liquidity_observations must be at least 1")
        if not self.benchmark.strip():
            raise ValueError("benchmark must be a non-empty symbol")
        try:
            start = datetime.fromisoformat(self.start_date).date()
            end = datetime.fromisoformat(self.effective_end_date).date()
        except ValueError as exc:
            raise ValueError("start_date and end_date must be ISO dates") from exc
        if start > end:
            raise ValueError("start_date must be on or before end_date")

    @property
    def total_cost_rate(self) -> float:
        return (self.transaction_cost_bps + self.slippage_bps) / 10_000.0

    @property
    def effective_end_date(self) -> str:
        return self.end_date or datetime.now(UTC).date().isoformat()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        data["report_dir"] = str(self.report_dir)
        data["cache_dir"] = str(self.cache_dir)
        data["total_cost_rate"] = self.total_cost_rate
        data["candidate_universe_size"] = len(self.universe)
        return data
