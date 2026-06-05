from momentum_factor_lab.universe import (
    DEFAULT_UNIVERSE,
    is_excluded_instrument_name,
    load_packaged_universe_frame,
    parse_nasdaq_symbol_directory,
    parse_sec_company_tickers_exchange,
)


def test_default_universe_has_at_least_2000_symbols_and_etfs():
    frame = load_packaged_universe_frame()
    assert len(DEFAULT_UNIVERSE) >= 2000
    assert len(frame) >= 2000
    assert frame["symbol"].is_unique
    assert frame["is_etf"].any()
    assert {"symbol", "name", "asset_type", "exchange", "source", "is_etf"}.issubset(frame.columns)


def test_sec_company_tickers_exchange_parser():
    payload = '{"fields":["cik","name","ticker","exchange"],"data":[[1,"Acme Corp","ACME","Nasdaq"]]}'
    frame = parse_sec_company_tickers_exchange(payload)
    assert frame.loc[0, "symbol"] == "ACME"
    assert frame.loc[0, "asset_type"] == "stock"
    assert frame.loc[0, "exchange"] == "Nasdaq"


def test_nasdaq_symbol_directory_parser_filters_tests_and_etfs():
    payload = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\nAAA|AAA Corp|Q|N|N|100|N|N\nBBB|BBB ETF|Q|N|N|100|Y|N\nTEST|Test Issue|Q|Y|N|100|N|N\nFile Creation Time: today"
    frame = parse_nasdaq_symbol_directory(payload, source_name="fixture")
    assert list(frame["symbol"]) == ["AAA", "BBB"]
    assert frame.set_index("symbol").loc["BBB", "is_etf"]


def test_packaged_universe_excludes_leveraged_inverse_short_products():
    frame = load_packaged_universe_frame()
    assert not frame["name"].map(is_excluded_instrument_name).any()
    assert is_excluded_instrument_name("Direxion Daily Bear 3X Shares")
    assert is_excluded_instrument_name("GraniteShares 2x Long NVDA Daily ETF")
    assert is_excluded_instrument_name("GraniteShares 1.25x Long TSLA Daily ETF")
    assert "TSL" not in set(frame["symbol"])
    assert is_excluded_instrument_name("ProShares UltraShort QQQ")
