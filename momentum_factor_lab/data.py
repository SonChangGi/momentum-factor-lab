from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

import numpy as np
import pandas as pd

from .config import RunConfig
from .universe import SAMPLE_UNIVERSE


@dataclass(slots=True)
class MarketData:
    prices: pd.DataFrame
    volumes: pd.DataFrame
    provider: str
    fetched_at: datetime
    as_of: pd.Timestamp | None
    exclusions: pd.DataFrame
    offline_sample: bool
    live_error: str | None = None

    @property
    def is_live(self) -> bool:
        return not self.offline_sample and self.live_error is None


def _business_dates(config: RunConfig) -> pd.DatetimeIndex:
    end = pd.Timestamp(config.end_date or "2025-12-31")
    return pd.bdate_range(config.start_date, end)


def generate_offline_sample_data(config: RunConfig) -> MarketData:
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
    return MarketData(
        prices=price_df,
        volumes=volume_df,
        provider="deterministic-offline-sample",
        fetched_at=datetime.now(UTC),
        as_of=price_df.index.max(),
        exclusions=exclusions,
        offline_sample=True,
    )


def _extract_yfinance(download: pd.DataFrame, symbols: Iterable[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if download.empty:
        return pd.DataFrame(), pd.DataFrame()
    symbols = list(symbols)
    if isinstance(download.columns, pd.MultiIndex):
        # yfinance can return either field-first or ticker-first MultiIndex.
        lvl0 = set(map(str, download.columns.get_level_values(0)))
        if "Close" in lvl0 or "Adj Close" in lvl0:
            close_key = "Adj Close" if "Adj Close" in lvl0 else "Close"
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


def download_live_data(config: RunConfig) -> MarketData:
    fetched_at = datetime.now(UTC)
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional extra
        sample = generate_offline_sample_data(config)
        sample.live_error = f"yfinance unavailable: {exc}"
        return sample

    symbols = list(dict.fromkeys([config.benchmark, *config.universe]))
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
    except Exception as exc:  # pragma: no cover - network dependent
        sample = generate_offline_sample_data(config)
        sample.live_error = f"live download failed: {exc}"
        return sample

    if prices.empty:
        sample = generate_offline_sample_data(config)
        sample.live_error = "live download returned no prices"
        return sample

    exclusions = []
    keep = []
    for symbol in symbols:
        if symbol not in prices:
            exclusions.append({"symbol": symbol, "reason": "missing from provider response"})
            continue
        series = prices[symbol].dropna()
        if len(series) < config.min_history_days:
            exclusions.append({"symbol": symbol, "reason": "insufficient price history"})
            continue
        if symbol in volumes:
            avg_dollar = (prices[symbol].tail(63) * volumes[symbol].tail(63)).mean()
            if pd.notna(avg_dollar) and avg_dollar < config.min_avg_dollar_volume:
                exclusions.append({"symbol": symbol, "reason": "below average dollar-volume filter"})
                continue
        keep.append(symbol)
    prices = prices[keep].dropna(how="all")
    volumes = volumes.reindex(columns=keep).loc[prices.index]
    return MarketData(
        prices=prices,
        volumes=volumes,
        provider="yfinance-free-public-data",
        fetched_at=fetched_at,
        as_of=prices.dropna(how="all").index.max() if not prices.empty else None,
        exclusions=pd.DataFrame(exclusions),
        offline_sample=False,
    )


def load_market_data(config: RunConfig) -> MarketData:
    if config.offline_sample:
        return generate_offline_sample_data(config)
    return download_live_data(config)
