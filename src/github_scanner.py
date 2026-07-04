"""Scans public GitHub repositories for deepfake-related keywords."""

import os
import time

import requests

KEYWORDS = [
    "deepfake",
    "faceswap",
    "nudify",
    "deepnude",
    "undress ai",
    "non consensual deepfake",
]

SEARCH_URL = "https://api.github.com/search/repositories"

# GitHub's search API allows 30 req/min authenticated, 10 req/min unauthenticated.
REQUEST_DELAY_SECONDS = 2


def _headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def scan_github(per_keyword_limit: int = 10) -> list[dict]:
    """Search public GitHub repos whose name/description/readme match KEYWORDS."""
    findings = []
    seen_ids = set()

    for index, keyword in enumerate(KEYWORDS):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        response = requests.get(
            SEARCH_URL,
            headers=_headers(),
            params={
                "q": f'"{keyword}" in:name,description,readme',
                "sort": "updated",
                "order": "desc",
                "per_page": per_keyword_limit,
            },
            timeout=15,
        )
        response.raise_for_status()

        for repo in response.json().get("items", []):
            repo_id = str(repo["id"])
            if repo_id in seen_ids:
                continue

            seen_ids.add(repo_id)
            findings.append(
                {
                    "source": "github",
                    "id": repo_id,
                    "title": repo["full_name"],
                    "body": repo.get("description") or "",
                    "url": repo["html_url"],
                    "created_utc": repo.get("created_at"),
                }
            )

    return findings
