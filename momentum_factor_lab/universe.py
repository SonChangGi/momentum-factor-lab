from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

RESOURCE_DIR = Path(__file__).with_name("resources")
DEFAULT_UNIVERSE_PATH = RESOURCE_DIR / "default_universe.csv"
SEC_COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
NASDAQ_LISTED_URL = "http://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_OTHER_LISTED_URL = "http://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
USER_AGENT = "momentum-factor-lab/0.1 free-public-data research"

CORE_SAMPLE_SYMBOLS = [
    "SPY",
    "QQQ",
    "IWM",
    "XLK",
    "XLF",
    "XLV",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "JPM",
    "UNH",
    "COST",
    "HD",
    "PG",
    "NFLX",
    "AMD",
    "ORCL",
]


@dataclass(frozen=True, slots=True)
class UniverseSourceResult:
    frame: pd.DataFrame
    data_sources: pd.DataFrame


def normalize_symbol(symbol: object) -> str:
    return str(symbol).strip().upper().replace(".", "-")


FORBIDDEN_INSTRUMENT_TERMS = (
    "2X",
    "3X",
    "-2X",
    "-3X",
    "LEVERAGED",
    "ULTRA",
    "ULTRAPRO",
    "DIREXION DAILY",
    "BEAR",
    "INVERSE",
    "SHORT ",
    "SHORT-",
    "BULL 2",
    "BULL 3",
    " DAILY BULL",
    " DAILY BEAR",
)


def is_supported_symbol(symbol: str) -> bool:
    if not re.match(r"^[A-Z][A-Z0-9-]{0,9}$", symbol):
        return False
    derivative_suffixes = ("WS", "WT", "W", "U", "R")
    return not (len(symbol) > 2 and symbol.endswith(derivative_suffixes))


def is_excluded_instrument_name(name: object) -> bool:
    upper = str(name).upper().replace("&", " AND ")
    if any(term in upper for term in FORBIDDEN_INSTRUMENT_TERMS):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\s*X\b", upper):
        return True
    if re.search(r"\b\d+(?:\.\d+)?X\s+(LONG|SHORT)", upper):
        return True
    if " DAILY " in upper and (" LONG " in upper or " SHORT " in upper):
        return True
    return False


def normalize_symbols(symbols: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if symbols is None:
        return list(DEFAULT_UNIVERSE)
    raw = symbols.replace("\n", ",").split(",") if isinstance(symbols, str) else list(symbols)
    out: list[str] = []
    for item in raw:
        symbol = normalize_symbol(item)
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def _base_columns() -> list[str]:
    return ["symbol", "name", "asset_type", "exchange", "source", "is_etf"]


def _clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=_base_columns())
    out = frame.copy()
    out["symbol"] = out["symbol"].map(normalize_symbol)
    out = out[out["symbol"].map(is_supported_symbol)]
    if "name" in out:
        out = out[~out["name"].map(is_excluded_instrument_name)]
    out = out.drop_duplicates("symbol", keep="first")
    for col in _base_columns():
        if col not in out:
            out[col] = ""
    out["is_etf"] = out["is_etf"].map(lambda v: str(v).lower() in {"true", "1", "yes", "y"})
    out["asset_type"] = out.apply(
        lambda row: "etf" if bool(row["is_etf"]) else (str(row["asset_type"]).lower() or "stock"),
        axis=1,
    )
    return out[_base_columns()].reset_index(drop=True)


def load_packaged_universe_frame(path: Path = DEFAULT_UNIVERSE_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"default universe resource missing: {path}")
    frame = pd.read_csv(path)
    return _clean_frame(frame)


def _load_default_symbols() -> list[str]:
    try:
        return load_packaged_universe_frame()["symbol"].tolist()
    except Exception:
        return list(CORE_SAMPLE_SYMBOLS)


DEFAULT_UNIVERSE = _load_default_symbols()
SAMPLE_UNIVERSE = list(CORE_SAMPLE_SYMBOLS)


def universe_frame_for_symbols(symbols: list[str] | tuple[str, ...] | str | None) -> pd.DataFrame:
    normalized = normalize_symbols(symbols)
    packaged = load_packaged_universe_frame().set_index("symbol")
    rows = []
    for symbol in normalized:
        if symbol in packaged.index:
            row = packaged.loc[symbol].to_dict()
            row["symbol"] = symbol
        else:
            row = {
                "symbol": symbol,
                "name": symbol,
                "asset_type": "custom",
                "exchange": "unknown",
                "source": "user-supplied",
                "is_etf": False,
            }
        rows.append(row)
    return _clean_frame(pd.DataFrame(rows))


def parse_sec_company_tickers_exchange(payload: str) -> pd.DataFrame:
    data = json.loads(payload)
    fields = data.get("fields", [])
    rows = []
    for raw in data.get("data", []):
        item = dict(zip(fields, raw, strict=False))
        symbol = normalize_symbol(item.get("ticker", ""))
        rows.append(
            {
                "symbol": symbol,
                "name": item.get("name", ""),
                "asset_type": "stock",
                "exchange": item.get("exchange", ""),
                "source": "sec-company-tickers-exchange",
                "is_etf": False,
            }
        )
    return _clean_frame(pd.DataFrame(rows))


def parse_nasdaq_symbol_directory(payload: str, *, source_name: str) -> pd.DataFrame:
    lines = [line for line in payload.splitlines() if "|" in line and not line.startswith("File Creation Time")]
    if not lines:
        return pd.DataFrame(columns=_base_columns())
    reader = csv.DictReader(lines, delimiter="|")
    rows = []
    for row in reader:
        symbol = normalize_symbol(row.get("Symbol") or row.get("ACT Symbol") or row.get("NASDAQ Symbol") or "")
        if row.get("Test Issue", "N").strip().upper() == "Y":
            continue
        is_etf = row.get("ETF", "N").strip().upper() == "Y"
        rows.append(
            {
                "symbol": symbol,
                "name": (row.get("Security Name") or "").strip(),
                "asset_type": "etf" if is_etf else "stock",
                "exchange": (row.get("Exchange") or "NASDAQ").strip(),
                "source": source_name,
                "is_etf": is_etf,
            }
        )
    return _clean_frame(pd.DataFrame(rows))


def _fetch_text_with_cache(
    url: str,
    cache_dir: Path | None,
    cache_name: str,
    retry_count: int,
    retry_backoff_seconds: float,
) -> tuple[str | None, dict[str, object]]:
    cache_path = cache_dir / cache_name if cache_dir is not None else None
    if cache_path is not None and cache_path.exists():
        return cache_path.read_text(encoding="utf-8"), {
            "source": url,
            "status": "cache_hit",
            "cache_path": str(cache_path),
            "retries": 0,
        }
    last_error = None
    for attempt in range(retry_count + 1):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
                text = response.read().decode("utf-8", errors="replace")
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(text, encoding="utf-8")
            return text, {
                "source": url,
                "status": "fetched",
                "cache_path": str(cache_path) if cache_path is not None else "disabled",
                "retries": attempt,
            }
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt < retry_count:
                time.sleep(retry_backoff_seconds)
    return None, {
        "source": url,
        "status": "failed",
        "cache_path": str(cache_path) if cache_path is not None else "disabled",
        "retries": retry_count,
        "error": str(last_error),
    }


def build_public_universe_frame(
    *,
    cache_dir: Path | None = None,
    retry_count: int = 1,
    retry_backoff_seconds: float = 0.5,
) -> UniverseSourceResult:
    frames: list[pd.DataFrame] = []
    source_rows: list[dict[str, object]] = []
    fetches = [
        (SEC_COMPANY_TICKERS_EXCHANGE_URL, "sec_company_tickers_exchange.json", parse_sec_company_tickers_exchange),
        (NASDAQ_LISTED_URL, "nasdaqlisted.txt", lambda text: parse_nasdaq_symbol_directory(text, source_name="nasdaq-trader-listed")),
        (NASDAQ_OTHER_LISTED_URL, "otherlisted.txt", lambda text: parse_nasdaq_symbol_directory(text, source_name="nasdaq-trader-otherlisted")),
    ]
    for url, cache_name, parser in fetches:
        text, source = _fetch_text_with_cache(url, cache_dir, cache_name, retry_count, retry_backoff_seconds)
        if text is None:
            source_rows.append({**source, "records": 0})
            continue
        frame = parser(text)
        frames.append(frame)
        source_rows.append({**source, "records": len(frame)})
    if not frames:
        packaged = load_packaged_universe_frame()
        return UniverseSourceResult(
            packaged,
            pd.DataFrame(
                [
                    {
                        "source": "packaged-default-universe",
                        "status": "fallback_after_public_source_failure",
                        "records": len(packaged),
                    },
                    *source_rows,
                ]
            ),
        )
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["is_etf", "symbol"], ascending=[False, True])
    combined = _clean_frame(combined)
    return UniverseSourceResult(combined, pd.DataFrame(source_rows))
