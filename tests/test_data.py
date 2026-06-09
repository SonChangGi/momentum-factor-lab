import sys
import inspect
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.data import (
    _apply_finance_datareader_fallback,
    _apply_stooq_fallback,
    _eligible_filter,
    build_data_quality_frame,
    download_live_data,
)


def _candidate_frame(symbols):
    return pd.DataFrame(
        {
            "symbol": symbols,
            "name": symbols,
            "asset_type": ["stock"] * len(symbols),
            "exchange": ["fixture"] * len(symbols),
            "source": ["test-fixture"] * len(symbols),
            "is_etf": [False] * len(symbols),
        }
    )


def test_eligible_filter_excludes_uninvestable_symbols():
    dates = pd.bdate_range("2024-01-01", periods=260)
    prices = pd.DataFrame(
        {
            "GOOD": np.linspace(20, 30, len(dates)),
            "LOWP": np.linspace(1, 2, len(dates)),
            "SHORT": [np.nan] * 200 + list(np.linspace(10, 12, 60)),
            "ILLIQ": np.linspace(10, 11, len(dates)),
        },
        index=dates,
    )
    volumes = pd.DataFrame(
        {
            "GOOD": 1_000_000,
            "LOWP": 1_000_000,
            "SHORT": 1_000_000,
            "ILLIQ": 10,
        },
        index=dates,
    )
    candidate = _candidate_frame(["GOOD", "LOWP", "SHORT", "ILLIQ", "MISS"])
    config = RunConfig(min_history_days=252, min_price=5, min_avg_dollar_volume=1_000_000)
    filtered, _, eligible, exclusions = _eligible_filter(prices, volumes, candidate, config)
    assert list(filtered.columns) == ["GOOD", "ILLIQ"]
    assert list(eligible["symbol"]) == ["GOOD", "ILLIQ"]
    reasons = exclusions.set_index("symbol")["reason"].to_dict()
    assert reasons["LOWP"] == "below minimum price"
    assert reasons["SHORT"] == "insufficient price history"
    assert reasons["MISS"] == "missing from price providers"


def test_eligible_filter_excludes_recent_data_quality_anomalies():
    dates = pd.bdate_range("2024-01-01", periods=260)
    base = np.linspace(20, 30, len(dates))
    prices = pd.DataFrame(
        {
            "GOOD": base,
            "MISSING": base.copy(),
            "NEGATIVE": base.copy(),
            "EXTREME": base.copy(),
            "OLD_EXTREME": base.copy(),
            "VOLMISS": base.copy(),
            "ALLNAN": np.nan,
        },
        index=dates,
    )
    prices.loc[dates[-60:-30], "MISSING"] = np.nan
    prices.loc[dates[-5], "NEGATIVE"] = -1.0
    prices.loc[dates[-3], "EXTREME"] = prices.loc[dates[-4], "EXTREME"] * 2.5
    prices.loc[dates[5], "OLD_EXTREME"] = prices.loc[dates[4], "OLD_EXTREME"] * 2.5
    volumes = pd.DataFrame(
        {
            "GOOD": 1_000_000,
            "MISSING": 1_000_000,
            "NEGATIVE": 1_000_000,
            "EXTREME": 1_000_000,
            "OLD_EXTREME": 1_000_000,
            "VOLMISS": 1_000_000,
            "ALLNAN": 1_000_000,
        },
        index=dates,
    )
    volumes.loc[dates[-40:], "VOLMISS"] = np.nan
    candidate = _candidate_frame(["GOOD", "MISSING", "NEGATIVE", "EXTREME", "OLD_EXTREME", "VOLMISS", "ALLNAN"])
    config = RunConfig(
        min_history_days=200,
        min_price=5,
        min_avg_dollar_volume=1_000_000,
        data_quality_lookback_days=252,
        max_price_missing_ratio=0.05,
        max_volume_missing_ratio=0.10,
        max_extreme_daily_return=0.80,
    )

    filtered, _, eligible, exclusions = _eligible_filter(prices, volumes, candidate, config)

    assert list(filtered.columns) == ["GOOD", "VOLMISS"]
    assert list(eligible["symbol"]) == ["GOOD", "VOLMISS"]
    reasons = exclusions.set_index("symbol")["reason"].to_dict()
    assert reasons["MISSING"] == "excessive missing price data"
    assert reasons["NEGATIVE"] == "non-positive price observations"
    assert reasons["EXTREME"] == "extreme adjusted daily return anomaly"
    assert reasons["OLD_EXTREME"] == "extreme adjusted daily return anomaly"
    assert reasons["ALLNAN"] == "missing from price providers"


def test_build_data_quality_frame_records_practical_symbol_diagnostics():
    dates = pd.bdate_range("2024-01-01", periods=260)
    prices = pd.DataFrame(
        {
            "GOOD": np.linspace(20, 30, len(dates)),
            "SPY": np.linspace(400, 430, len(dates)),
            "MISSVOL": np.linspace(25, 35, len(dates)),
        },
        index=dates,
    )
    volumes = pd.DataFrame({"GOOD": 1_000_000, "MISSVOL": np.nan}, index=dates)
    candidate = _candidate_frame(["GOOD", "MISSVOL"])
    config = RunConfig(min_history_days=200, min_avg_dollar_volume=1_000_000, data_quality_lookback_days=126)

    quality = build_data_quality_frame(
        prices,
        volumes,
        ["GOOD", "MISSVOL", "MISSING", "SPY"],
        candidate,
        config,
        provider="fixture-provider",
        price_sources=pd.DataFrame(
            [
                {"symbol": "GOOD", "price_source": "adjusted-close-fixture"},
                {"symbol": "SPY", "price_source": "benchmark-fixture"},
            ]
        ),
        exclusions=pd.DataFrame([{"symbol": "MISSVOL", "reason": "missing volume data"}]),
        as_of=dates[-1],
    )

    rows = quality.set_index("symbol")
    assert rows.loc["GOOD", "data_quality_status"] == "pass"
    assert rows.loc["GOOD", "price_source"] == "adjusted-close-fixture"
    assert rows.loc["MISSVOL", "data_quality_status"] == "missing_volume"
    assert rows.loc["MISSING", "data_quality_status"] == "missing_price"
    assert rows.loc["SPY", "data_quality_status"] == "benchmark_comparator_only"
    assert rows.loc["GOOD", "missing_ratio"] == 0.0
    assert not bool(rows.loc["MISSVOL", "data_quality_pass"])


@pytest.mark.parametrize(
    ("provider", "price_source"),
    [
        ("yfinance-free-public-data+stooq-fallback", "stooq-daily-close-fallback"),
        ("yfinance-free-public-data+finance-datareader-fallback", "finance-datareader-close-fallback"),
    ],
)
def test_close_fallback_is_not_tradable_data_quality(provider, price_source):
    dates = pd.bdate_range("2024-01-01", periods=260)
    prices = pd.DataFrame({"STQ": np.linspace(20, 30, len(dates))}, index=dates)
    volumes = pd.DataFrame({"STQ": 1_000_000}, index=dates)
    candidate = _candidate_frame(["STQ"])

    quality = build_data_quality_frame(
        prices,
        volumes,
        ["STQ"],
        candidate,
        RunConfig(min_history_days=200, min_avg_dollar_volume=1_000_000),
        provider=provider,
        price_sources=pd.DataFrame([{"symbol": "STQ", "price_source": price_source}]),
        as_of=dates[-1],
    )

    row = quality.iloc[0]
    assert row["data_quality_status"] == "provider_adjustment_incompatible"
    assert not bool(row["data_quality_pass"])


def test_eligible_filter_retains_benchmark_price_without_candidate_liquidity():
    dates = pd.bdate_range("2024-01-01", periods=260)
    prices = pd.DataFrame(
        {
            "SPY": np.linspace(400, 430, len(dates)),
            "GOOD": np.linspace(20, 30, len(dates)),
        },
        index=dates,
    )
    volumes = pd.DataFrame({"GOOD": 1_000_000}, index=dates)
    candidate = _candidate_frame(["GOOD"])
    config = RunConfig(min_history_days=252, min_price=5, min_avg_dollar_volume=1_000_000)

    filtered, _, eligible, exclusions = _eligible_filter(prices, volumes, candidate, config)

    assert list(filtered.columns) == ["SPY", "GOOD"]
    assert list(eligible["symbol"]) == ["GOOD"]
    assert "SPY" not in set(exclusions["symbol"])


def test_data_quality_frame_records_symbol_level_statuses():
    dates = pd.bdate_range("2024-01-01", periods=260)
    prices = pd.DataFrame(
        {
            "SPY": np.linspace(400, 430, len(dates)),
            "GOOD": np.linspace(20, 30, len(dates)),
            "STALE": list(np.linspace(20, 25, 254)) + [np.nan] * 6,
            "SHORT": [np.nan] * 220 + list(np.linspace(10, 12, 40)),
            "ILLIQ": np.linspace(20, 21, len(dates)),
            "NOVOL": np.linspace(20, 22, len(dates)),
        },
        index=dates,
    )
    volumes = pd.DataFrame(
        {
            "SPY": 1_000_000,
            "GOOD": 1_000_000,
            "STALE": 1_000_000,
            "SHORT": 1_000_000,
            "ILLIQ": 10,
        },
        index=dates,
    )
    candidate = _candidate_frame(["GOOD", "STALE", "SHORT", "ILLIQ", "NOVOL", "MISS"])
    config = RunConfig(
        min_history_days=252,
        min_price=5,
        min_avg_dollar_volume=1_000_000,
        stale_after_days=5,
    )
    _, _, _, exclusions = _eligible_filter(prices, volumes, candidate, config)
    price_sources = pd.DataFrame(
        {"symbol": list(prices.columns), "price_source": ["fixture-adjusted"] * len(prices.columns)}
    )

    quality = build_data_quality_frame(
        prices,
        volumes,
        ["SPY", "GOOD", "STALE", "SHORT", "ILLIQ", "NOVOL", "MISS"],
        candidate,
        config,
        provider="fixture-provider",
        price_sources=price_sources,
        exclusions=exclusions,
        as_of=prices.index.max(),
    )
    statuses = quality.set_index("symbol")["data_quality_status"].to_dict()
    roles = quality.set_index("symbol")["role"].to_dict()

    assert roles["SPY"] == "benchmark"
    assert statuses["SPY"] == "benchmark_comparator_only"
    assert statuses["GOOD"] == "pass"
    assert statuses["STALE"] == "stale_price"
    assert statuses["SHORT"] == "insufficient_history"
    assert statuses["ILLIQ"] == "below_liquidity_floor"
    assert statuses["NOVOL"] == "missing_volume"
    assert statuses["MISS"] == "missing_price"


def test_stooq_fallback_records_symbol_provider_and_cache(monkeypatch, tmp_path):
    dates = pd.bdate_range("2024-01-01", periods=5)
    config = RunConfig(cache_dir=tmp_path, stooq_fallback_limit=1)

    def fake_download(symbol, cfg):
        price = pd.Series(np.linspace(10, 12, len(dates)), index=dates, name=symbol)
        volume = pd.Series(1000, index=dates, name=symbol)
        return price, volume, None, "cache_hit", str(tmp_path / "cached.csv"), 0

    monkeypatch.setattr("momentum_factor_lab.data._download_stooq_symbol", fake_download)
    prices, volumes, sources = _apply_stooq_fallback(pd.DataFrame(index=dates), pd.DataFrame(index=dates), ["MISS"], config)
    assert "MISS" in prices.columns
    assert "MISS" in volumes.columns
    row = sources.iloc[0]
    assert row["symbol"] == "MISS"
    assert row["source"] == "stooq-daily-close-fallback"
    assert row["status"] == "cache_hit"
    assert row["cache_path"].endswith("cached.csv")


def test_stooq_fallback_defaults_to_all_missing_symbols(monkeypatch, tmp_path):
    dates = pd.bdate_range("2024-01-01", periods=5)
    config = RunConfig(cache_dir=tmp_path, stooq_fallback_limit=None)

    def fake_download(symbol, cfg):
        price = pd.Series(np.linspace(10, 12, len(dates)), index=dates, name=symbol)
        volume = pd.Series(1000, index=dates, name=symbol)
        return price, volume, None, "fetched", str(tmp_path / f"{symbol}.csv"), 0

    monkeypatch.setattr("momentum_factor_lab.data._download_stooq_symbol", fake_download)
    prices, volumes, sources = _apply_stooq_fallback(
        pd.DataFrame(index=dates),
        pd.DataFrame(index=dates),
        ["MISS1", "MISS2"],
        config,
    )

    assert set(prices.columns) == {"MISS1", "MISS2"}
    assert set(volumes.columns) == {"MISS1", "MISS2"}
    assert set(sources["symbol"]) == {"MISS1", "MISS2"}


def test_finance_datareader_fallback_records_symbol_provider(monkeypatch, tmp_path):
    dates = pd.bdate_range("2024-01-01", periods=5)
    config = RunConfig(cache_dir=tmp_path, finance_datareader_fallback_limit=None)

    def fake_download(symbol, cfg):
        price = pd.Series(np.linspace(20, 22, len(dates)), index=dates, name=symbol)
        volume = pd.Series(2000, index=dates, name=symbol)
        return price, volume, None, "fetched", str(tmp_path / f"{symbol}.csv"), 0

    monkeypatch.setattr("momentum_factor_lab.data._download_finance_datareader_symbol", fake_download)
    prices, volumes, sources = _apply_finance_datareader_fallback(
        pd.DataFrame(index=dates),
        pd.DataFrame(index=dates),
        ["FDR1", "FDR2"],
        config,
    )

    assert set(prices.columns) == {"FDR1", "FDR2"}
    assert set(volumes.columns) == {"FDR1", "FDR2"}
    assert set(sources["source"]) == {"finance-datareader-close-fallback"}
    assert set(sources["symbol"]) == {"FDR1", "FDR2"}


def test_live_download_preserves_yfinance_stooq_finance_datareader_order(monkeypatch, tmp_path):
    dates = pd.bdate_range("2024-01-01", periods=8)
    config = RunConfig(
        cache_dir=tmp_path,
        start_date="2024-01-01",
        end_date="2024-01-12",
        min_history_days=2,
        min_price=1,
        min_avg_dollar_volume=0,
        min_liquidity_observations=2,
        stale_after_days=10_000,
        universe=["YF", "STQ", "FDRX"],
    )
    candidate = _candidate_frame(["YF", "STQ", "FDRX"])
    monkeypatch.setattr(
        "momentum_factor_lab.data._candidate_universe",
        lambda _: (
            candidate,
            pd.DataFrame([{"source": "fixture-universe", "status": "loaded", "records": 3}]),
        ),
    )
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace())

    def fake_yfinance(symbols, cfg):
        prices = pd.DataFrame(
            {
                "SPY": np.linspace(400, 408, len(dates)),
                "YF": np.linspace(10, 18, len(dates)),
            },
            index=dates,
        )
        volumes = pd.DataFrame({"SPY": 1_000_000, "YF": 1_000_000}, index=dates)
        return prices, volumes, pd.DataFrame(
            [
                {
                    "source": "yfinance-adjusted-daily",
                    "status": "fetched",
                    "records": 2,
                    "requested_symbols": ",".join(symbols),
                    "returned_symbols": "SPY,YF",
                    "missing_symbols": "STQ,FDRX",
                }
            ]
        )

    def fake_stooq(symbol, cfg):
        if symbol != "STQ":
            return None, None, "not found", "failed", "cache", 0
        return (
            pd.Series(np.linspace(20, 28, len(dates)), index=dates, name=symbol),
            pd.Series(2_000_000, index=dates, name=symbol),
            None,
            "fetched",
            "cache",
            0,
        )

    def fake_fdr(symbol, cfg):
        if symbol != "FDRX":
            return None, None, "not found", "failed", "cache", 0
        return (
            pd.Series(np.linspace(30, 38, len(dates)), index=dates, name=symbol),
            pd.Series(3_000_000, index=dates, name=symbol),
            None,
            "fetched",
            "cache",
            0,
        )

    monkeypatch.setattr("momentum_factor_lab.data._download_yfinance", fake_yfinance)
    monkeypatch.setattr("momentum_factor_lab.data._download_stooq_symbol", fake_stooq)
    monkeypatch.setattr("momentum_factor_lab.data._download_finance_datareader_symbol", fake_fdr)

    result = download_live_data(config)

    sources = result.data_sources["source"].tolist()
    assert sources.index("yfinance-adjusted-daily") < sources.index("stooq-daily-close-fallback")
    assert sources.index("stooq-daily-close-fallback") < sources.index("finance-datareader-close-fallback")
    assert {"YF", "STQ", "FDRX"}.issubset(set(result.prices.columns))
    summary = result.data_sources[result.data_sources["source"].eq("live-run-summary")].iloc[-1]
    assert int(summary["requested_price_symbols"]) == 3
    assert int(summary["eligible_price_symbols"]) == 3


def test_yfinance_chunk_uses_csv_json_price_cache_without_network(tmp_path):
    from momentum_factor_lab.data import _download_yfinance_chunk, _price_cache_path, _write_price_cache

    config = RunConfig(cache_dir=tmp_path, start_date="2024-01-01", end_date="2024-01-10")
    symbols = ["AAA", "BBB"]
    dates = pd.bdate_range("2024-01-01", periods=3)
    cached_prices = pd.DataFrame({"AAA": [1, 2, 3], "BBB": [4, 5, 6]}, index=dates)
    cached_volumes = pd.DataFrame({"AAA": [10, 10, 10], "BBB": [20, 20, 20]}, index=dates)
    cache_path = _price_cache_path(config, "yfinance", symbols)
    _write_price_cache(cache_path, cached_prices, cached_volumes, provider="yfinance", symbols=symbols)
    prices, volumes, status = _download_yfinance_chunk(symbols, config)
    pd.testing.assert_frame_equal(prices, cached_prices, check_freq=False)
    pd.testing.assert_frame_equal(volumes, cached_volumes, check_freq=False)
    assert status["status"] == "cache_hit"
    assert status["cache_path"] == str(cache_path)
    assert status["cache_format"] == "csv+json"
    assert cache_path.suffix == ".json"
    assert not list(tmp_path.rglob("*.pkl"))


def test_yfinance_chunk_does_not_use_pickle_cache(monkeypatch, tmp_path):
    import momentum_factor_lab.data as data
    from momentum_factor_lab.data import _download_yfinance_chunk

    monkeypatch.setattr(pd, "read_pickle", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("read_pickle used")))
    monkeypatch.setattr(pd, "to_pickle", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("to_pickle used")))

    dates = pd.bdate_range("2024-01-01", periods=2)
    raw = pd.DataFrame({"Close": [10.0, 11.0], "Volume": [100.0, 120.0]}, index=dates)

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=lambda **kwargs: raw))

    config = RunConfig(cache_dir=tmp_path, start_date="2024-01-01", end_date="2024-01-10")
    prices, volumes, status = _download_yfinance_chunk(["AAA"], config)

    assert status["status"] == "fetched"
    assert list(prices.columns) == ["AAA"]
    assert list(volumes.columns) == ["AAA"]
    assert not list(tmp_path.rglob("*.pkl"))
    assert not str(status.get("cache_path", "")).endswith(".pkl")
    source = inspect.getsource(data)
    assert "read_pickle" not in source
    assert "to_pickle" not in source
    assert ".pkl" not in source


def test_yfinance_chunk_passes_inclusive_config_end_date(monkeypatch, tmp_path):
    from momentum_factor_lab.data import _download_yfinance_chunk

    captured = {}
    dates = pd.bdate_range("2024-01-01", periods=3)
    columns = pd.MultiIndex.from_tuples(
        [
            ("Close", "AAA"),
            ("Close", "BBB"),
            ("Volume", "AAA"),
            ("Volume", "BBB"),
        ]
    )
    raw = pd.DataFrame(
        [
            [1.0, 4.0, 100.0, 400.0],
            [2.0, 5.0, 100.0, 400.0],
            [3.0, 6.0, 100.0, 400.0],
        ],
        index=dates,
        columns=columns,
    )

    def fake_download(**kwargs):
        captured.update(kwargs)
        return raw

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=fake_download))

    config = RunConfig(cache_dir=tmp_path, start_date="2024-01-01", end_date="2024-01-10")
    prices, volumes, status = _download_yfinance_chunk(["AAA", "BBB"], config)

    assert captured["end"] == "2024-01-11"
    assert captured["start"] == "2024-01-01"
    assert status["status"] == "fetched"
    assert list(prices.columns) == ["AAA", "BBB"]
    assert list(volumes.columns) == ["AAA", "BBB"]


def test_yfinance_chunk_leaves_open_ended_download_without_end(monkeypatch, tmp_path):
    from momentum_factor_lab.data import _download_yfinance_chunk

    captured = {}
    dates = pd.bdate_range("2024-01-01", periods=2)
    raw = pd.DataFrame({"Close": [10.0, 11.0], "Volume": [100.0, 120.0]}, index=dates)

    def fake_download(**kwargs):
        captured.update(kwargs)
        return raw

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=fake_download))

    config = RunConfig(cache_dir=tmp_path, start_date="2024-01-01", end_date=None)
    prices, _, status = _download_yfinance_chunk(["AAA"], config)

    assert captured["end"] is None
    assert status["status"] == "fetched"
    assert list(prices.columns) == ["AAA"]


def test_provider_summary_marks_cached_stooq_as_mixed():
    from momentum_factor_lab.data import _provider_label_from_sources

    stooq_sources = pd.DataFrame(
        [{"source": "stooq-daily-close-fallback", "symbol": "MISS", "status": "cache_hit", "records": 1}]
    )
    assert _provider_label_from_sources(stooq_sources) == "yfinance-free-public-data+stooq-fallback"
    fdr_sources = pd.DataFrame(
        [{"source": "finance-datareader-close-fallback", "symbol": "MISS2", "status": "fetched", "records": 1}]
    )
    assert (
        _provider_label_from_sources(stooq_sources, fdr_sources)
        == "yfinance-free-public-data+stooq-fallback+finance-datareader-fallback"
    )
    assert _provider_label_from_sources(pd.DataFrame()) == "yfinance-free-public-data"


def test_build_eligibility_mask_uses_rebalance_date_liquidity_and_history():
    from momentum_factor_lab.data import build_eligibility_mask

    dates = pd.bdate_range("2024-01-01", periods=80)
    prices = pd.DataFrame(
        {
            "GOOD": np.linspace(20, 30, len(dates)),
            "LATE": [np.nan] * 30 + list(np.linspace(20, 25, 50)),
            "LOWP": np.linspace(1, 2, len(dates)),
            "ILLIQ": np.linspace(20, 21, len(dates)),
        },
        index=dates,
    )
    volumes = pd.DataFrame(
        {
            "GOOD": 1_000_000,
            "LATE": 1_000_000,
            "LOWP": 1_000_000,
            "ILLIQ": 10,
        },
        index=dates,
    )
    config = RunConfig(
        min_history_days=40,
        min_price=5,
        min_avg_dollar_volume=1_000_000,
        min_liquidity_observations=20,
    )

    mask = build_eligibility_mask(prices, volumes, config)

    assert mask.loc[dates[45], "GOOD"]
    assert not mask.loc[dates[45], "LATE"]
    assert mask.loc[dates[-1], "LATE"]
    assert not mask["LOWP"].any()
    assert not mask.loc[dates[-1], "ILLIQ"]


def test_aggressive_profile_lowers_endpoint_discovery_not_configured_gate():
    dates = pd.bdate_range("2024-01-01", periods=260)
    prices = pd.DataFrame({"MID": np.linspace(10, 12, len(dates))}, index=dates)
    volumes = pd.DataFrame({"MID": 150_000}, index=dates)  # about $1.8m ADV, below default $5m.
    candidate = _candidate_frame(["MID"])
    aggressive = RunConfig(universe_profile="aggressive_stock_only", min_avg_dollar_volume=5_000_000)
    large = RunConfig(universe_profile="large_liquid", min_avg_dollar_volume=5_000_000)

    aggressive_prices, _, aggressive_eligible, _ = _eligible_filter(prices, volumes, candidate, aggressive)
    large_prices, _, large_eligible, _ = _eligible_filter(prices, volumes, candidate, large)

    assert list(aggressive_prices.columns) == ["MID"]
    assert list(aggressive_eligible["symbol"]) == ["MID"]
    assert list(large_prices.columns) == ["MID"]
    assert list(large_eligible["symbol"]) == ["MID"]
    assert aggressive.min_avg_dollar_volume == 5_000_000
