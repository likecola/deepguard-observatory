"""Recursive pivoting: follow one account's leads out to the wider network.

Starting from a single account, this walks outward — the account's promoted
domains -> other GitHub accounts that also reference those domains -> their
domains -> ... — mapping a network of actors instead of just one.

Two safety rails keep it from running away:
- a *visited* set, so the same account is never investigated twice (no loops)
- *depth* and *account* caps, so one crawl can't spider all of GitHub or blow
  through the API rate limit

It reuses investigate.build_dossier() to profile each account.

CLI:
    python src/pivot.py github <account>          # defaults: depth 1, 6 accounts
    python src/pivot.py github <account> 2 8      # depth 2, up to 8 accounts
"""

import json
import sys
import time
from collections import deque
from pathlib import Path

import requests

import investigate  # reuse the dossier builder + its helpers

ROOT = Path(__file__).resolve().parent.parent
NETWORK_DIR = ROOT / "data" / "networks"
REPORTS_DIR = ROOT / "reports"

SEARCH_URL = "https://api.github.com/search/repositories"
# GitHub's search API allows ~10 req/min unauthenticated; one search per domain.
SEARCH_DELAY_SECONDS = 6
# Only pivot on a sample of each account's domains, to bound API calls.
MAX_DOMAINS_PER_ACCOUNT = 5

# Generic domains that everyone references — pivoting on these links totally
# unrelated (and usually legitimate) accounts, so they are skipped.
GENERIC_DOMAINS = {
    "github.com", "gitlab.com", "bitbucket.org", "godoc.org", "pkg.go.dev",
    "npmjs.com", "pypi.org", "medium.com", "dev.to",
    "google.com", "youtube.com", "youtu.be", "twitter.com", "x.com",
    "facebook.com", "instagram.com", "linkedin.com", "reddit.com",
    "wikipedia.org", "stackoverflow.com", "discord.gg", "discord.com",
    "t.me", "telegram.me", "patreon.com", "paypal.com", "buymeacoffee.com",
    "hacktricks.xyz", "book.hacktricks.xyz",
}


def _is_generic(domain: str) -> bool:
    d = domain.lower()
    if d.startswith("www."):
        d = d[4:]
    if d.endswith((".github.io", ".readthedocs.io", ".gitbook.io", ".medium.com")):
        return True
    return d in GENERIC_DOMAINS


def related_accounts(domain: str, exclude: set) -> set:
    """Other GitHub accounts whose repos reference this domain."""
    response = requests.get(
        SEARCH_URL,
        headers=investigate._headers(),
        params={"q": f'"{domain}" in:name,description,readme', "per_page": 10},
        timeout=15,
    )
    response.raise_for_status()
    owners = set()
    for repo in response.json().get("items", []):
        owner = repo["owner"]["login"]
        if owner not in exclude:
            owners.add(owner)
    return owners


def crawl(start: str, max_depth: int = 1, max_accounts: int = 6) -> dict:
    visited = set()
    queue = deque([(start, 0)])
    nodes = {}   # account -> {depth, domains}
    edges = []   # {"from": account, "via": domain, "to": account}

    while queue and len(visited) < max_accounts:
        account, depth = queue.popleft()
        if account in visited:
            continue
        visited.add(account)

        dossier = investigate.build_dossier("github", account)
        domains = sorted(
            {investigate._domain(lead) for lead in dossier.get("leads", [])
             if investigate._domain(lead) and not _is_generic(investigate._domain(lead))}
        )
        nodes[account] = {"depth": depth, "domains": len(domains)}
        print(f"[depth {depth}] {account}: {len(domains)} distinctive domain(s)")

        if depth >= max_depth:
            continue

        for domain in domains[:MAX_DOMAINS_PER_ACCOUNT]:
            time.sleep(SEARCH_DELAY_SECONDS)
            try:
                found = related_accounts(domain, visited)
            except requests.RequestException as exc:
                print(f"  search failed for {domain}: {exc}")
                continue
            for other in found:
                edges.append({"from": account, "via": domain, "to": other})
                already_queued = other in {a for a, _ in queue}
                room = len(visited) + len(queue) < max_accounts
                if other not in visited and not already_queued and room:
                    queue.append((other, depth + 1))
                    print(f"    -> found related account: {other} (via {domain})")

    return {"start": start, "nodes": nodes, "edges": edges}


def save(network: dict) -> tuple:
    NETWORK_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = network["start"]

    json_path = NETWORK_DIR / f"{start}.json"
    json_path.write_text(json.dumps(network, indent=2, ensure_ascii=False) + "\n")

    lines = [
        f"# Network map — from {start}",
        "",
        f"{len(network['nodes'])} accounts, {len(network['edges'])} connections.",
        "",
        "## Accounts",
        "",
        "| Account | Depth | Domains |",
        "|---|---|---|",
    ]
    for account, info in sorted(network["nodes"].items(),
                                key=lambda kv: (kv[1]["depth"], kv[0])):
        lines.append(f"| {account} | {info['depth']} | {info['domains']} |")

    lines += ["", "## Connections (shared domains link actors)", ""]
    if network["edges"]:
        for e in network["edges"]:
            lines.append(f"- `{e['from']}` — {e['via']} — `{e['to']}`")
    else:
        lines.append("_No shared-domain links to other accounts found._")

    md_path = REPORTS_DIR / f"network-{start}.md"
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path


def main() -> None:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "github":
        account = args[1]
        max_depth = int(args[2]) if len(args) > 2 else 1
        max_accounts = int(args[3]) if len(args) > 3 else 6
        print(f"Crawling from {account} (depth {max_depth}, max {max_accounts} accounts)...")
        network = crawl(account, max_depth, max_accounts)
        json_path, md_path = save(network)
        print(f"Mapped {len(network['nodes'])} account(s), "
              f"{len(network['edges'])} connection(s).")
        print(f"Saved: {json_path}\n       {md_path}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
