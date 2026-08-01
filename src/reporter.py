"""Reporting helper: assemble an evidence-based abuse-report packet for one site.

This does NOT send anything. It gathers what you already know (is the site live,
who registered it, is it part of a network) and produces a copy-paste packet:
where to report, and a ready draft to paste there. You review and submit.

It reuses our own modules - liveness.check() and enrich.lookup_domain() - so
the evidence is generated fresh, not copied from an old file.

CLI:
    python src/reporter.py example-site.net     # one site
    python src/reporter.py queue <account>      # all live sites in a dossier
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import enrich
import liveness

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_DIR = ROOT / "data" / "dossiers"
REPORTS_DIR = ROOT / "reports"

REQUEST_DELAY_SECONDS = 1

# Nameserver substring -> known hosting/CDN abuse channel.
HOST_ABUSE = {
    "cloudflare": ("Cloudflare", "https://abuse.cloudflare.com/"),
    "o2switch": ("o2switch", "abuse@o2switch.fr"),
}


def _network_context(domain: str) -> dict:
    """If this domain appears in a saved dossier's leads, report the network size."""
    for path in DOSSIER_DIR.glob("*.json"):
        dossier = json.loads(path.read_text())
        leads = dossier.get("leads", [])
        hosts = [lead.split("//", 1)[-1].split("/", 1)[0] for lead in leads]
        if domain in hosts:
            return {"account": dossier.get("account", ""), "size": len(hosts)}
    return {}


def build_packet(domain: str) -> dict:
    live = liveness.check(domain)
    info = enrich.lookup_domain(domain)
    network = _network_context(domain)

    channels = []
    for ns in info["nameservers"]:
        for needle, (name, where) in HOST_ABUSE.items():
            if needle in ns and (name, where) not in [(c[0], c[1]) for c in channels]:
                channels.append((name, where, "hosting/CDN abuse"))
    if info["registrar"]:
        channels.append(
            (info["registrar"], f"search: \"{info['registrar']} abuse contact\"",
             "domain registrar abuse")
        )
    if network.get("account"):
        channels.append(
            ("GitHub", "https://github.com/contact/report-abuse",
             f"the account {network['account']} that hosts the repo")
        )
    channels.append(
        ("Google Search", "https://support.google.com/websearch/answer/9109057",
         "remove from search results")
    )

    return {
        "domain": domain,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "live": live,
        "registrar": info["registrar"],
        "nameservers": info["nameservers"],
        "network": network,
        "channels": channels,
    }


def render(packet: dict) -> str:
    d = packet
    live_line = (
        f"currently LIVE (HTTP {d['live']['status']})"
        if d["live"]["verdict"] in ("LIVE", "BLOCKED")
        else f"currently unreachable ({d['live']['verdict']})"
    )
    net = d["network"]
    net_line = (
        f"- It is one of ~{net['size']} sites linked to the same operator "
        f"(GitHub account `{net['account']}`), several registered through the "
        f"same registrar within a short window (see enrichment report).\n"
        if net else ""
    )

    draft = (
        "To whom it may concern,\n\n"
        f"I am reporting {d['domain']}, which promotes/hosts a service for "
        "generating non-consensual synthetic intimate imagery ('nudify' / "
        "deepfake). This facilitates image-based sexual abuse.\n\n"
        "Evidence:\n"
        f"- The site is {live_line} as of {d['generated']}.\n"
        f"- Domain registered through {d['registrar'] or 'an unknown registrar'}; "
        f"nameservers: {', '.join(d['nameservers']) or 'n/a'}.\n"
        f"{net_line}"
        "\nI request review and action under your abuse policy.\n\n"
        "[YOUR NAME / CONTACT]\n"
    )

    lines = [
        f"# Report packet — {d['domain']}",
        "",
        f"_Generated {d['generated']}. Review and submit yourself - this file "
        "sends nothing._",
        "",
        "## Where to report",
        "",
        "| Channel | Where | What it covers |",
        "|---|---|---|",
    ]
    for name, where, covers in d["channels"]:
        lines.append(f"| {name} | {where} | {covers} |")

    lines += [
        "",
        "> If you observe sexual imagery of minors specifically, that is CSAM: "
        "report it to the NCMEC CyberTipline (report.cybertip.org) or, in the "
        "UK, the IWF (iwf.org.uk) - not just to the abuse channels above.",
        "",
        "## Draft message (paste into each channel)",
        "",
        "```",
        draft,
        "```",
        "",
    ]
    return "\n".join(lines)


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


def build_queue(account: str) -> Path:
    """Prepare packets for every LIVE site in a dossier + a master checklist.

    Still sends nothing: this just removes the busywork so you can review,
    paste, solve the CAPTCHA, and submit each one yourself.
    """
    domains = _domains_from_dossier(account)
    print(f"Preparing report packets for {len(domains)} site(s) from {account}...")

    live_rows = []
    for index, domain in enumerate(domains):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        packet = build_packet(domain)
        verdict = packet["live"]["verdict"]
        print(f"  {verdict:8} {domain}")
        if verdict in ("LIVE", "BLOCKED"):
            (REPORTS_DIR / f"report-{domain}.md").write_text(render(packet))
            live_rows.append(packet)

    lines = [
        f"# Report queue — {account}",
        "",
        f"{len(live_rows)} live site(s) ready to report, out of {len(domains)}.",
        "**Nothing is sent automatically.** Work top to bottom: open the channel,"
        " paste the draft from the per-site file, solve the CAPTCHA, submit.",
        "",
        "| # | Site | Channels | Draft |",
        "|---|---|---|---|",
    ]
    for i, packet in enumerate(live_rows, 1):
        d = packet["domain"]
        chans = ", ".join(c[0] for c in packet["channels"])
        lines.append(f"| {i} | {d} | {chans} | `reports/report-{d}.md` |")

    lines += [
        "",
        "After you submit one, log it:",
        "`python src/report.py mark <finding-key> reported`",
        "",
    ]
    out_path = REPORTS_DIR / f"report-queue-{account}.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "queue":
        out_path = build_queue(args[1])
        print(f"Saved queue: {out_path}  (review, then submit each yourself)")
    elif len(args) == 1 and "." in args[0]:
        packet = build_packet(args[0])
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = REPORTS_DIR / f"report-{args[0]}.md"
        out_path.write_text(render(packet))
        up = packet["live"]["verdict"]
        print(f"{args[0]}: {up} | channels: {len(packet['channels'])}")
        print(f"Saved: {out_path}  (review, then submit yourself)")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
