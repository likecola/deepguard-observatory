"""Shared-analytics clustering: link sites by the tracking IDs baked into them.

Different sites can hide behind different registrars and nameservers, but an
operator usually reuses the same Google Analytics / AdSense / Tag Manager /
Facebook Pixel account across all of them. Those IDs sit in the page HTML, so
two domains sharing one are almost certainly the same operator.

CLI:
    python src/analytics.py example-site.net        # one site's IDs
    python src/analytics.py dossier <account>       # cluster a dossier's domains
"""

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_DIR = ROOT / "data" / "dossiers"
REPORTS_DIR = ROOT / "reports"

HEADERS = {"User-Agent": "Mozilla/5.0 (deepguard-observatory research)"}
REQUEST_DELAY_SECONDS = 0.5

# label -> regex for the tracking IDs we can read out of page HTML.
ID_PATTERNS = {
    "GA4": re.compile(r"\bG-[A-Z0-9]{7,}\b"),
    "UA": re.compile(r"\bUA-\d{4,10}-\d{1,4}\b"),
    "GTM": re.compile(r"\bGTM-[A-Z0-9]{5,}\b"),
    "ADSENSE": re.compile(r"\bca-pub-\d{10,20}\b"),
    "FBPIXEL": re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{6,})['\"]"),
}


def fetch_ids(domain: str) -> set:
    """Return a set of 'LABEL:id' tracking IDs found on the site's homepage."""
    url = domain if domain.startswith("http") else f"https://{domain}"
    try:
        html = requests.get(url, headers=HEADERS, timeout=10,
                            allow_redirects=True).text
    except requests.RequestException:
        return set()

    ids = set()
    for label, pattern in ID_PATTERNS.items():
        for match in pattern.findall(html):
            ids.add(f"{label}:{match}")
    return ids


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


def cluster_dossier(account: str) -> Path:
    domains = _domains_from_dossier(account)
    print(f"Reading tracking IDs from {len(domains)} site(s) in {account}...")

    id_to_domains = defaultdict(set)
    domain_ids = {}
    for index, domain in enumerate(domains):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        ids = fetch_ids(domain)
        domain_ids[domain] = ids
        for tracking_id in ids:
            id_to_domains[tracking_id].add(domain)
        print(f"  {domain}: {len(ids)} id(s)")

    # A cluster is a tracking ID shared by 2+ domains = same operator.
    clusters = {tid: doms for tid, doms in id_to_domains.items() if len(doms) >= 2}

    lines = [
        f"# Shared-analytics clusters — {account}",
        "",
        f"{len(clusters)} tracking ID(s) shared across 2+ sites "
        f"(strong same-operator signal).",
        "",
        "## Clusters (shared tracking ID → sites)",
        "",
    ]
    if clusters:
        for tid, doms in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"- **{tid}** — {len(doms)} sites:")
            lines += [f"    - {d}" for d in sorted(doms)]
    else:
        lines.append("_No tracking IDs were shared across sites "
                     "(or pages were JS-rendered / blocked)._")

    lines += ["", "## Per-site IDs", "", "| Site | Tracking IDs |", "|---|---|"]
    for domain in domains:
        ids = ", ".join(sorted(domain_ids[domain])) or "—"
        lines.append(f"| {domain} | {ids} |")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"analytics-{account}.md"
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "dossier":
        out_path = cluster_dossier(args[1])
        print(f"Saved: {out_path}")
    elif len(args) == 1 and "." in args[0]:
        print(sorted(fetch_ids(args[0])) or "no tracking IDs found")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
