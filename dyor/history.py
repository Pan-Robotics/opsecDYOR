"""Score history — a token's score trajectory across persisted collection runs.

We persist the raw feature records per run (not the scores), so history is
computed by re-scoring each run's universe and pulling the token's final score.
That keeps the store schema-light and means history always reflects the *current*
scoring logic (re-tune weights → history updates).
"""

from __future__ import annotations

import math
from typing import Any

from dyor.pipeline import score_universe
from dyor.store import db


def score_history(
    con: Any, token: str, config: dict | None = None, *, peer_groups: bool = False
) -> list[tuple[Any, float]]:
    """[(collected_at, final_score)] for `token` across all runs, oldest first.

    Runs where the token has no (or a NaN) score are skipped.
    """
    out: list[tuple[Any, float]] = []
    for run_id, at in db.runs(con):
        records = db.records_for_run(con, run_id)
        results = score_universe(records, config, peer_groups=peer_groups)
        match = next((r for r in results if r.token == token), None)
        if match and not math.isnan(match.final_score):
            out.append((at, match.final_score))
    return out
