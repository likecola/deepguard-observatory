"""Certificate-transparency signal: find sibling domains via shared TLS certs.

Every HTTPS certificate is logged publicly (Certificate Transparency). crt.sh
lets us query those logs for free. Two useful things fall out:
- when a domain's first certificate appeared (≈ when the site launched)
- other domains that appear on the *same* certificate (a same-operator signal,
  since an operator often puts several of their domains on one cert)

Caveat: Cloudflare and other CDNs sometimes bundle unrelated customers onto one
cert, so treat CDN-issued sibling matches as weak (flagged in the output).

    python src/certs.py example-site.net       # one domain
    python src/certs.py dossier <account>      # every domain in a dossier
"""

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_DIR = ROOT / "data" / "dossiers"
REPORTS_DIR = ROOT / "reports"

HEADERS = {"User-Agent": "deepguard-observatory/0.1 (research; contact via github)"}
CRT_SH = "https://crt.sh/"
REQUEST_DELAY_SECONDS = 2


def fetch_certs(domain: str) -> dict:
    """Query crt.sh for a domain. Returns issuer(s), earliest cert, siblings."""
    result = {"domain": domain, "issuers": set(), "earliest": "",
              "siblings": set(), "error": ""}
    try:
        response = requests.get(
            CRT_SH, params={"q": domain, "output": "json"},
            headers=HEADERS, timeout=25,
        )
        response.raise_for_status()
        certs = response.json()
    except (requests.RequestException, ValueError) as exc:
        # crt.sh is often slow or returns non-JSON under load; fail soft.
        result["error"] = str(exc)[:80]
        return result

    dates = []
    for cert in certs:
        result["issuers"].add((cert.get("issuer_name") or "").split(", ")[-1][:40])
        if cert.get("not_before"):
            dates.append(cert["not_before"][:10])
        # name_value holds the cert's SAN entries, newline-separated.
        for name in (cert.get("name_value") or "").split("\n"):
            name = name.strip().lower()
            if name and not name.startswith("*.") and not name.endswith(domain):
                result["siblings"].add(name)
    if dates:
        result["earliest"] = min(dates)
    return result


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


def certs_dossier(account: str) -> Path:
    domains = _domains_from_dossier(account)
    print(f"Querying certificate transparency for {len(domains)} domain(s)...")

    rows = []
    for index, domain in enumerate(domains):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        info = fetch_certs(domain)
        rows.append(info)
        note = info["error"] or f"{len(info['siblings'])} sibling(s)"
        print(f"  {domain}: first {info['earliest'] or '—'} | {note}")

    lines = [
        f"# Certificate transparency — {account}",
        "",
        "Sibling = another domain sharing a certificate (possible same operator).",
        "CDN-issued certs can bundle unrelated domains, so weigh these with other",
        "signals (registrar, nameserver, analytics ID).",
        "",
        "| Domain | First cert | Issuer | Siblings |",
        "|---|---|---|---|",
    ]
    for r in rows:
        issuer = next(iter(r["issuers"]), "—") if r["issuers"] else "—"
        sibs = ", ".join(sorted(r["siblings"])[:5]) or "—"
        lines.append(f"| {r['domain']} | {r['earliest'] or '—'} | {issuer} | {sibs} |")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"certs-{account}.md"
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "dossier":
        out_path = certs_dossier(args[1])
        print(f"Saved: {out_path}")
    elif len(args) == 1 and "." in args[0]:
        info = fetch_certs(args[0])
        info["issuers"] = sorted(info["issuers"])
        info["siblings"] = sorted(info["siblings"])
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
