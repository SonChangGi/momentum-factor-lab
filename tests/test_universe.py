from momentum_factor_lab.universe import (
    DEFAULT_UNIVERSE,
    DEFAULT_UNIVERSE_PATH,
    build_public_universe_frame,
    is_excluded_instrument_name,
    is_known_etf_symbol,
    load_packaged_universe_frame,
    parse_nasdaq_symbol_directory,
    parse_sec_company_tickers_exchange,
    universe_frame_for_symbols,
)
import pandas as pd


def test_default_universe_has_at_least_2000_stock_symbols_and_no_etfs():
    frame = load_packaged_universe_frame()
    assert len(DEFAULT_UNIVERSE) >= 2000
    assert len(frame) >= 2000
    assert frame["symbol"].is_unique
    assert not frame["is_etf"].any()
    assert set(frame["asset_type"]) == {"stock"}
    assert {"SPY", "QQQ", "IWM", "XLK", "XLF", "XLV"}.isdisjoint(set(frame["symbol"]))
    assert {"symbol", "name", "asset_type", "exchange", "source", "is_etf"}.issubset(frame.columns)


def test_raw_packaged_universe_resource_is_stock_only_not_runtime_only():
    raw = pd.read_csv(DEFAULT_UNIVERSE_PATH)
    assert len(raw) >= 2000
    assert raw["symbol"].is_unique
    assert not raw["is_etf"].astype(bool).any()
    assert set(raw["asset_type"]) == {"stock"}
    assert not raw["name"].map(is_excluded_instrument_name).any()
    assert {"SPY", "QQQ", "IWM", "XLK", "XLF", "XLV", "PHYS", "PDI", "QQQX"}.isdisjoint(set(raw["symbol"]))


def test_sec_company_tickers_exchange_parser():
    payload = '{"fields":["cik","name","ticker","exchange"],"data":[[1,"Acme Corp","ACME","Nasdaq"]]}'
    frame = parse_sec_company_tickers_exchange(payload)
    assert frame.loc[0, "symbol"] == "ACME"
    assert frame.loc[0, "asset_type"] == "stock"
    assert frame.loc[0, "exchange"] == "Nasdaq"


def test_sec_parser_filters_fund_like_instruments_by_name():
    payload = (
        '{"fields":["cik","name","ticker","exchange"],'
        '"data":[[1,"Sprott Physical Gold Trust","PHYS","NYSE Arca"],[2,"Acme Corp","ACME","Nasdaq"]]}'
    )
    frame = parse_sec_company_tickers_exchange(payload)
    assert list(frame["symbol"]) == ["ACME"]


def test_nasdaq_symbol_directory_parser_filters_tests_and_etfs():
    payload = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\nAAA|AAA Corp|Q|N|N|100|N|N\nBBB|BBB ETF|Q|N|N|100|Y|N\nTEST|Test Issue|Q|Y|N|100|N|N\nFile Creation Time: today"
    frame = parse_nasdaq_symbol_directory(payload, source_name="fixture")
    assert list(frame["symbol"]) == ["AAA"]
    assert not frame["is_etf"].any()


def test_nasdaq_parser_can_retain_etf_evidence_for_refresh_merge():
    payload = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\nAAA|AAA Corp|Q|N|N|100|N|N\nZZZ|ZZZ ETF|Q|N|N|100|Y|N\nFile Creation Time: today"
    frame = parse_nasdaq_symbol_directory(payload, source_name="fixture", include_etfs=True)
    assert set(frame["symbol"]) == {"AAA", "ZZZ"}
    assert frame.set_index("symbol").loc["ZZZ", "is_etf"]


def test_public_universe_refresh_combined_output_is_stock_only(monkeypatch, tmp_path):
    sec_payload = (
        '{"fields":["cik","name","ticker","exchange"],'
        '"data":[[1,"AAA Corp","AAA","Nasdaq"],[2,"SPDR S&P 500 ETF Trust","SPY","NYSE Arca"],'
        '[3,"Invesco QQQ Trust","QQQ","Nasdaq"],[4,"Sprott Physical Gold Trust","PHYS","NYSE Arca"],'
        '[5,"ZZZ Holding Co","ZZZ","Nasdaq"]]}'
    )
    nasdaq_payload = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\nAAA|AAA Corp|Q|N|N|100|N|N\nQQQ|Invesco QQQ Trust|Q|N|N|100|Y|N\nZZZ|ZZZ ETF|Q|N|N|100|Y|N\nTEST|Test Issue|Q|Y|N|100|N|N\nFile Creation Time: today"
    other_payload = "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\nBBB|BBB Corp|N|BBB|N|100|N|BBB\nIWM|iShares Russell 2000 ETF|P|IWM|Y|100|N|IWM\nFile Creation Time: today"

    def fake_fetch(url, cache_dir, cache_name, retry_count, retry_backoff_seconds):
        payloads = {
            "sec_company_tickers_exchange.json": sec_payload,
            "nasdaqlisted.txt": nasdaq_payload,
            "otherlisted.txt": other_payload,
        }
        return payloads[cache_name], {"source": url, "status": "fixture", "cache_path": str(tmp_path / cache_name), "retries": 0}

    monkeypatch.setattr("momentum_factor_lab.universe._fetch_text_with_cache", fake_fetch)

    result = build_public_universe_frame(cache_dir=tmp_path)

    assert list(result.frame["symbol"]) == ["AAA", "BBB"]
    assert not result.frame["is_etf"].any()
    assert set(result.frame["asset_type"]) == {"stock"}


def test_known_etf_tickers_are_denied_as_custom_candidates():
    denied = ["SPY", "QQQ", "VUG", "VGT", "TQQQ", "SQQQ", "EFA", "EEM", "HYG", "LQD", "XBI", "XRT"]
    frame = universe_frame_for_symbols([*denied, "VDE", "UNKNOWN", "AAPL", "MSFT"])
    assert {"AAPL", "MSFT"}.issubset(set(frame["symbol"]))
    assert {*denied, "VDE", "UNKNOWN"}.isdisjoint(set(frame["symbol"]))
    assert all(is_known_etf_symbol(symbol) for symbol in denied)


def test_packaged_universe_excludes_leveraged_inverse_short_products():
    frame = load_packaged_universe_frame()
    assert not frame["name"].map(is_excluded_instrument_name).any()
    assert is_excluded_instrument_name("Direxion Daily Bear 3X Shares")
    assert is_excluded_instrument_name("GraniteShares 2x Long NVDA Daily ETF")
    assert is_excluded_instrument_name("GraniteShares 1.25x Long TSLA Daily ETF")
    assert "TSL" not in set(frame["symbol"])
    assert is_excluded_instrument_name("ProShares UltraShort QQQ")
