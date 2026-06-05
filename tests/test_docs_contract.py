from pathlib import Path


def test_readme_and_methodology_qualify_recommendations_as_research_or_fresh_live_only():
    readme = Path("README.md").read_text(encoding="utf-8")
    methodology = Path("docs/methodology.md").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    disclaimers = Path("momentum_factor_lab/disclaimers.py").read_text(encoding="utf-8")
    combined = f"{readme}\n{methodology}\n{pyproject}\n{disclaimers}"

    assert "research_signals" in combined
    assert "zero weights" in combined or "weights are zeroed" in combined
    assert "Live tradable recommendations require `--selected-factor`" in readme
    assert "point-in-time universe evidence" in readme
    assert "liquidity evidence" in readme
    assert "capacity warnings" in combined
    assert "--target-aum" in readme
    assert "--max-adv-participation" in readme
    assert "--min-liquidity-observations" in readme
    assert "eligible symbols covering the requested stock price symbols" in methodology
    assert "current free/public live runs are intentionally research-only" in readme
    assert "Backtest portfolios are research diagnostics" in methodology
    assert "US individual stocks" in combined
    assert "ETFs are excluded from candidate holdings" in combined
    assert "Benchmark ETFs such as SPY" in combined
    assert "benchmark prices are comparator-only" in methodology
    assert "US stocks and ETFs" not in combined
    assert "stock/ETF universe" not in combined
    assert "1,000 ETFs" not in combined
