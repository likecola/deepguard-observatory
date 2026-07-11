"""Searches the open web for deepfake services via Google Programmable Search.

Requires GOOGLE_API_KEY and GOOGLE_CSE_ID (see .env.example).
Free tier: 100 queries/day - QUERIES is kept short on purpose.
"""

import os
import time

import requests

QUERIES = [
    "nudify app",
    "deepnude generator",
    "undress ai app",
    "deepfake nude tool",
]

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

REQUEST_DELAY_SECONDS = 1


def scan_google_cse(per_query_limit: int = 10) -> list:
    """Search the web for QUERIES; each result URL becomes one candidate."""
    api_key = os.environ["GOOGLE_API_KEY"]
    cse_id = os.environ["GOOGLE_CSE_ID"]

    findings = []
    seen_urls = set()

    for index, query in enumerate(QUERIES):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        response = requests.get(
            SEARCH_URL,
            params={
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "num": min(per_query_limit, 10),  # API max is 10 per request
            },
            timeout=15,
        )
        response.raise_for_status()

        for item in response.json().get("items", []):
            link = item.get("link", "")
            if not link or link in seen_urls:
                continue

            seen_urls.add(link)
            findings.append(
                {
                    "source": "google",
                    "id": link,
                    "title": item.get("title", ""),
                    "body": item.get("snippet", ""),
                    "url": link,
                    "created_utc": None,
                }
            )

    return findings
