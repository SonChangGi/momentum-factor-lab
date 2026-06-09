from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Iterable
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .config import RunConfig
from .universe import (
    SAMPLE_UNIVERSE,
    build_public_universe_frame,
    is_known_etf_symbol,
    normalize_symbol,
    stock_only_universe_frame,
    universe_frame_for_symbols,
)


@dataclass(slots=True)
class MarketData:
    prices: pd.DataFrame
    volumes: pd.DataFrame
    provider: str
    fetched_at: datetime
    as_of: pd.Timestamp | None
    exclusions: pd.DataFrame
    offline_sample: bool
    candidate_universe: pd.DataFrame
    eligible_universe: pd.DataFrame
    price_sources: pd.DataFrame
    data_sources: pd.DataFrame
    live_error: str | None = None
    data_quality: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def is_live(self) -> bool:
        return not self.offline_sample and self.live_error is None


def _business_dates(config: RunConfig) -> pd.DatetimeIndex:
    end = pd.Timestamp(config.end_date or "2025-12-31")
    return pd.bdate_range(config.start_date, end)


def _source_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "source",
        "status",
        "records",
        "candidate_symbols",
        "requested_price_symbols",
        "eligible_price_symbols",
        "excluded_symbols",
        "subset_run",
        "point_in_time_universe",
        "tradable_universe_approved",
        "universe_provenance",
        "cache_path",
        "retries",
        "error",
        "note",
        "benchmark_symbol",
        "benchmark_price_available",
        "requested_download_symbols",
        "requested_symbols",
        "returned_symbols",
        "missing_symbols",
        "as_of_min",
        "as_of_max",
        "cache_hit",
        "provider_adjustment_note",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)
    for col in columns:
        if col not in frame:
            frame[col] = None
    return frame[columns]


def _candidate_universe(config: RunConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    refresh_requested = config.universe_source_mode == "refresh" or config.universe_profile in {
        "extended_current",
        "aggressive_stock_only",
    }
    if refresh_requested and not config.offline_sample:
        result = build_public_universe_frame(
            cache_dir=config.cache_dir / "universe",
            retry_count=config.retry_count,
            retry_backoff_seconds=config.retry_backoff_seconds,
            user_agent=config.sec_user_agent,
        )
        data_sources = result.data_sources.copy()
        data_sources["universe_profile"] = config.universe_profile
        data_sources["universe_source_mode"] = "refresh"
        data_sources["point_in_time_universe"] = False
        data_sources["tradable_universe_approved"] = False
        return result.frame, data_sources
    frame = universe_frame_for_symbols(config.universe)
    source_name = "packaged-default-universe" if len(frame) > len(SAMPLE_UNIVERSE) else "user-supplied-universe"
    status = "loaded"
    note = None
    if refresh_requested and config.offline_sample:
        status = "packaged_fallback_for_offline_profile"
        note = (
            "Offline/sample mode keeps the reproducible packaged stock-only universe; current refresh "
            "profiles need a live run for current recommendations; missing PIT evidence is reported as a limitation."
        )
    return frame, pd.DataFrame(
        [
            {
                "source": source_name,
                "status": status,
                "records": len(frame),
                "candidate_symbols": len(frame),
                "point_in_time_universe": False,
                "tradable_universe_approved": False,
                "universe_provenance": source_name.replace("-", " "),
                "universe_profile": config.universe_profile,
                "universe_source_mode": config.universe_source_mode,
                "cache_path": "package-resource",
                "retries": 0,
                "note": note,
            }
        ]
    )


def _point_in_time_provenance_source(config: RunConfig, candidate: pd.DataFrame) -> pd.DataFrame:
    if config.point_in_time_universe_provenance is None and not config.approved_tradable_universe:
        return _source_frame([])
    provenance = (config.point_in_time_universe_provenance or "").strip()
    return _source_frame(
        [
            {
                "source": "user-point-in-time-universe-provenance",
                "status": "attested" if provenance else "missing_provenance",
                "records": len(candidate),
                "candidate_symbols": len(candidate),
                "point_in_time_universe": bool(provenance),
                "tradable_universe_approved": bool(config.approved_tradable_universe),
                "universe_provenance": provenance,
                "retries": 0,
                "note": (
                    "User-supplied point-in-time/tradable-universe provenance. The lab records this evidence "
                    "for gating but does not independently validate survivorship-free historical membership."
                ),
            }
        ]
    )


def _requested_symbols(config: RunConfig, candidate: pd.DataFrame) -> tuple[list[str], bool]:
    benchmark = normalize_symbol(config.benchmark)
    candidate_symbols = [symbol for symbol in candidate["symbol"].tolist() if symbol != benchmark and not is_known_etf_symbol(symbol)]
    symbols = list(dict.fromkeys([benchmark, *candidate_symbols]))
    if config.max_price_symbols is not None and len(symbols) > config.max_price_symbols:
        keep = [benchmark]
        for symbol in candidate_symbols:
            if symbol not in keep:
                keep.append(symbol)
            if len(keep) >= config.max_price_symbols:
                break
        return keep, True
    return symbols, False


def _price_source_frame(symbols: Iterable[str], source: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": list(symbols),
            "price_source": source,
            "provider_adjustment_note": (
                "Deterministic synthetic adjusted-close sample; not executable market data."
                if source == "deterministic-offline-sample"
                else None
            ),
        }
    )


DATA_QUALITY_COLUMNS = [
    "symbol",
    "role",
    "price_source",
    "provider",
    "first_price_date",
    "last_price_date",
    "observation_count",
    "missing_ratio",
    "volume_missing_ratio",
    "latest_price",
    "volume_obs_count",
    "avg_share_volume_63d",
    "avg_dollar_volume_63d",
    "non_positive_price_observations",
    "max_abs_daily_return",
    "extreme_return_observations",
    "full_history_max_abs_daily_return",
    "full_history_extreme_return_observations",
    "stale_days",
    "exclusion_reason",
    "data_quality_status",
    "data_quality_pass",
    "data_quality_warning",
]


def _exclusion_status(reason: object) -> str:
    text = str(reason or "").strip().lower()
    if not text:
        return "pass"
    if "missing from price" in text:
        return "missing_price"
    if "excessive missing price" in text:
        return "excessive_missing_price"
    if "excessive missing volume" in text:
        return "excessive_missing_volume"
    if "non-positive price" in text:
        return "non_positive_price"
    if "extreme adjusted daily return" in text:
        return "extreme_return_anomaly"
    if "provider adjustment" in text or "provider-adjustment" in text:
        return "provider_adjustment_incompatible"
    if "insufficient price history" in text:
        return "insufficient_history"
    if "stale" in text:
        return "stale_price"
    if "minimum price" in text:
        return "below_minimum_price"
    if "missing volume" in text:
        return "missing_volume"
    if "dollar-volume" in text or "share-volume" in text:
        return "below_liquidity_floor"
    if "benchmark" in text:
        return "insufficient_benchmark_history"
    if "etf" in text:
        return "known_etf_excluded"
    if "not in stock candidate" in text:
        return "not_in_stock_candidate_universe"
    return "excluded"


def _matching_column(frame: pd.DataFrame, symbol: str) -> str | None:
    normalized = normalize_symbol(symbol)
    return next((column for column in frame.columns if normalize_symbol(str(column)) == normalized), None)


def _price_source_map(price_sources: pd.DataFrame) -> dict[str, str]:
    if price_sources.empty or "symbol" not in price_sources or "price_source" not in price_sources:
        return {}
    return {
        normalize_symbol(str(row["symbol"])): str(row["price_source"])
        for _, row in price_sources.dropna(subset=["symbol"]).iterrows()
    }


def build_data_quality_frame(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    requested_symbols: Iterable[str],
    candidate: pd.DataFrame,
    config: RunConfig,
    *,
    provider: str,
    price_sources: pd.DataFrame | None = None,
    exclusions: pd.DataFrame | None = None,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Build auditable per-symbol price/volume quality diagnostics.

    The manifest separates hard price-integrity evidence from advisory
    volume/liquidity/provider-compatibility warnings so broad live runs can keep
    coverage without hiding source quality limitations.
    """

    requested = list(dict.fromkeys(normalize_symbol(symbol) for symbol in requested_symbols))
    if not requested:
        return pd.DataFrame(columns=DATA_QUALITY_COLUMNS)
    prices = prices.sort_index()
    volumes = volumes.reindex(index=prices.index)
    benchmark = normalize_symbol(config.benchmark)
    candidate_symbols = set(candidate["symbol"].map(normalize_symbol)) if "symbol" in candidate else set()
    price_source_frame = price_sources if price_sources is not None else pd.DataFrame()
    source_by_symbol = _price_source_map(price_source_frame)
    exclusions_by_symbol: dict[str, object] = {}
    if exclusions is not None and not exclusions.empty and {"symbol", "reason"}.issubset(exclusions.columns):
        exclusions_by_symbol = {
            normalize_symbol(str(row["symbol"])): row["reason"]
            for _, row in exclusions.dropna(subset=["symbol"]).iterrows()
        }
    data_as_of = pd.Timestamp(as_of).normalize() if as_of is not None else None
    if data_as_of is None and not prices.empty:
        data_as_of = pd.Timestamp(prices.dropna(how="all").index.max()).normalize()

    rows: list[dict[str, object]] = []
    for symbol in requested:
        price_column = _matching_column(prices, symbol)
        volume_column = _matching_column(volumes, symbol)
        price_series = (
            pd.to_numeric(prices[price_column], errors="coerce")
            if price_column is not None
            else pd.Series(index=prices.index, dtype=float)
        )
        volume_series = (
            pd.to_numeric(volumes[volume_column], errors="coerce")
            if volume_column is not None
            else pd.Series(index=prices.index, dtype=float)
        )
        valid_prices = price_series.dropna()
        valid_volumes = volume_series.dropna()
        first_price_date = valid_prices.index.min() if not valid_prices.empty else None
        last_price_date = valid_prices.index.max() if not valid_prices.empty else None
        latest_price = float(valid_prices.iloc[-1]) if not valid_prices.empty else np.nan
        stale_days = (
            (data_as_of - pd.Timestamp(last_price_date).normalize()).days
            if data_as_of is not None and last_price_date is not None
            else np.nan
        )
        quality_prices = price_series.tail(config.data_quality_lookback_days)
        quality_volumes = volume_series.tail(config.data_quality_lookback_days)
        tail_prices = price_series.tail(63)
        tail_volumes = volume_series.tail(63)
        avg_share_volume = float(tail_volumes.mean()) if not tail_volumes.dropna().empty else np.nan
        avg_dollar_volume = (
            float(tail_prices.mul(tail_volumes).mean())
            if not tail_prices.dropna().empty and not tail_volumes.dropna().empty
            else np.nan
        )
        missing_ratio = (
            float(quality_prices.isna().mean())
            if len(quality_prices.index) > 0 and price_column is not None
            else np.nan
        )
        volume_missing_ratio = (
            float(quality_volumes.isna().mean())
            if len(quality_volumes.index) > 0 and volume_column is not None
            else np.nan
        )
        non_positive_prices = int(quality_prices.le(0).fillna(False).sum())
        daily_returns = quality_prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).abs()
        max_abs_daily_return = float(daily_returns.max()) if not daily_returns.dropna().empty else np.nan
        extreme_return_observations = int(
            daily_returns.gt(config.max_extreme_daily_return).fillna(False).sum()
        )
        full_history_returns = price_series.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).abs()
        full_history_max_abs_daily_return = (
            float(full_history_returns.max()) if not full_history_returns.dropna().empty else np.nan
        )
        full_history_extreme_return_observations = int(
            full_history_returns.gt(config.max_extreme_daily_return).fillna(False).sum()
        )
        exclusion_reason = exclusions_by_symbol.get(symbol)
        price_source = source_by_symbol.get(symbol, "unavailable" if price_column is None else provider)
        if symbol == benchmark:
            role = "benchmark"
            status = "benchmark_comparator_only" if len(valid_prices) >= 2 else "insufficient_benchmark_history"
        elif price_column is None or valid_prices.empty:
            role = "missing"
            status = "missing_price"
            exclusion_reason = exclusion_reason or "missing from price providers"
        elif exclusion_reason:
            role = "excluded"
            status = _exclusion_status(exclusion_reason)
        elif symbol not in candidate_symbols or is_known_etf_symbol(symbol):
            role = "excluded"
            exclusion_reason = "not in stock candidate universe"
            status = _exclusion_status(exclusion_reason)
        else:
            role = "candidate"
            status = "pass"
            if pd.notna(stale_days) and int(stale_days) > config.stale_after_days:
                status = "stale_price"
            elif "close-fallback" in price_source:
                status = "provider_adjustment_incompatible"
            elif len(valid_prices) < config.min_history_days:
                status = "insufficient_history"
            elif non_positive_prices > 0:
                status = "non_positive_price"
            elif pd.notna(missing_ratio) and missing_ratio > config.max_price_missing_ratio:
                status = "excessive_missing_price"
            elif pd.isna(latest_price) or latest_price < config.min_price:
                status = "below_minimum_price"
            elif valid_volumes.empty:
                status = "missing_volume"
            elif (
                config.min_avg_dollar_volume > 0 or config.min_avg_volume > 0
            ) and pd.notna(volume_missing_ratio) and volume_missing_ratio > config.max_volume_missing_ratio:
                status = "excessive_missing_volume"
            elif int(tail_volumes.count()) < config.min_liquidity_observations:
                status = "insufficient_liquidity_observations"
            elif config.min_avg_volume > 0 and avg_share_volume < config.min_avg_volume:
                status = "below_liquidity_floor"
            elif config.min_avg_dollar_volume > 0 and avg_dollar_volume < config.discovery_min_avg_dollar_volume:
                status = "below_liquidity_floor"
            elif extreme_return_observations > 0 or full_history_extreme_return_observations > 0:
                status = "extreme_return_anomaly"
            if status != "pass":
                role = "excluded"
                exclusion_reason = exclusion_reason or status

        warning = (
            "pass"
            if status in {"pass", "benchmark_comparator_only"}
            else f"{status}: inspect source data before practical use"
        )

        rows.append(
            {
                "symbol": symbol,
                "role": role,
                "price_source": price_source,
                "provider": provider,
                "first_price_date": first_price_date.date().isoformat() if first_price_date is not None else None,
                "last_price_date": last_price_date.date().isoformat() if last_price_date is not None else None,
                "observation_count": int(valid_prices.count()),
                "missing_ratio": missing_ratio,
                "volume_missing_ratio": volume_missing_ratio,
                "latest_price": latest_price,
                "volume_obs_count": int(valid_volumes.count()),
                "avg_share_volume_63d": avg_share_volume,
                "avg_dollar_volume_63d": avg_dollar_volume,
                "non_positive_price_observations": non_positive_prices,
                "max_abs_daily_return": max_abs_daily_return,
                "extreme_return_observations": extreme_return_observations,
                "full_history_max_abs_daily_return": full_history_max_abs_daily_return,
                "full_history_extreme_return_observations": full_history_extreme_return_observations,
                "stale_days": int(stale_days) if pd.notna(stale_days) else np.nan,
                "exclusion_reason": exclusion_reason,
                "data_quality_status": status,
                "data_quality_pass": status in {"pass", "benchmark_comparator_only"},
                "data_quality_warning": warning,
            }
        )
    return pd.DataFrame(rows, columns=DATA_QUALITY_COLUMNS)


def generate_offline_sample_data(config: RunConfig) -> MarketData:
    candidate, universe_sources = _candidate_universe(config)
    symbols = list(dict.fromkeys([normalize_symbol(config.benchmark), *SAMPLE_UNIVERSE, *config.universe[:8]]))[:24]
    dates = _business_dates(config)
    rng = np.random.default_rng(42)
    common = rng.normal(0.00025, 0.008, len(dates))
    prices: dict[str, np.ndarray] = {}
    volumes: dict[str, np.ndarray] = {}
    for i, symbol in enumerate(symbols):
        style = (i % 6) - 2
        drift = 0.00012 + 0.00004 * style
        vol = 0.011 + 0.0015 * (i % 5)
        seasonal = 0.0008 * np.sin(np.linspace(0, 10 + i / 3, len(dates)))
        shock = rng.normal(drift, vol, len(dates)) + 0.35 * common + seasonal
        if symbol in {"NVDA", "MSFT", "AAPL", "AVGO", "TSLA"}:
            shock += np.linspace(-0.0001, 0.00045, len(dates))
        if symbol in {"JPM", "XOM"}:
            shock += 0.00015 * np.sin(np.linspace(0, 22, len(dates)))
        series = 80 * np.exp(np.cumsum(shock))
        prices[symbol] = np.maximum(series, 1.0)
        volumes[symbol] = rng.integers(1_000_000, 25_000_000, len(dates)) * (1 + i / 25)
    price_df = pd.DataFrame(prices, index=dates).round(4)
    volume_df = pd.DataFrame(volumes, index=dates).round(0)
    exclusions = pd.DataFrame(columns=["symbol", "reason"])
    candidate_symbol_set = set(candidate["symbol"])
    eligible_symbols = [symbol for symbol in symbols if symbol in candidate_symbol_set]
    eligible = stock_only_universe_frame(candidate[candidate["symbol"].isin(eligible_symbols)])
    price_sources = _price_source_frame(symbols, "deterministic-offline-sample")
    data_quality = build_data_quality_frame(
        price_df,
        volume_df,
        symbols,
        candidate,
        config,
        provider="deterministic-offline-sample",
        price_sources=price_sources,
        exclusions=exclusions,
        as_of=price_df.index.max(),
    )
    data_sources = pd.concat(
        [
            universe_sources,
            _source_frame(
                [
                    {
                        "source": "deterministic-offline-sample",
                        "status": "generated",
                        "records": len(symbols),
                        "candidate_symbols": len(candidate),
                        "requested_price_symbols": len(eligible_symbols),
                        "eligible_price_symbols": len(eligible_symbols),
                        "requested_download_symbols": len(symbols),
                        "requested_symbols": ",".join(symbols),
                        "returned_symbols": ",".join(price_df.columns),
                        "missing_symbols": "",
                        "as_of_min": str(price_df.dropna(how="all").index.min().date()),
                        "as_of_max": str(price_df.dropna(how="all").index.max().date()),
                        "cache_hit": False,
                        "benchmark_symbol": normalize_symbol(config.benchmark),
                        "benchmark_price_available": normalize_symbol(config.benchmark) in price_df.columns,
                        "excluded_symbols": 0,
                        "subset_run": True,
                        "point_in_time_universe": False,
                        "tradable_universe_approved": False,
                        "provider_adjustment_note": "Synthetic adjusted-close sample for deterministic CI/reporting only.",
                        "note": "Offline CI/sample mode uses deterministic synthetic prices while preserving broad candidate-universe metadata.",
                    }
                ]
            ),
            _point_in_time_provenance_source(config, candidate),
        ],
        ignore_index=True,
    )
    return MarketData(
        prices=price_df,
        volumes=volume_df,
        provider="deterministic-offline-sample",
        fetched_at=datetime.now(UTC),
        as_of=price_df.index.max(),
        exclusions=exclusions,
        offline_sample=True,
        candidate_universe=candidate,
        eligible_universe=eligible,
        price_sources=price_sources,
        data_sources=data_sources,
        data_quality=data_quality,
    )


def _extract_yfinance(download: pd.DataFrame, symbols: Iterable[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if download.empty:
        return pd.DataFrame(), pd.DataFrame()
    symbols = list(symbols)
    if isinstance(download.columns, pd.MultiIndex):
        lvl0 = set(map(str, download.columns.get_level_values(0)))
        if "Close" in lvl0 or "Adj Close" in lvl0:
            close_key = "Close" if "Close" in lvl0 else "Adj Close"
            prices = download[close_key].copy()
            volumes = download["Volume"].copy() if "Volume" in lvl0 else pd.DataFrame(index=prices.index)
        else:
            price_cols = {}
            volume_cols = {}
            for symbol in symbols:
                if symbol in download.columns.get_level_values(0):
                    sub = download[symbol]
                    if "Adj Close" in sub:
                        price_cols[symbol] = sub["Adj Close"]
                    elif "Close" in sub:
                        price_cols[symbol] = sub["Close"]
                    if "Volume" in sub:
                        volume_cols[symbol] = sub["Volume"]
            prices = pd.DataFrame(price_cols)
            volumes = pd.DataFrame(volume_cols)
    else:
        prices = pd.DataFrame({symbols[0]: download.get("Adj Close", download.get("Close"))})
        volumes = pd.DataFrame({symbols[0]: download.get("Volume")})
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    volumes.index = pd.to_datetime(volumes.index).tz_localize(None)
    return prices.dropna(axis=1, how="all"), volumes.reindex(columns=prices.columns)


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _price_cache_path(config: RunConfig, provider: str, symbols: list[str]) -> Path:
    key = json.dumps(
        {
            "provider": provider,
            "symbols": symbols,
            "start_date": config.start_date,
            "end_date": config.effective_end_date,
            "download_end_date": (
                _yfinance_download_end_date(config)
                if provider == "yfinance"
                else config.effective_end_date
            ),
            "auto_adjust": True,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return config.cache_dir / "prices" / f"{provider}_{digest}.json"


def _price_cache_component_paths(metadata_path: Path) -> dict[str, Path]:
    return {
        "metadata": metadata_path,
        "prices": metadata_path.with_suffix(".prices.csv"),
        "volumes": metadata_path.with_suffix(".volumes.csv"),
    }


def _read_price_cache(metadata_path: Path) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    paths = _price_cache_component_paths(metadata_path)
    if not all(path.exists() for path in paths.values()):
        return None
    try:
        metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        prices = pd.read_csv(paths["prices"], index_col=0, parse_dates=True)
        volumes = pd.read_csv(paths["volumes"], index_col=0, parse_dates=True)
        symbols = [str(symbol) for symbol in metadata.get("symbols", prices.columns.tolist())]
        prices = prices.reindex(columns=symbols)
        volumes = volumes.reindex(index=prices.index, columns=symbols)
    except Exception:
        return None
    return prices, volumes


def _write_price_cache(metadata_path: Path, prices: pd.DataFrame, volumes: pd.DataFrame, *, provider: str, symbols: list[str]) -> None:
    paths = _price_cache_component_paths(metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "version": 1,
        "provider": provider,
        "symbols": symbols,
        "price_file": paths["prices"].name,
        "volume_file": paths["volumes"].name,
        "format": "csv+json",
        "created_at_utc": datetime.now(UTC).isoformat(),
    }
    paths["metadata"].write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    prices.to_csv(paths["prices"])
    volumes.reindex(index=prices.index, columns=prices.columns).to_csv(paths["volumes"])


def _yfinance_download_end_date(config: RunConfig) -> str | None:
    """Return the yfinance `end` argument for an inclusive user end date.

    yfinance treats `end` as an exclusive bound. The lab's CLI/config dates are
    user-facing analysis dates, and the offline/Stooq/FinanceDataReader paths
    already treat an explicit `end_date` as inclusive. Add one calendar day only
    for explicit yfinance downloads so `--end-date 2026-06-08` can include the
    2026-06-08 trading session when the provider has it available.
    """

    if config.end_date is None:
        return None
    return (pd.Timestamp(config.end_date).date() + timedelta(days=1)).isoformat()


def _stooq_cache_path(config: RunConfig, symbol: str) -> Path:
    safe = symbol.replace("/", "_").replace("-", "_")
    return config.cache_dir / "prices" / "stooq" / f"{safe}_{config.start_date}_{config.effective_end_date}.csv"


def _finance_datareader_cache_path(config: RunConfig, symbol: str) -> Path:
    safe = symbol.replace("/", "_").replace("-", "_")
    return config.cache_dir / "prices" / "finance_datareader" / f"{safe}_{config.start_date}_{config.effective_end_date}.csv"


def _download_yfinance_chunk(symbols: list[str], config: RunConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    cache_path = _price_cache_path(config, "yfinance", symbols)
    cached = _read_price_cache(cache_path)
    if cached is not None:
        prices, volumes = cached
        return prices, volumes, {
            "status": "cache_hit",
            "retries": 0,
            "error": None,
            "cache_path": str(cache_path),
            "cache_format": "csv+json",
        }

    import yfinance as yf  # type: ignore

    last_error = None
    for attempt in range(config.retry_count + 1):
        try:
            raw = yf.download(
                tickers=symbols,
                start=config.start_date,
                end=_yfinance_download_end_date(config),
                auto_adjust=True,
                group_by="column",
                progress=False,
                threads=True,
            )
            prices, volumes = _extract_yfinance(raw, symbols)
            _write_price_cache(cache_path, prices, volumes, provider="yfinance", symbols=symbols)
            return prices, volumes, {
                "status": "fetched",
                "retries": attempt,
                "error": None,
                "cache_path": str(cache_path),
                "cache_format": "csv+json",
            }
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt < config.retry_count:
                time.sleep(config.retry_backoff_seconds)
    return pd.DataFrame(), pd.DataFrame(), {
        "status": "failed",
        "retries": config.retry_count,
        "error": str(last_error),
        "cache_path": str(cache_path),
        "cache_format": "csv+json",
    }


def _download_yfinance(symbols: list[str], config: RunConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    price_frames: list[pd.DataFrame] = []
    volume_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    for chunk in _chunks(symbols, config.price_chunk_size):
        prices, volumes, status = _download_yfinance_chunk(chunk, config)
        price_frames.append(prices)
        volume_frames.append(volumes)
        returned = [symbol for symbol in chunk if symbol in prices.columns]
        missing = [symbol for symbol in chunk if symbol not in prices.columns]
        rows.append(
            {
                "source": "yfinance-adjusted-daily",
                "status": status["status"],
                "records": len(prices.columns),
                "requested_price_symbols": len(chunk),
                "requested_symbols": ",".join(chunk),
                "returned_symbols": ",".join(returned),
                "missing_symbols": ",".join(missing),
                "as_of_min": (
                    str(prices.dropna(how="all").index.min().date()) if not prices.empty else None
                ),
                "as_of_max": (
                    str(prices.dropna(how="all").index.max().date()) if not prices.empty else None
                ),
                "cache_hit": status["status"] == "cache_hit",
                "cache_path": status.get("cache_path"),
                "retries": status["retries"],
                "error": status["error"],
                "provider_adjustment_note": "yfinance auto_adjust=True daily close series.",
            }
        )
    prices = pd.concat(price_frames, axis=1) if price_frames else pd.DataFrame()
    volumes = pd.concat(volume_frames, axis=1) if volume_frames else pd.DataFrame(index=prices.index)
    prices = prices.loc[:, ~prices.columns.duplicated()].sort_index()
    volumes = volumes.loc[:, ~volumes.columns.duplicated()].reindex(index=prices.index, columns=prices.columns)
    return prices, volumes, pd.DataFrame(rows)


def _stooq_symbol(symbol: str) -> str:
    return quote(symbol.lower().replace("-", ".") + ".us")


def _download_stooq_symbol(
    symbol: str,
    config: RunConfig,
) -> tuple[pd.Series | None, pd.Series | None, str | None, str, str, int]:
    cache_path = _stooq_cache_path(config, symbol)
    if cache_path.exists():
        frame = pd.read_csv(cache_path)
        if frame.empty or "Date" not in frame or "Close" not in frame:
            return None, None, "empty stooq cache", "cache_hit_invalid", str(cache_path), 0
        frame["Date"] = pd.to_datetime(frame["Date"])
        frame = frame.set_index("Date").sort_index()
        return (
            frame["Close"].rename(symbol),
            frame.get("Volume", pd.Series(index=frame.index, dtype=float)).rename(symbol),
            None,
            "cache_hit",
            str(cache_path),
            0,
        )

    start = config.start_date.replace("-", "")
    end = config.effective_end_date.replace("-", "")
    url = f"https://stooq.com/q/d/l/?s={_stooq_symbol(symbol)}&d1={start}&d2={end}&i=d"
    last_error = None
    for attempt in range(config.retry_count + 1):
        try:
            with urlopen(Request(url, headers={"User-Agent": "momentum-factor-lab/0.1"}), timeout=20) as response:
                text = response.read().decode("utf-8", errors="replace")
            frame = pd.read_csv(StringIO(text))
            if frame.empty or "Date" not in frame or "Close" not in frame:
                return None, None, "empty stooq response", "failed", str(cache_path), attempt
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(cache_path, index=False)
            frame["Date"] = pd.to_datetime(frame["Date"])
            frame = frame.set_index("Date").sort_index()
            return (
                frame["Close"].rename(symbol),
                frame.get("Volume", pd.Series(index=frame.index, dtype=float)).rename(symbol),
                None,
                "fetched",
                str(cache_path),
                attempt,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt < config.retry_count:
                time.sleep(config.retry_backoff_seconds)
    return None, None, str(last_error), "failed", str(cache_path), config.retry_count


def _apply_stooq_fallback(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    symbols: list[str],
    config: RunConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    missing_all = [symbol for symbol in symbols if symbol not in prices.columns]
    limit = len(missing_all) if config.stooq_fallback_limit is None else config.stooq_fallback_limit
    missing = missing_all[:limit]
    rows = []
    for symbol in missing:
        price, volume, error, status, cache_path, retries = _download_stooq_symbol(symbol, config)
        if price is None:
            rows.append(
                {
                    "source": "stooq-daily-close-fallback",
                    "symbol": symbol,
                    "status": "failed" if not status.startswith("cache") else status,
                    "records": 0,
                    "requested_price_symbols": 1,
                    "requested_symbols": symbol,
                    "returned_symbols": "",
                    "missing_symbols": symbol,
                    "cache_hit": status.startswith("cache"),
                    "cache_path": cache_path,
                    "retries": retries,
                    "error": error,
                    "provider_adjustment_note": "Stooq fallback returned no usable close series.",
                    "note": symbol,
                }
            )
            continue
        prices = prices.join(price, how="outer")
        volumes = volumes.join(volume, how="outer")
        rows.append(
            {
                "source": "stooq-daily-close-fallback",
                "symbol": symbol,
                "status": status,
                "records": 1,
                "requested_price_symbols": 1,
                "requested_symbols": symbol,
                "returned_symbols": symbol,
                "missing_symbols": "",
                "as_of_min": str(price.dropna().index.min().date()) if not price.dropna().empty else None,
                "as_of_max": str(price.dropna().index.max().date()) if not price.dropna().empty else None,
                "cache_hit": status == "cache_hit",
                "cache_path": cache_path,
                "retries": retries,
                "error": None,
                "provider_adjustment_note": "Stooq close-price fallback; adjusted-price compatibility may differ from yfinance.",
                "note": f"{symbol}; close-price compatibility may differ from yfinance auto-adjusted prices",
            }
        )
    return prices.sort_index(), volumes.reindex(index=prices.sort_index().index), pd.DataFrame(rows)


def _download_finance_datareader_symbol(
    symbol: str,
    config: RunConfig,
) -> tuple[pd.Series | None, pd.Series | None, str | None, str, str, int]:
    cache_path = _finance_datareader_cache_path(config, symbol)
    if cache_path.exists():
        frame = pd.read_csv(cache_path)
        if frame.empty or "Date" not in frame or "Close" not in frame:
            return None, None, "empty FinanceDataReader cache", "cache_hit_invalid", str(cache_path), 0
        frame["Date"] = pd.to_datetime(frame["Date"])
        frame = frame.set_index("Date").sort_index()
        return (
            frame["Close"].rename(symbol),
            frame.get("Volume", pd.Series(index=frame.index, dtype=float)).rename(symbol),
            None,
            "cache_hit",
            str(cache_path),
            0,
        )

    try:
        import FinanceDataReader as fdr  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        return None, None, f"FinanceDataReader unavailable: {exc}", "unavailable", str(cache_path), 0

    last_error = None
    for attempt in range(config.retry_count + 1):
        try:
            frame = fdr.DataReader(symbol, config.start_date, config.effective_end_date)
            if frame is None or frame.empty or "Close" not in frame:
                return None, None, "empty FinanceDataReader response", "failed", str(cache_path), attempt
            frame = frame.copy()
            frame.index = pd.to_datetime(frame.index).tz_localize(None)
            export = frame.reset_index().rename(columns={frame.index.name or "index": "Date"})
            if "Date" not in export.columns:
                export = export.rename(columns={export.columns[0]: "Date"})
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            export.to_csv(cache_path, index=False)
            return (
                pd.to_numeric(frame["Close"], errors="coerce").rename(symbol),
                pd.to_numeric(frame.get("Volume", pd.Series(index=frame.index, dtype=float)), errors="coerce").rename(symbol),
                None,
                "fetched",
                str(cache_path),
                attempt,
            )
        except Exception as exc:  # pragma: no cover - network/provider dependent
            last_error = exc
            if attempt < config.retry_count:
                time.sleep(config.retry_backoff_seconds)
    return None, None, str(last_error), "failed", str(cache_path), config.retry_count


def _apply_finance_datareader_fallback(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    symbols: list[str],
    config: RunConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    missing_all = [symbol for symbol in symbols if symbol not in prices.columns]
    limit = len(missing_all) if config.finance_datareader_fallback_limit is None else config.finance_datareader_fallback_limit
    missing = missing_all[:limit]
    rows = []
    for symbol in missing:
        price, volume, error, status, cache_path, retries = _download_finance_datareader_symbol(symbol, config)
        if price is None:
            rows.append(
                {
                    "source": "finance-datareader-close-fallback",
                    "symbol": symbol,
                    "status": status,
                    "records": 0,
                    "requested_price_symbols": 1,
                    "requested_symbols": symbol,
                    "returned_symbols": "",
                    "missing_symbols": symbol,
                    "cache_hit": status.startswith("cache"),
                    "cache_path": cache_path,
                    "retries": retries,
                    "error": error,
                    "provider_adjustment_note": "FinanceDataReader fallback returned no usable close series.",
                    "note": symbol,
                }
            )
            continue
        prices = prices.join(price, how="outer")
        volumes = volumes.join(volume, how="outer")
        rows.append(
            {
                "source": "finance-datareader-close-fallback",
                "symbol": symbol,
                "status": status,
                "records": 1,
                "requested_price_symbols": 1,
                "requested_symbols": symbol,
                "returned_symbols": symbol,
                "missing_symbols": "",
                "as_of_min": str(price.dropna().index.min().date()) if not price.dropna().empty else None,
                "as_of_max": str(price.dropna().index.max().date()) if not price.dropna().empty else None,
                "cache_hit": status == "cache_hit",
                "cache_path": cache_path,
                "retries": retries,
                "error": None,
                "provider_adjustment_note": "FinanceDataReader close fallback; adjusted-price compatibility may differ from yfinance.",
                "note": f"{symbol}; close-price compatibility may differ from yfinance auto-adjusted prices",
            }
        )
    return prices.sort_index(), volumes.reindex(index=prices.sort_index().index), pd.DataFrame(rows)


def build_eligibility_mask(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    config: RunConfig,
    *,
    liquidity_window: int = 63,
) -> pd.DataFrame:
    prices = prices.sort_index()
    volumes = volumes.reindex(index=prices.index, columns=prices.columns)
    price_observations = prices.notna().rolling(config.min_history_days, min_periods=1).sum()
    history_ok = price_observations >= config.min_history_days
    price_ok = prices >= config.min_price
    fresh_ok = prices.notna()
    dollar_volume = prices.mul(volumes)
    price_liquidity_obs = prices.notna().rolling(liquidity_window, min_periods=1).sum()
    share_liquidity_obs = volumes.notna().rolling(liquidity_window, min_periods=1).sum()
    dollar_liquidity_obs = dollar_volume.notna().rolling(liquidity_window, min_periods=1).sum()
    liquidity_observations_ok = (
        (price_liquidity_obs >= config.min_liquidity_observations)
        & (share_liquidity_obs >= config.min_liquidity_observations)
        & (dollar_liquidity_obs >= config.min_liquidity_observations)
    )
    avg_share_volume = volumes.rolling(liquidity_window, min_periods=1).mean()
    avg_dollar_volume = dollar_volume.rolling(liquidity_window, min_periods=1).mean()
    share_volume_ok = pd.DataFrame(True, index=prices.index, columns=prices.columns)
    if config.min_avg_volume > 0:
        share_volume_ok = avg_share_volume >= config.min_avg_volume
    dollar_volume_ok = pd.DataFrame(True, index=prices.index, columns=prices.columns)
    if config.min_avg_dollar_volume > 0:
        dollar_volume_ok = avg_dollar_volume >= config.min_avg_dollar_volume
    mask = history_ok & price_ok & fresh_ok & liquidity_observations_ok & share_volume_ok & dollar_volume_ok
    return mask.fillna(False).astype(bool)


def _eligible_filter(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    candidate: pd.DataFrame,
    config: RunConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    exclusions: list[dict[str, object]] = []
    keep: list[str] = []
    candidate_symbols = set(candidate["symbol"].map(normalize_symbol)) if "symbol" in candidate else set()
    benchmark = normalize_symbol(config.benchmark)
    as_of = prices.dropna(how="all").index.max() if not prices.empty else None
    for raw_symbol in prices.columns:
        symbol = normalize_symbol(raw_symbol)
        is_benchmark = symbol == benchmark
        is_candidate = symbol in candidate_symbols
        if not is_benchmark and not is_candidate:
            exclusions.append({"symbol": symbol, "reason": "not in stock candidate universe", "observed": np.nan})
            continue
        if is_candidate and is_known_etf_symbol(symbol):
            exclusions.append({"symbol": symbol, "reason": "known ETF excluded from stock-only universe", "observed": np.nan})
            continue
        series = prices[raw_symbol].dropna()
        if is_benchmark:
            if len(series) < 2:
                exclusions.append({"symbol": symbol, "reason": "insufficient benchmark price history", "observed": len(series)})
                continue
            keep.append(raw_symbol)
            continue
        if series.empty:
            exclusions.append({"symbol": symbol, "reason": "missing from price providers", "observed": np.nan})
            continue
        latest_date = series.index.max()
        if as_of is not None and (pd.Timestamp(as_of).normalize() - pd.Timestamp(latest_date).normalize()).days > config.stale_after_days:
            exclusions.append({"symbol": symbol, "reason": "stale symbol price", "observed": str(latest_date.date())})
            continue
        if len(series) < config.min_history_days:
            exclusions.append({"symbol": symbol, "reason": "insufficient price history", "observed": len(series)})
            continue
        recent_prices = prices[raw_symbol].tail(config.data_quality_lookback_days)
        non_positive_prices = int(recent_prices.le(0).fillna(False).sum())
        if non_positive_prices > 0:
            exclusions.append(
                {
                    "symbol": symbol,
                    "reason": "non-positive price observations",
                    "observed": non_positive_prices,
                }
            )
            continue
        missing_price_ratio = float(recent_prices.isna().mean()) if len(recent_prices.index) > 0 else 1.0
        if missing_price_ratio > config.max_price_missing_ratio:
            exclusions.append(
                {
                    "symbol": symbol,
                    "reason": "excessive missing price data",
                    "observed": missing_price_ratio,
                }
            )
            continue
        recent_returns = recent_prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).abs()
        extreme_returns = int(recent_returns.gt(config.max_extreme_daily_return).fillna(False).sum())
        full_history_returns = prices[raw_symbol].pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).abs()
        full_history_extreme_returns = int(full_history_returns.gt(config.max_extreme_daily_return).fillna(False).sum())
        if extreme_returns > 0 or full_history_extreme_returns > 0:
            exclusions.append(
                {
                    "symbol": symbol,
                    "reason": "extreme adjusted daily return anomaly",
                    "observed": extreme_returns or full_history_extreme_returns,
                }
            )
            continue
        latest_price = float(series.iloc[-1])
        if latest_price < config.min_price:
            exclusions.append({"symbol": symbol, "reason": "below minimum price", "observed": latest_price})
            continue
        keep.append(raw_symbol)
    for symbol in candidate["symbol"]:
        if symbol not in prices.columns:
            exclusions.append({"symbol": symbol, "reason": "missing from price providers", "observed": np.nan})
    keep = list(dict.fromkeys(keep))
    price_keep = prices[keep].dropna(how="all") if keep else pd.DataFrame(index=prices.index)
    volume_keep = volumes.reindex(index=price_keep.index, columns=keep)
    eligible_symbols = [
        symbol
        for symbol in keep
        if normalize_symbol(symbol) in candidate_symbols and normalize_symbol(symbol) != benchmark
    ]
    normalized_eligible = {normalize_symbol(symbol) for symbol in eligible_symbols}
    eligible = stock_only_universe_frame(candidate[candidate["symbol"].map(normalize_symbol).isin(normalized_eligible)])
    exclusions_df = pd.DataFrame(exclusions, columns=["symbol", "reason", "observed"])
    return price_keep, volume_keep, eligible, exclusions_df


def _provider_label_from_sources(stooq_sources: pd.DataFrame, finance_datareader_sources: pd.DataFrame | None = None) -> str:
    provider = "yfinance-free-public-data"
    records = stooq_sources.get("records", pd.Series(dtype=float)) if not stooq_sources.empty else pd.Series(dtype=float)
    if not stooq_sources.empty and records.fillna(0).astype(int).gt(0).any():
        provider += "+stooq-fallback"
    fdr = finance_datareader_sources if finance_datareader_sources is not None else pd.DataFrame()
    fdr_records = fdr.get("records", pd.Series(dtype=float)) if not fdr.empty else pd.Series(dtype=float)
    if not fdr.empty and fdr_records.fillna(0).astype(int).gt(0).any():
        provider += "+finance-datareader-fallback"
    return provider


def download_live_data(config: RunConfig) -> MarketData:
    fetched_at = datetime.now(UTC)
    candidate, universe_sources = _candidate_universe(config)
    symbols, subset_run = _requested_symbols(config, candidate)
    try:
        import yfinance  # noqa: F401  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional extra
        sample = generate_offline_sample_data(config)
        sample.live_error = f"yfinance unavailable: {exc}"
        return sample

    try:
        prices, volumes, yf_sources = _download_yfinance(symbols, config)
        if config.stooq_fallback_limit != 0:
            prices, volumes, stooq_sources = _apply_stooq_fallback(prices, volumes, symbols, config)
        else:
            stooq_sources = pd.DataFrame()
        if config.finance_datareader_fallback_limit != 0:
            prices, volumes, finance_datareader_sources = _apply_finance_datareader_fallback(prices, volumes, symbols, config)
        else:
            finance_datareader_sources = pd.DataFrame()
    except Exception as exc:  # pragma: no cover - network dependent
        sample = generate_offline_sample_data(config)
        sample.live_error = f"live download failed: {exc}"
        return sample

    if prices.empty:
        sample = generate_offline_sample_data(config)
        sample.live_error = "live download returned no prices"
        return sample

    benchmark = normalize_symbol(config.benchmark)
    requested_candidate_symbols = [symbol for symbol in symbols if symbol != benchmark and symbol in set(candidate["symbol"])]
    downloaded_prices = prices.copy()
    downloaded_volumes = volumes.copy()
    prices, volumes, eligible, exclusions = _eligible_filter(prices, volumes, candidate[candidate["symbol"].isin(requested_candidate_symbols)], config)
    stooq_symbols = set()
    if not stooq_sources.empty and "symbol" in stooq_sources:
        stooq_symbols = set(stooq_sources.loc[stooq_sources["records"].fillna(0).astype(int).gt(0), "symbol"].astype(str))
    finance_datareader_symbols = set()
    if not finance_datareader_sources.empty and "symbol" in finance_datareader_sources:
        finance_datareader_symbols = set(
            finance_datareader_sources.loc[
                finance_datareader_sources["records"].fillna(0).astype(int).gt(0),
                "symbol",
            ].astype(str)
        )
    price_source_rows = []
    for symbol in downloaded_prices.columns:
        if symbol in stooq_symbols:
            source = "stooq-daily-close-fallback"
            note = "Stooq close-price fallback; adjusted-price compatibility may differ from yfinance."
        elif symbol in finance_datareader_symbols:
            source = "finance-datareader-close-fallback"
            note = "FinanceDataReader close fallback; adjusted-price compatibility may differ from yfinance."
        else:
            source = "yfinance-adjusted-daily"
            note = "yfinance auto_adjust=True daily close series."
        price_source_rows.append(
            {
                "symbol": symbol,
                "price_source": source,
                "adjustment_note": note,
                "provider_adjustment_note": note,
            }
        )
    price_sources = pd.DataFrame(price_source_rows)
    as_of = prices.dropna(how="all").index.max() if not prices.empty else None
    data_quality = build_data_quality_frame(
        downloaded_prices,
        downloaded_volumes,
        symbols,
        candidate,
        config,
        provider=_provider_label_from_sources(stooq_sources, finance_datareader_sources),
        price_sources=price_sources,
        exclusions=exclusions,
        as_of=downloaded_prices.dropna(how="all").index.max() if not downloaded_prices.empty else None,
    )
    provider = _provider_label_from_sources(stooq_sources, finance_datareader_sources)
    returned_symbols = [symbol for symbol in symbols if symbol in downloaded_prices.columns]
    missing_symbols = [symbol for symbol in symbols if symbol not in downloaded_prices.columns]
    summary = _source_frame(
        [
            {
                "source": "live-run-summary",
                "status": "partial_subset" if subset_run else "full_requested_universe",
                "records": len(prices.columns),
                "candidate_symbols": len(candidate),
                "requested_price_symbols": len(requested_candidate_symbols),
                "eligible_price_symbols": len(eligible),
                "requested_download_symbols": len(symbols),
                "requested_symbols": ",".join(requested_candidate_symbols),
                "returned_symbols": ",".join(symbol for symbol in returned_symbols if symbol != benchmark),
                "missing_symbols": ",".join(symbol for symbol in missing_symbols if symbol != benchmark),
                "as_of_min": (
                    str(downloaded_prices.dropna(how="all").index.min().date())
                    if not downloaded_prices.empty
                    else None
                ),
                "as_of_max": (
                    str(downloaded_prices.dropna(how="all").index.max().date())
                    if not downloaded_prices.empty
                    else None
                ),
                "cache_hit": bool(
                    not yf_sources.empty
                    and "cache_hit" in yf_sources
                    and yf_sources["cache_hit"].fillna(False).astype(bool).all()
                ),
                "benchmark_symbol": benchmark,
                "benchmark_price_available": benchmark in prices.columns,
                "excluded_symbols": len(exclusions),
                "subset_run": subset_run,
                "point_in_time_universe": False,
                "tradable_universe_approved": False,
                "provider_adjustment_note": (
                    "yfinance auto_adjust=True; Stooq and FinanceDataReader close fallback rows are separately labeled when used."
                ),
                "note": (
                    "Model-portfolio outputs are based only on eligible stock candidate price symbols after history, "
                    "liquidity, and freshness filters; benchmark prices are retained only for comparison; practical execution limitations are exported "
                    "as advisory metadata alongside the ranked recommendations."
                ),
            }
        ]
    )
    data_sources = pd.concat(
        [
            universe_sources,
            yf_sources,
            stooq_sources,
            finance_datareader_sources,
            summary,
            _point_in_time_provenance_source(config, candidate),
        ],
        ignore_index=True,
    )
    return MarketData(
        prices=prices,
        volumes=volumes,
        provider=provider,
        fetched_at=fetched_at,
        as_of=as_of,
        exclusions=exclusions,
        offline_sample=False,
        candidate_universe=candidate,
        eligible_universe=eligible,
        price_sources=price_sources,
        data_sources=data_sources,
        data_quality=data_quality,
    )


def load_market_data(config: RunConfig) -> MarketData:
    if config.offline_sample:
        return generate_offline_sample_data(config)
    return download_live_data(config)
