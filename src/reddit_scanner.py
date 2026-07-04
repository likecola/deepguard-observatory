"""Scans a fixed set of subreddits for posts matching deepfake-related keywords."""

import os

import praw

KEYWORDS = [
    "deepfake",
    "deep fake",
    "faceswap",
    "face swap",
    "nudify",
    "deepnude",
    "undress ai",
    "non consensual",
    "nonconsensual",
]

SUBREDDITS = [
    "deepfakes",
    "MachineLearning",
    "StableDiffusion",
    "artificial",
]


def _build_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent="deepguard-observatory/0.1 (monitoring bot)",
    )


def scan_reddit(limit_per_subreddit: int = 25) -> list[dict]:
    """Scan configured subreddits for new posts whose title/body match KEYWORDS."""
    reddit = _build_reddit_client()
    reddit.read_only = True

    findings = []
    seen_ids = set()

    for subreddit_name in SUBREDDITS:
        subreddit = reddit.subreddit(subreddit_name)
        for post in subreddit.new(limit=limit_per_subreddit):
            if post.id in seen_ids:
                continue

            haystack = f"{post.title}\n{post.selftext}".lower()
            if not any(keyword in haystack for keyword in KEYWORDS):
                continue

            seen_ids.add(post.id)
            findings.append(
                {
                    "source": "reddit",
                    "id": post.id,
                    "subreddit": subreddit_name,
                    "title": post.title,
                    "body": post.selftext,
                    "url": f"https://reddit.com{post.permalink}",
                    "created_utc": post.created_utc,
                }
            )

    return findings
