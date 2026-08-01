"""Infrastructure enrichment: look up who registered a domain, and when.

Uses RDAP (the modern, JSON-over-HTTPS replacement for WHOIS) - no API key,
no extra dependency. When many domains share a registrar + registration window
+ nameservers, that's strong evidence they're run by the same operator.

CLI:
    python src/enrich.py example-site.net          # one domain
    python src/enrich.py dossier <account>        # every domain in a saved dossier
"""

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_DIR = ROOT / "data" / "dossiers"
REPORTS_DIR = ROOT / "reports"

# Some RDAP servers reject requests that don't identify themselves.
HEADERS = {"User-Agent": "deepguard-observatory/0.1 (research; contact via github)"}

# rdap.org is a bootstrap that redirects to the right registry for any TLD.
RDAP_BOOTSTRAP = "https://rdap.org/domain/{}"

REQUEST_DELAY_SECONDS = 1


def _registrar(entities: list) -> str:
    """Pull the registrar's name out of RDAP's nested entity/vcard structure."""
    for entity in entities:
        if "registrar" in entity.get("roles", []):
            for field in entity.get("vcardArray", ["vcard", []])[1]:
                if field[0] == "fn":
                    return field[3]
    return ""


def lookup_domain(domain: str) -> dict:
    """Return registration facts for one domain (empty fields if unavailable)."""
    result = {
        "domain": domain,
        "found": False,
        "registrar": "",
        "created": "",
        "expires": "",
        "nameservers": [],
        "error": "",
    }
    try:
        response = requests.get(
            RDAP_BOOTSTRAP.format(domain), headers=HEADERS, timeout=15
        )
        if response.status_code == 404:
            result["error"] = "not found in RDAP"
            return result
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        # Many TLDs (e.g. .ai) have no public RDAP server - that's expected.
        result["error"] = str(exc)[:80]
        return result

    events = {e["eventAction"]: e.get("eventDate", "") for e in data.get("events", [])}
    result.update(
        found=True,
        registrar=_registrar(data.get("entities", [])),
        created=events.get("registration", ""),
        expires=events.get("expiration", ""),
        nameservers=sorted(
            n.get("ldhName", "").lower() for n in data.get("nameservers", [])
        ),
    )
    return result


def _domains_from_dossier(account: str) -> list:
    path = DOSSIER_DIR / f"github_{account}.json"
    if not path.exists():
        raise SystemExit(f"No dossier at {path}. Run investigate.py first.")
    dossier = json.loads(path.read_text())
    domains = []
    for lead in dossier.get("leads", []):
        # leads look like "https://example.com" - keep just the host.
        host = lead.split("//", 1)[-1].split("/", 1)[0]
        if host and host not in domains:
            domains.append(host)
    return domains


def enrich_dossier(account: str) -> Path:
    domains = _domains_from_dossier(account)
    print(f"Enriching {len(domains)} domain(s) from {account}'s dossier...")

    rows = []
    for index, domain in enumerate(domains):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        info = lookup_domain(domain)
        rows.append(info)
        flag = "ok" if info["found"] else f"({info['error']})"
        print(f"  {domain}: {info['created'][:10] or '—'} {flag}")

    # Cluster hint: group by (registrar, first nameserver, registration month).
    lines = [
        f"# Infrastructure enrichment — {account}",
        "",
        "Domains sharing a registrar, registration month, and nameserver are",
        "likely the same operator.",
        "",
        "| Domain | Registered | Registrar | Nameserver |",
        "|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (x["registrar"], x["created"])):
        ns = r["nameservers"][0] if r["nameservers"] else "—"
        lines.append(
            f"| {r['domain']} | {r['created'][:10] or '—'} |"
            f" {r['registrar'] or '—'} | {ns} |"
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"enrichment-{account}.md"
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "dossier":
        out_path = enrich_dossier(args[1])
        print(f"Saved: {out_path}")
    elif len(args) == 1 and "." in args[0]:
        info = lookup_domain(args[0])
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
