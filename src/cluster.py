"""Unified fingerprint clustering: group a dossier's domains into operators.

Each domain gets a fingerprint from the signals we already collect —
nameservers + registrar (enrich) and tracking IDs (analytics). Domains that
share a *distinctive* fingerprint are joined into one cluster (union-find):
that's the "same operator" grouping. The result is written as a report and as
an interactive network graph (nodes = domains, edges = shared signal).

Not all signals are equal (lesson learned the hard way): shared tracking IDs
are strong; a shared host's generic nameserver (e.g. every o2switch customer)
is weak and is skipped so it can't merge unrelated domains.

    python src/cluster.py dossier <account>

Output (git-ignored, contains domain names = intel):
    reports/cluster-<account>.md      cluster report
    reports/graph-<account>.html      interactive graph (open in a browser)
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import analytics
import enrich

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_DIR = ROOT / "data" / "dossiers"
REPORTS_DIR = ROOT / "reports"

# Nameservers shared by every customer of a host — too generic to cluster on.
GENERIC_NS_HINTS = ("o2switch",)


def _generic_ns(ns: str) -> bool:
    return any(hint in ns for hint in GENERIC_NS_HINTS)


def fingerprint(domain: str) -> dict:
    info = enrich.lookup_domain(domain)
    return {
        "registrar": info.get("registrar", ""),
        "nameservers": info.get("nameservers", []),
        "tracking_ids": sorted(analytics.fetch_ids(domain)),
    }


class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


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


def cluster(account: str) -> dict:
    domains = _domains_from_dossier(account)
    print(f"Fingerprinting {len(domains)} domain(s)...")

    fps = {}
    for i, domain in enumerate(domains):
        if i > 0:
            time.sleep(1)
        fps[domain] = fingerprint(domain)
        print(f"  {domain}: ns={len(fps[domain]['nameservers'])}"
              f" track={len(fps[domain]['tracking_ids'])}")

    # Map each distinctive signal value -> the domains carrying it.
    value_to_domains = defaultdict(set)
    for domain, fp in fps.items():
        for ns in fp["nameservers"]:
            if not _generic_ns(ns):
                value_to_domains[f"ns:{ns}"].add(domain)
        for tid in fp["tracking_ids"]:
            value_to_domains[f"track:{tid}"].add(domain)

    uf = _UnionFind(domains)
    edges = []
    for value, ds in value_to_domains.items():
        if len(ds) < 2:
            continue
        ds = sorted(ds)
        for other in ds[1:]:
            uf.union(ds[0], other)
        for a in ds:
            for b in ds:
                if a < b:
                    edges.append({"from": a, "to": b, "signal": value})

    clusters = defaultdict(list)
    for domain in domains:
        clusters[uf.find(domain)].append(domain)
    clusters = sorted(clusters.values(), key=len, reverse=True)

    return {"account": account, "fps": fps, "clusters": clusters, "edges": edges}


def _write_report(result: dict) -> Path:
    account, clusters, fps = result["account"], result["clusters"], result["fps"]
    lines = [
        f"# Operator clusters — {account}",
        "",
        f"{len(fps)} domains grouped into {len(clusters)} cluster(s) by shared"
        " nameserver / tracking ID (generic host nameservers excluded).",
        "",
    ]
    for i, members in enumerate(clusters, 1):
        tag = "cluster" if len(members) > 1 else "singleton"
        lines.append(f"## {tag.capitalize()} {i} — {len(members)} domain(s)")
        for d in members:
            reg = fps[d]["registrar"] or "—"
            lines.append(f"- {d}  _(registrar: {reg})_")
        lines.append("")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"cluster-{account}.md"
    path.write_text("\n".join(lines))
    return path


def _write_graph(result: dict) -> Path:
    account, clusters, edges = result["account"], result["clusters"], result["edges"]
    cluster_of = {d: i for i, members in enumerate(clusters) for d in members}
    nodes = [{"id": d, "label": d, "group": cluster_of[d]}
             for members in clusters for d in members]
    edge_data = [{"from": e["from"], "to": e["to"], "title": e["signal"]}
                 for e in edges]

    html = """<!doctype html><html><head><meta charset="utf-8">
<title>Network — %s</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/dist/vis-network.min.js"></script>
<style>body{margin:0;background:#0d1117;color:#e6edf3;font:14px sans-serif}
#h{padding:12px 16px}#net{width:100%%;height:88vh;border-top:1px solid #22282f}</style>
</head><body>
<div id="h"><b>%s</b> — %d domains, %d clusters. Nodes = sites, edges = shared signal (hover to see which).</div>
<div id="net"></div>
<script>
const nodes=new vis.DataSet(%s);
const edges=new vis.DataSet(%s);
new vis.Network(document.getElementById('net'),{nodes,edges},
 {nodes:{shape:'dot',size:12,font:{color:'#e6edf3'}},
  edges:{color:{color:'#3fb950',opacity:0.5}},
  physics:{stabilization:true}});
</script></body></html>""" % (
        account, account, len(nodes), len(clusters),
        json.dumps(nodes), json.dumps(edge_data),
    )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"graph-{account}.html"
    path.write_text(html)
    return path


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "dossier":
        result = cluster(args[1])
        report = _write_report(result)
        graph = _write_graph(result)
        multi = sum(1 for c in result["clusters"] if len(c) > 1)
        print(f"{len(result['clusters'])} cluster(s) ({multi} with 2+ domains).")
        print(f"Saved: {report}\n       {graph}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
