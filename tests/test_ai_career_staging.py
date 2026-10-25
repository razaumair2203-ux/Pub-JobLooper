"""AI career promotion package must remain staged until governed truth review."""
from __future__ import annotations

import json
from pathlib import Path

from core import store

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".joblooper" / "truth" / "user_confirmed_ai_profile_2026-09-18.jsonl"
PLAN = ROOT / ".joblooper" / "truth" / "AI_CAREER_TRUTH_PROMOTION_2026-09-18.md"


def test_ai_promotion_package_is_complete_but_non_authoritative():
    rows = [json.loads(line) for line in STAGING.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 7
    assert all(row["status"] == "USER_REQUESTED_PENDING_CANONICAL_PROMOTION"
               for row in rows)

    # Critical safety invariant: staging evidence exists under .joblooper/truth,
    # but generation authority is the explicit _TRUTH_CONTEXT_FILES allowlist.
    rel = "truth/user_confirmed_ai_profile_2026-09-18.jsonl"
    assert rel not in store._TRUTH_CONTEXT_FILES

    payload = STAGING.read_text(encoding="utf-8")
    assert "applied_ai" in payload
    assert "AI-LODESTAR-001" in payload
    assert "AI-TIRFOD-001" in payload
    assert "AI-CLEARRUN-001" in payload
    assert "AI-CODEX-ARL-001" in payload
    assert "AI-JOBLOOPER-001" in payload
    assert "accepted/presented at IBCAST 2026" in payload
    assert "IEEE Xplore or DOI claim until independently verified" in payload
    assert "400+ professionals" not in payload

    plan = PLAN.read_text(encoding="utf-8")
    assert "without altering signed candidate truth" in plan
    assert "18+ years" in plan
    assert "user reviews the changed truth digest" in plan
