"""Actor investigation: pivot from one finding to a profile of the person behind it.

Given a GitHub account (directly, or via a finding key), this pulls together a
"dossier" from public sources only - legal OSINT, no authentication beyond an
optional read-only GitHub token:

- the account's profile (bio, blog, linked socials, email, location, join date)
- every public repo, with the deepfake-related ones highlighted
- external links harvested from the bio and repo homepages/descriptions
  (these are the leads: the sites and services the actor is promoting)
- cross-platform presence: models published under the same username on
  Hugging Face
- suggested pivots: other usernames and domains worth investigating next

Output:
    data/dossiers/<source>_<account>.json   structured dossier
    reports/dossier-<source>-<account>.md    readable investigator's file

CLI:
    python src/investigate.py github <username>   # investigate an account
    python src/investigate.py <finding-key>       # e.g. github:12345
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
FINDINGS_PATH = ROOT / "data" / "findings.json"
DOSSIER_DIR = ROOT / "data" / "dossiers"
REPORTS_DIR = ROOT / "reports"

GITHUB_API = "https://api.github.com"
HF_MODELS_API = "https://huggingface.co/api/models"

# Keywords that mark a repo/model as relevant to this investigation.
FLAG_KEYWORDS = (
    "deepfake",
    "faceswap",
    "face swap",
    "face-swap",
    "nudify",
    "deepnude",
    "undress",
    "nsfw",
    "swap",
)

_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")

# Some actors name each repo after the domain they promote (e.g. "example-site.net").
# Match a repo name that is itself a domain: label(s) + a plausible TLD.
_DOMAIN_NAME_RE = re.compile(
    r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|ai|nl|eu|co|xyz|app|site|online)$",
    re.IGNORECASE,
)


def _headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _flagged(*texts: str) -> bool:
    haystack = " ".join(t for t in texts if t).lower()
    return any(kw in haystack for kw in FLAG_KEYWORDS)


def _find_urls(*texts: str) -> list:
    urls = []
    for text in texts:
        if text:
            urls += _URL_RE.findall(text)
    return urls


def github_profile(username: str) -> dict:
    response = requests.get(
        f"{GITHUB_API}/users/{username}", headers=_headers(), timeout=15
    )
    if response.status_code == 404:
        return {"_missing": True}
    response.raise_for_status()
    return response.json()


def github_repos(username: str) -> list:
    repos = []
    page = 1
    while True:
        response = requests.get(
            f"{GITHUB_API}/users/{username}/repos",
            headers=_headers(),
            params={"per_page": 100, "sort": "pushed", "page": page},
            timeout=15,
        )
        if response.status_code == 404:
            break
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    return repos


def huggingface_models(username: str) -> list:
    """Models published under the same username on Hugging Face (if any)."""
    try:
        response = requests.get(
            HF_MODELS_API,
            params={"author": username, "limit": 50},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


def build_dossier(source: str, account: str) -> dict:
    if source != "github":
        raise SystemExit(f"Investigation currently supports GitHub accounts only (got {source!r}).")

    profile = github_profile(account)
    if profile.get("_missing"):
        return {
            "source": source,
            "account": account,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "note": "GitHub account not found (deleted, renamed, or suspended).",
            "profile": {},
            "repos": [],
            "flagged_repos": [],
            "leads": [],
            "cross_platform": {},
            "pivots": [],
        }

    repos = github_repos(account)

    # Harvest leads: external links from the bio and every repo's homepage/description.
    leads = set(_find_urls(profile.get("bio"), profile.get("blog")))
    flagged_repos = []
    repo_rows = []
    for repo in repos:
        name = repo.get("name") or ""
        desc = repo.get("description") or ""
        homepage = repo.get("homepage") or ""
        is_flagged = _flagged(name, desc)
        leads.update(_find_urls(desc, homepage))
        if homepage.startswith("http"):
            leads.add(homepage)
        # A repo named after a domain is itself a lead (this actor's whole
        # operation is naming one repo per promoted site).
        if _DOMAIN_NAME_RE.match(name):
            leads.add(f"https://{name}")

        row = {
            "name": repo.get("full_name", ""),
            "description": desc,
            "homepage": homepage,
            "stars": repo.get("stargazers_count", 0),
            "created_at": repo.get("created_at"),
            "pushed_at": repo.get("pushed_at"),
            "flagged": is_flagged,
        }
        repo_rows.append(row)
        if is_flagged:
            flagged_repos.append(row)

    hf_models = huggingface_models(account)

    # Suggested pivots: linked socials, and domains extracted from leads.
    pivots = []
    if profile.get("twitter_username"):
        pivots.append(f"twitter:{profile['twitter_username']}")
    if profile.get("email"):
        pivots.append(f"email:{profile['email']}")
    domains = sorted({_domain(u) for u in leads if _domain(u)})
    pivots += [f"domain:{d}" for d in domains]

    return {
        "source": source,
        "account": account,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "profile": {
            "name": profile.get("name"),
            "bio": profile.get("bio"),
            "company": profile.get("company"),
            "location": profile.get("location"),
            "blog": profile.get("blog"),
            "twitter_username": profile.get("twitter_username"),
            "email": profile.get("email"),
            "public_repos": profile.get("public_repos"),
            "followers": profile.get("followers"),
            "created_at": profile.get("created_at"),
            "html_url": profile.get("html_url"),
        },
        "repos": repo_rows,
        "flagged_repos": flagged_repos,
        "leads": sorted(leads),
        "cross_platform": {
            "huggingface_models": [
                {"id": m.get("id"), "url": f"https://huggingface.co/{m.get('id')}"}
                for m in hf_models
            ]
        },
        "pivots": pivots,
    }


def _domain(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url or "")
    return match.group(1).lower() if match else ""


def save_dossier(dossier: dict) -> tuple:
    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{dossier['source']}_{dossier['account']}"
    json_path = DOSSIER_DIR / f"{stem}.json"
    json_path.write_text(json.dumps(dossier, indent=2, ensure_ascii=False) + "\n")

    md_path = REPORTS_DIR / f"dossier-{dossier['source']}-{dossier['account']}.md"
    md_path.write_text(render_markdown(dossier))
    return json_path, md_path


def render_markdown(d: dict) -> str:
    p = d["profile"]
    lines = [
        f"# Dossier — {d['source']}:{d['account']}",
        "",
        f"_Generated {d['generated']} from public sources (OSINT)._",
        "",
    ]
    if d.get("note"):
        lines += [f"> **Note:** {d['note']}", ""]
        return "\n".join(lines) + "\n"

    lines += [
        "## Identity",
        "",
        f"- Profile: {p.get('html_url')}",
        f"- Name: {p.get('name') or '—'}",
        f"- Bio: {p.get('bio') or '—'}",
        f"- Company: {p.get('company') or '—'}",
        f"- Location: {p.get('location') or '—'}",
        f"- Blog/site: {p.get('blog') or '—'}",
        f"- Twitter/X: {('@' + p['twitter_username']) if p.get('twitter_username') else '—'}",
        f"- Public email: {p.get('email') or '—'}",
        f"- Account created: {p.get('created_at') or '—'}",
        f"- Public repos: {p.get('public_repos')} | Followers: {p.get('followers')}",
        "",
        "## Flagged repositories",
        "",
    ]
    if d["flagged_repos"]:
        lines += ["| Repo | Description | Homepage | Created |", "|---|---|---|---|"]
        for r in d["flagged_repos"]:
            desc = (r["description"] or "").replace("|", "\\|")[:60]
            lines.append(
                f"| [{r['name']}](https://github.com/{r['name']}) | {desc} |"
                f" {r['homepage'] or '—'} | {(r['created_at'] or '')[:10]} |"
            )
    else:
        lines.append("_None of the account's repos matched the keyword filter._")

    lines += ["", "## Leads (external links harvested)", ""]
    if d["leads"]:
        lines += [f"- {url}" for url in d["leads"]]
    else:
        lines.append("_No external links found._")

    hf = d["cross_platform"]["huggingface_models"]
    lines += ["", "## Cross-platform presence", ""]
    if hf:
        lines += [f"- Hugging Face model: [{m['id']}]({m['url']})" for m in hf]
    else:
        lines.append("_No Hugging Face models under this username._")

    lines += ["", "## Suggested pivots (investigate next)", ""]
    if d["pivots"]:
        lines += [f"- `{pivot}`" for pivot in d["pivots"]]
    else:
        lines.append("_No obvious pivots._")

    lines += [
        "",
        "## All public repos",
        "",
        "| Repo | Flagged | Stars | Pushed |",
        "|---|---|---|---|",
    ]
    for r in sorted(d["repos"], key=lambda x: x["pushed_at"] or "", reverse=True):
        lines.append(
            f"| [{r['name']}](https://github.com/{r['name']}) |"
            f" {'⚑' if r['flagged'] else ''} | {r['stars']} |"
            f" {(r['pushed_at'] or '')[:10]} |"
        )

    lines += ["", "---", "", "_All data is public. This dossier is for reporting to "
              "official platform channels, not for contacting or confronting anyone._", ""]
    return "\n".join(lines)


def _account_from_finding(key: str) -> tuple:
    findings = json.loads(FINDINGS_PATH.read_text()) if FINDINGS_PATH.exists() else {}
    if key not in findings:
        raise SystemExit(f"No finding with key {key!r}.")
    finding = findings[key]
    source = finding.get("source", "")
    # GitHub finding titles are "owner/repo"; the owner is the account.
    title = finding.get("title", "")
    account = title.split("/")[0] if "/" in title else title
    return source, account


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] in ("github",):
        source, account = args[0], args[1]
    elif len(args) == 1 and ":" in args[0]:
        source, account = _account_from_finding(args[0])
    else:
        raise SystemExit(__doc__)

    print(f"Investigating {source}:{account} ...")
    dossier = build_dossier(source, account)
    json_path, md_path = save_dossier(dossier)
    print(f"Flagged repos: {len(dossier['flagged_repos'])} | "
          f"Leads: {len(dossier['leads'])} | "
          f"HF models: {len(dossier['cross_platform']['huggingface_models'])} | "
          f"Pivots: {len(dossier['pivots'])}")
    print(f"Saved: {json_path}")
    print(f"       {md_path}")


if __name__ == "__main__":
    main()
