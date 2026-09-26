"""GitHub client — developer activity (an early narrative signal).

60 req/hr unauthenticated vs 5000 req/hr with a token (set DYOR_GITHUB_TOKEN).
Pair with Electric Capital's taxonomy to scope which repos belong to which
ecosystem before hitting these endpoints.
"""

from __future__ import annotations

from typing import Any

import httpx

from dyor.config import get_settings
from dyor.ingestion.base import BaseClient


class GitHubClient(BaseClient):
    name = "github"
    default_rate_per_min = 80.0  # 5000/hr authed

    # Unauthenticated GitHub is 60 requests per HOUR. Pacing at the configured
    # authed rate without a token would 403 as soon as the target list grew.
    UNAUTHED_RATE_PER_MIN = 1.0

    def __init__(self, config: dict | None = None, **kwargs) -> None:
        if not get_settings().github_token and "rate_per_min" not in kwargs:
            kwargs["rate_per_min"] = self.UNAUTHED_RATE_PER_MIN
        super().__init__(config, **kwargs)
        self.base_url = self.config["ingestion"]["sources"]["github"]["base_url"]

    def default_headers(self) -> dict[str, str]:
        headers = super().default_headers()
        headers["Accept"] = "application/vnd.github+json"
        token = get_settings().github_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def repo(self, owner: str, name: str) -> dict[str, Any]:
        """Stars, forks, open issues, pushed_at — basic repo health."""
        return self.get_json(f"{self.base_url}/repos/{owner}/{name}")

    def contributors(self, owner: str, name: str, per_page: int = 100) -> list[dict[str, Any]]:
        return self.get_json(
            f"{self.base_url}/repos/{owner}/{name}/contributors",
            params={"per_page": per_page, "anon": "false"},
        )

    def weekly_commit_activity(self, owner: str, name: str) -> list[dict[str, Any]]:
        """52 weeks of commit counts — the 'is the team still shipping?' signal.

        Note: GitHub computes this asynchronously and may return 202 (empty) on a
        cold cache; callers should tolerate an empty list.
        """
        return self.get_json(
            f"{self.base_url}/repos/{owner}/{name}/stats/commit_activity"
        )

    def org_latest_push(self, org: str) -> str | None:
        """ISO timestamp of the most recent push across an org's repos.

        A robust, single-call org-level 'is the team active?' signal — avoids
        having to know the exact canonical repo (what Electric Capital's taxonomy
        otherwise resolves). Returns None if the org has no repos.
        """
        repos = self.get_json(
            f"{self.base_url}/orgs/{org}/repos",
            params={"sort": "pushed", "direction": "desc", "per_page": 1},
        )
        return repos[0]["pushed_at"] if repos else None

    def account_latest_push(self, name: str) -> str | None:
        """`org_latest_push` for an account that may be a *user* rather than an
        org. CoinGecko and DefiLlama list both without distinction (convex-eth,
        resupplyfi, xvi10/GMX …) and `/orgs/{name}` answers 404 for a user, which
        used to read as "no repos". Returns None only when neither has repos
        (e.g. `makerdao` after the move to `sky-ecosystem`)."""
        try:
            return self.org_latest_push(name)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        repos = self.get_json(
            f"{self.base_url}/users/{name}/repos",
            params={"sort": "pushed", "direction": "desc", "per_page": 1},
        )
        return repos[0]["pushed_at"] if repos else None
