"""Liveness check: which of an actor's sites are actually up right now.

A dossier can list dozens of domains, but you can only report so many at once.
A live site is active harm (report first); a dead one is lower priority but
still evidence it existed. This sorts the leads so the urgent ones float up.

We judge liveness by the HTTP status the server returns:
- 2xx           -> LIVE     (up and serving)
- 401 / 403     -> BLOCKED  (server is up but refusing us - still active)
- 5xx           -> ERROR    (up but broken)
- 404 / 410     -> GONE     (server up, page removed)
- no response   -> DEAD     (connection refused / timeout / DNS gone)

CLI:
    python src/liveness.py example-site.net        # one domain
    python src/liveness.py dossier <account>      # every domain in a dossier
"""

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_DIR = ROOT / "data" / "dossiers"
REPORTS_DIR = ROOT / "reports"

# A browser-like User-Agent: some of these sites block obvious bot clients.
HEADERS = {"User-Agent": "Mozilla/5.0 (deepguard-observatory research)"}

REQUEST_DELAY_SECONDS = 0.5

# verdict -> (priority for reporting, lower = more urgent)
PRIORITY = {"LIVE": 0, "BLOCKED": 1, "ERROR": 2, "GONE": 3, "DEAD": 4}


def _verdict(status: int) -> str:
    if 200 <= status < 300:
        return "LIVE"
    if status in (401, 403):
        return "BLOCKED"
    if status in (404, 410):
        return "GONE"
    if status >= 500:
        return "ERROR"
    return "LIVE"  # other 2xx/3xx-after-redirect: treat as up


def check(url: str) -> dict:
    """Return {url, verdict, status, note} for one site."""
    if not url.startswith("http"):
        url = f"https://{url}"
    try:
        response = requests.get(
            url, headers=HEADERS, timeout=8, allow_redirects=True
        )
        return {
            "url": url,
            "verdict": _verdict(response.status_code),
            "status": response.status_code,
            "note": "",
        }
    except requests.RequestException as exc:
        # No response at all: refused, timed out, or the domain no longer resolves.
        return {
            "url": url,
            "verdict": "DEAD",
            "status": None,
            "note": type(exc).__name__,
        }


def _domains_from_dossier(account: str) -> list:
    path = DOSSIER_DIR / f"github_{account}.json"
    if not path.exists():
        raise SystemExit(f"No dossier at {path}. Run investigate.py first.")
    dossier = json.loads(path.read_text())
    domains = []
    for lead in dossier.get("leads", []):
        host = lead.split("//", 1)[-1].split("/", 1)[0]
        if host and host not in domains:
            domains.append(host)
    return domains


def check_dossier(account: str) -> Path:
    domains = _domains_from_dossier(account)
    print(f"Checking {len(domains)} site(s) from {account}'s dossier...")

    rows = []
    for index, domain in enumerate(domains):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        result = check(domain)
        rows.append(result)
        print(f"  {result['verdict']:8} {domain}"
              f"  (HTTP {result['status'] or result['note']})")

    # Sort so the sites worth reporting first are at the top.
    rows.sort(key=lambda r: (PRIORITY[r["verdict"]], r["url"]))

    live = sum(1 for r in rows if r["verdict"] in ("LIVE", "BLOCKED"))
    lines = [
        f"# Liveness triage — {account}",
        "",
        f"{live} of {len(rows)} sites are up. Report the LIVE ones first.",
        "",
        "| Priority | Verdict | Site | HTTP |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {PRIORITY[r['verdict']]} | {r['verdict']} | {r['url']} |"
            f" {r['status'] or r['note']} |"
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"triage-{account}.md"
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "dossier":
        out_path = check_dossier(args[1])
        print(f"Saved: {out_path}")
    elif len(args) == 1 and "." in args[0]:
        print(json.dumps(check(args[0]), indent=2, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
