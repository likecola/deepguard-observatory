"""Scans Hugging Face Hub (models and spaces) for deepfake-related keywords.

Uses the public Hub API anonymously - no token required.
"""

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

MODELS_URL = "https://huggingface.co/api/models"
SPACES_URL = "https://huggingface.co/api/spaces"

REQUEST_DELAY_SECONDS = 1


def _search(url: str, keyword: str, limit: int) -> list:
    response = requests.get(
        url,
        params={"search": keyword, "limit": limit},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def scan_huggingface(per_keyword_limit: int = 10) -> list:
    """Search public HF models and spaces whose name/tags match KEYWORDS."""
    findings = []
    seen_ids = set()

    targets = [
        ("model", MODELS_URL, "https://huggingface.co/{}"),
        ("space", SPACES_URL, "https://huggingface.co/spaces/{}"),
    ]

    first_request = True
    for kind, url, link_format in targets:
        for keyword in KEYWORDS:
            if not first_request:
                time.sleep(REQUEST_DELAY_SECONDS)
            first_request = False

            for item in _search(url, keyword, per_keyword_limit):
                repo_id = item.get("id", "")
                key = f"{kind}:{repo_id}"
                if not repo_id or key in seen_ids:
                    continue

                seen_ids.add(key)
                tags = ", ".join(item.get("tags") or [])
                pipeline = item.get("pipeline_tag") or ""
                findings.append(
                    {
                        "source": "huggingface",
                        "id": key,
                        "title": f"{kind}: {repo_id}",
                        "body": f"Pipeline: {pipeline}\nTags: {tags}".strip(),
                        "url": link_format.format(repo_id),
                        "created_utc": item.get("createdAt"),
                    }
                )

    return findings
