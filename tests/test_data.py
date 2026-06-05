import numpy as np
import pandas as pd

from momentum_factor_lab.config import RunConfig
from momentum_factor_lab.data import _apply_stooq_fallback, _eligible_filter


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
    assert list(filtered.columns) == ["GOOD"]
    assert list(eligible["symbol"]) == ["GOOD"]
    reasons = exclusions.set_index("symbol")["reason"].to_dict()
    assert reasons["LOWP"] == "below minimum price"
    assert reasons["SHORT"] == "insufficient price history"
    assert reasons["ILLIQ"] == "below average dollar-volume filter"
    assert reasons["MISS"] == "missing from price providers"


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


def test_yfinance_chunk_uses_price_cache_without_network(tmp_path):
    from momentum_factor_lab.data import _download_yfinance_chunk, _price_cache_path

    config = RunConfig(cache_dir=tmp_path, start_date="2024-01-01", end_date="2024-01-10")
    symbols = ["AAA", "BBB"]
    dates = pd.bdate_range("2024-01-01", periods=3)
    cached_prices = pd.DataFrame({"AAA": [1, 2, 3], "BBB": [4, 5, 6]}, index=dates)
    cached_volumes = pd.DataFrame({"AAA": [10, 10, 10], "BBB": [20, 20, 20]}, index=dates)
    cache_path = _price_cache_path(config, "yfinance", symbols)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle({"prices": cached_prices, "volumes": cached_volumes}, cache_path)
    prices, volumes, status = _download_yfinance_chunk(symbols, config)
    pd.testing.assert_frame_equal(prices, cached_prices)
    pd.testing.assert_frame_equal(volumes, cached_volumes)
    assert status["status"] == "cache_hit"
    assert status["cache_path"] == str(cache_path)


def test_provider_summary_marks_cached_stooq_as_mixed():
    from momentum_factor_lab.data import _provider_label_from_sources

    stooq_sources = pd.DataFrame(
        [{"source": "stooq-daily-close-fallback", "symbol": "MISS", "status": "cache_hit", "records": 1}]
    )
    assert _provider_label_from_sources(stooq_sources) == "yfinance-free-public-data+stooq-fallback"
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
    assert not mask["ILLIQ"].any()


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
    assert large_prices.empty
    assert large_eligible.empty
    assert aggressive.min_avg_dollar_volume == 5_000_000
