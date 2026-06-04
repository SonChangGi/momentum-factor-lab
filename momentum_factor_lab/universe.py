from __future__ import annotations

# Current liquid US stocks + ETFs. This is intentionally compact for default runs.
DEFAULT_UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA", "VTI", "XLK", "XLF", "XLV", "XLY", "XLI",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "COST", "JPM",
    "LLY", "UNH", "V", "MA", "HD", "PG", "NFLX", "AMD", "CRM", "ORCL",
]

SAMPLE_UNIVERSE = [
    "SPY", "QQQ", "IWM", "XLK", "XLF", "XLV", "AAPL", "MSFT", "NVDA", "AMZN",
    "META", "GOOGL", "JPM", "UNH", "COST", "HD", "PG", "NFLX", "AMD", "ORCL",
]


def normalize_symbols(symbols: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if symbols is None:
        return list(DEFAULT_UNIVERSE)
    if isinstance(symbols, str):
        raw = symbols.replace("\n", ",").split(",")
    else:
        raw = list(symbols)
    out: list[str] = []
    for item in raw:
        symbol = str(item).strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out
