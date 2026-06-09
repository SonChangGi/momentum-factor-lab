from pathlib import Path

from momentum_factor_lab.factors import FACTOR_SPECS


def test_readme_and_methodology_qualify_recommendations_as_research_or_fresh_live_only():
    readme = Path("README.md").read_text(encoding="utf-8")
    methodology = Path("docs/methodology.md").read_text(encoding="utf-8")
    factor_catalog = Path("docs/factor-catalog.md").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    disclaimers = Path("momentum_factor_lab/disclaimers.py").read_text(encoding="utf-8")
    combined = f"{readme}\n{methodology}\n{factor_catalog}\n{pyproject}\n{disclaimers}"

    assert "execution_limitations" in combined
    assert "recommendations" in combined
    assert "data_quality" in combined
    assert "--data-quality-lookback-days" in readme
    assert "--max-price-missing-ratio" in readme
    assert "--max-volume-missing-ratio" in readme
    assert "--max-extreme-daily-return" in readme
    assert "source=... as_of=YYYY-MM-DD symbol_count=... hash=..." in readme
    assert "Stooq fallback rows" in methodology
    assert "factor_validation" in combined
    assert "factor_score_history_top20" in combined
    assert "primary `recommendations`" in combined
    assert "row-level liquidity/capacity" in combined
    assert "`--max-price-symbols` is still available for explicit smoke/debug runs" in readme
    assert "FinanceDataReader fallback" in readme
    assert "point-in-time universe evidence" in readme
    assert "liquidity evidence" in readme
    assert "capacity warnings" in combined
    assert "--target-aum" in readme
    assert "--max-adv-participation" in readme
    assert "--min-liquidity-observations" in readme
    assert "no explicit price-symbol cap" in methodology
    assert "complete requested price coverage" in methodology
    assert "hard price-integrity checks" in methodology
    assert "Stooq daily CSV is the first fallback" in methodology
    assert "FinanceDataReader is an optional second fallback" in methodology
    assert "docs/factor-catalog.md" in readme
    assert "Total factors: **55**" in factor_catalog
    assert "Full factor definitions" in factor_catalog
    assert "US individual stocks" in combined
    assert "ETFs are excluded from candidate holdings" in combined
    assert "Benchmark ETFs such as SPY" in combined
    assert "benchmark prices are comparator-only" in methodology
    assert "US stocks and ETFs" not in combined
    assert "stock/ETF universe" not in combined
    assert "1,000 ETFs" not in combined
    assert "http://www.nasdaqtrader.com" not in combined
    assert "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt" in readme
    assert "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt" in readme


def test_factor_catalog_documents_every_factor_spec():
    factor_catalog = Path("docs/factor-catalog.md").read_text(encoding="utf-8")

    assert f"Total factors: **{len(FACTOR_SPECS)}**" in factor_catalog
    for spec in FACTOR_SPECS.values():
        assert f"`{spec.name}`" in factor_catalog
        assert spec.category in factor_catalog
        assert spec.formula.replace("|", "\\|") in factor_catalog
        assert spec.description in factor_catalog
        assert spec.validation_notes in factor_catalog
