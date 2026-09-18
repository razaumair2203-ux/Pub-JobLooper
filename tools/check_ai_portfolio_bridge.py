"""Validate that public career-facing AI pages defer to the audited canonical portfolio."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "https://github.com/razaumair2203-ux/applied-ai-portfolio"

def main():
    ai = (ROOT / "AI-PORTFOLIO.md").read_text(encoding="utf-8")
    bridge = (ROOT / "portfolio" / "README.md").read_text(encoding="utf-8")
    lodestar = (ROOT / "portfolio" / "lodestar-rag.md").read_text(encoding="utf-8")
    tir = (ROOT / "portfolio" / "tir-fod-edge-ai.md").read_text(encoding="utf-8")

    assert CANONICAL in ai
    assert CANONICAL in bridge
    assert "1/34 top-5 expected-source misses (2.9%)" in ai
    assert "raw historical run logs and engine were not retained" in ai
    assert "team-developed" in ai
    assert "under revision" in ai
    assert "accepted/presented at IBCAST 2026" in ai
    assert "2.9% top-5 retrieval error" not in ai
    assert "Current headline state includes" in lodestar
    assert "author-confirmed ten-run historical summaries" in tir
    assert "duplication caused" in lodestar.lower()
    assert "duplication caused" in tir.lower()
    print("Public AI portfolio bridge validation passed")

if __name__ == "__main__":
    main()
