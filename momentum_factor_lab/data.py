from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
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
        "cache_path",
        "retries",
        "error",
        "note",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)
    for col in columns:
        if col not in frame:
            frame[col] = None
    return frame[columns]


def _candidate_universe(config: RunConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    if config.universe_source_mode == "refresh" and not config.offline_sample:
        result = build_public_universe_frame(
            cache_dir=config.cache_dir / "universe",
            retry_count=config.retry_count,
            retry_backoff_seconds=config.retry_backoff_seconds,
        )
        return result.frame, result.data_sources
    frame = universe_frame_for_symbols(config.universe)
    return frame, pd.DataFrame(
        [
            {
                "source": "packaged-default-universe" if len(frame) > len(SAMPLE_UNIVERSE) else "user-supplied-universe",
                "status": "loaded",
                "records": len(frame),
                "cache_path": "package-resource",
                "retries": 0,
            }
        ]
    )


def _requested_symbols(config: RunConfig, candidate: pd.DataFrame) -> tuple[list[str], bool]:
    symbols = list(dict.fromkeys([config.benchmark, *candidate["symbol"].tolist()]))
    if config.max_price_symbols is not None and len(symbols) > config.max_price_symbols:
        keep = [config.benchmark]
        for symbol in symbols:
            if symbol not in keep:
                keep.append(symbol)
            if len(keep) >= config.max_price_symbols:
                break
        return keep, True
    return symbols, False


def _price_source_frame(symbols: Iterable[str], source: str) -> pd.DataFrame:
    return pd.DataFrame({"symbol": list(symbols), "price_source": source})


def generate_offline_sample_data(config: RunConfig) -> MarketData:
    candidate, universe_sources = _candidate_universe(config)
    symbols = list(dict.fromkeys([config.benchmark, *SAMPLE_UNIVERSE, *config.universe[:8]]))[:24]
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
        if symbol in {"NVDA", "MSFT", "AAPL", "QQQ", "XLK"}:
            shock += np.linspace(-0.0001, 0.00045, len(dates))
        if symbol in {"IWM", "XLF"}:
            shock += 0.00015 * np.sin(np.linspace(0, 22, len(dates)))
        series = 80 * np.exp(np.cumsum(shock))
        prices[symbol] = np.maximum(series, 1.0)
        volumes[symbol] = rng.integers(1_000_000, 25_000_000, len(dates)) * (1 + i / 25)
    price_df = pd.DataFrame(prices, index=dates).round(4)
    volume_df = pd.DataFrame(volumes, index=dates).round(0)
    exclusions = pd.DataFrame(columns=["symbol", "reason"])
    eligible = universe_frame_for_symbols(symbols)
    price_sources = _price_source_frame(symbols, "deterministic-offline-sample")
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
                        "requested_price_symbols": len(symbols),
                        "eligible_price_symbols": len(symbols),
                        "excluded_symbols": 0,
                        "subset_run": True,
                        "note": "Offline CI/sample mode uses deterministic synthetic prices while preserving broad candidate-universe metadata.",
                    }
                ]
            ),
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
            "auto_adjust": True,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return config.cache_dir / "prices" / f"{provider}_{digest}.pkl"


def _stooq_cache_path(config: RunConfig, symbol: str) -> Path:
    safe = symbol.replace("/", "_").replace("-", "_")
    return config.cache_dir / "prices" / "stooq" / f"{safe}_{config.start_date}_{config.effective_end_date}.csv"


def _download_yfinance_chunk(symbols: list[str], config: RunConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    cache_path = _price_cache_path(config, "yfinance", symbols)
    if cache_path.exists():
        cached = pd.read_pickle(cache_path)
        return cached["prices"], cached["volumes"], {
            "status": "cache_hit",
            "retries": 0,
            "error": None,
            "cache_path": str(cache_path),
        }

    import yfinance as yf  # type: ignore

    last_error = None
    for attempt in range(config.retry_count + 1):
        try:
            raw = yf.download(
                tickers=symbols,
                start=config.start_date,
                end=config.end_date,
                auto_adjust=True,
                group_by="column",
                progress=False,
                threads=True,
            )
            prices, volumes = _extract_yfinance(raw, symbols)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            pd.to_pickle({"prices": prices, "volumes": volumes}, cache_path)
            return prices, volumes, {
                "status": "fetched",
                "retries": attempt,
                "error": None,
                "cache_path": str(cache_path),
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
    }


def _download_yfinance(symbols: list[str], config: RunConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    price_frames: list[pd.DataFrame] = []
    volume_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    for chunk in _chunks(symbols, config.price_chunk_size):
        prices, volumes, status = _download_yfinance_chunk(chunk, config)
        price_frames.append(prices)
        volume_frames.append(volumes)
        rows.append(
            {
                "source": "yfinance-adjusted-daily",
                "status": status["status"],
                "records": len(prices.columns),
                "requested_price_symbols": len(chunk),
                "cache_path": status.get("cache_path"),
                "retries": status["retries"],
                "error": status["error"],
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
    missing = [symbol for symbol in symbols if symbol not in prices.columns][: config.stooq_fallback_limit]
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
                    "cache_path": cache_path,
                    "retries": retries,
                    "error": error,
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
                "cache_path": cache_path,
                "retries": retries,
                "error": None,
                "note": f"{symbol}; close-price compatibility may differ from yfinance auto-adjusted prices",
            }
        )
    return prices.sort_index(), volumes.reindex(index=prices.sort_index().index), pd.DataFrame(rows)


def _eligible_filter(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    candidate: pd.DataFrame,
    config: RunConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    exclusions: list[dict[str, object]] = []
    keep: list[str] = []
    as_of = prices.dropna(how="all").index.max() if not prices.empty else None
    for symbol in prices.columns:
        series = prices[symbol].dropna()
        if len(series) < config.min_history_days:
            exclusions.append({"symbol": symbol, "reason": "insufficient price history", "observed": len(series)})
            continue
        latest_date = series.index.max()
        if as_of is not None and (pd.Timestamp(as_of).normalize() - pd.Timestamp(latest_date).normalize()).days > config.stale_after_days:
            exclusions.append({"symbol": symbol, "reason": "stale symbol price", "observed": str(latest_date.date())})
            continue
        latest_price = float(series.iloc[-1])
        if latest_price < config.min_price:
            exclusions.append({"symbol": symbol, "reason": "below minimum price", "observed": latest_price})
            continue
        if symbol not in volumes or volumes[symbol].dropna().empty:
            if config.min_avg_dollar_volume > 0 or config.min_avg_volume > 0:
                exclusions.append({"symbol": symbol, "reason": "missing volume data", "observed": np.nan})
                continue
        else:
            avg_volume = float(volumes[symbol].tail(63).mean())
            avg_dollar = float((prices[symbol].tail(63) * volumes[symbol].tail(63)).mean())
            if avg_volume < config.min_avg_volume:
                exclusions.append({"symbol": symbol, "reason": "below average share-volume filter", "observed": avg_volume})
                continue
            if avg_dollar < config.min_avg_dollar_volume:
                exclusions.append({"symbol": symbol, "reason": "below average dollar-volume filter", "observed": avg_dollar})
                continue
        keep.append(symbol)
    for symbol in candidate["symbol"]:
        if symbol not in prices.columns:
            exclusions.append({"symbol": symbol, "reason": "missing from price providers", "observed": np.nan})
    keep = list(dict.fromkeys(keep))
    price_keep = prices[keep].dropna(how="all") if keep else pd.DataFrame(index=prices.index)
    volume_keep = volumes.reindex(index=price_keep.index, columns=keep)
    eligible = universe_frame_for_symbols(keep)
    exclusions_df = pd.DataFrame(exclusions, columns=["symbol", "reason", "observed"])
    return price_keep, volume_keep, eligible, exclusions_df


def _provider_label_from_sources(stooq_sources: pd.DataFrame) -> str:
    provider = "yfinance-free-public-data"
    records = stooq_sources.get("records", pd.Series(dtype=float)) if not stooq_sources.empty else pd.Series(dtype=float)
    if not stooq_sources.empty and records.fillna(0).astype(int).gt(0).any():
        provider += "+stooq-fallback"
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
        if config.stooq_fallback_limit > 0:
            prices, volumes, stooq_sources = _apply_stooq_fallback(prices, volumes, symbols, config)
        else:
            stooq_sources = pd.DataFrame()
    except Exception as exc:  # pragma: no cover - network dependent
        sample = generate_offline_sample_data(config)
        sample.live_error = f"live download failed: {exc}"
        return sample

    if prices.empty:
        sample = generate_offline_sample_data(config)
        sample.live_error = "live download returned no prices"
        return sample

    prices, volumes, eligible, exclusions = _eligible_filter(prices, volumes, candidate[candidate["symbol"].isin(symbols)], config)
    stooq_symbols = set()
    if not stooq_sources.empty and "symbol" in stooq_sources:
        stooq_symbols = set(stooq_sources.loc[stooq_sources["records"].fillna(0).astype(int).gt(0), "symbol"].astype(str))
    price_source_rows = []
    for symbol in prices.columns:
        if symbol in stooq_symbols:
            source = "stooq-daily-close-fallback"
            note = "Stooq close-price fallback; adjusted-price compatibility may differ from yfinance."
        else:
            source = "yfinance-adjusted-daily"
            note = "yfinance auto_adjust=True daily close series."
        price_source_rows.append({"symbol": symbol, "price_source": source, "adjustment_note": note})
    price_sources = pd.DataFrame(price_source_rows)
    as_of = prices.dropna(how="all").index.max() if not prices.empty else None
    provider = _provider_label_from_sources(stooq_sources)
    summary = _source_frame(
        [
            {
                "source": "live-run-summary",
                "status": "partial_subset" if subset_run else "full_requested_universe",
                "records": len(prices.columns),
                "candidate_symbols": len(candidate),
                "requested_price_symbols": len(symbols),
                "eligible_price_symbols": len(prices.columns),
                "excluded_symbols": len(exclusions),
                "subset_run": subset_run,
                "note": (
                    "Model-portfolio outputs are based only on eligible price symbols after history, "
                    "liquidity, and freshness filters; tradability gates decide whether rows are exported "
                    "as live recommendations or zero-weight research_signals."
                ),
            }
        ]
    )
    data_sources = pd.concat([universe_sources, yf_sources, stooq_sources, summary], ignore_index=True)
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
    )


def load_market_data(config: RunConfig) -> MarketData:
    if config.offline_sample:
        return generate_offline_sample_data(config)
    return download_live_data(config)
