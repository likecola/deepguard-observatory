"""Scans Civitai for models matching deepfake-related keywords.

Uses the public v1 API anonymously - no key required.
"""

import re
import time

import requests

KEYWORDS = [
    "deepfake",
    "faceswap",
    "face swap",
    "nudify",
    "deepnude",
    "undress",
]

SEARCH_URL = "https://civitai.com/api/v1/models"

REQUEST_DELAY_SECONDS = 2

# Civitai descriptions are HTML; keep only the text for analysis.
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text or "").strip()


def scan_civitai(per_keyword_limit: int = 10) -> list:
    """Search public Civitai models whose name/description match KEYWORDS."""
    findings = []
    seen_ids = set()

    for index, keyword in enumerate(KEYWORDS):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        response = requests.get(
            SEARCH_URL,
            params={"query": keyword, "limit": per_keyword_limit, "sort": "Newest"},
            timeout=20,
        )
        response.raise_for_status()

        for model in response.json().get("items", []):
            model_id = str(model.get("id", ""))
            if not model_id or model_id in seen_ids:
                continue

            seen_ids.add(model_id)
            tags = ", ".join(model.get("tags") or [])
            description = _strip_html(model.get("description"))[:1000]
            versions = model.get("modelVersions") or [{}]
            findings.append(
                {
                    "source": "civitai",
                    "id": model_id,
                    "title": model.get("name", ""),
                    "body": (
                        f"Type: {model.get('type', '')}\n"
                        f"Tags: {tags}\n"
                        f"{description}"
                    ).strip(),
                    "url": f"https://civitai.com/models/{model_id}",
                    "created_utc": versions[0].get("createdAt"),
                }
            )

    return findings
