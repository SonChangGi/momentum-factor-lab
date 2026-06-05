from pathlib import Path


def test_readme_and_methodology_qualify_recommendations_as_research_or_fresh_live_only():
    readme = Path("README.md").read_text(encoding="utf-8")
    methodology = Path("docs/methodology.md").read_text(encoding="utf-8")
    combined = f"{readme}\n{methodology}"

    assert "research_signals" in combined
    assert "zero weights" in combined or "weights are zeroed" in combined
    assert "Live tradable recommendations require `--selected-factor`" in readme
    assert "point-in-time universe evidence" in readme
    assert "liquidity evidence" in readme
    assert "capacity warnings" in combined
    assert "--target-aum" in readme
    assert "--max-adv-participation" in readme
    assert "--min-liquidity-observations" in readme
    assert "eligible symbols covering the requested price symbols" in methodology
    assert "current free/public live runs are intentionally research-only" in readme
    assert "Backtest portfolios are research diagnostics" in methodology
