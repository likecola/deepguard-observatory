"""Unified fingerprint clustering: group a dossier's domains into operators.

Each domain gets a fingerprint from the signals we already collect —
nameservers + registrar (enrich) and tracking IDs (analytics). Domains that
share a *distinctive* fingerprint are joined into one cluster (union-find):
that's the "same operator" grouping.

Outputs:
- reports/cluster-<account>.md    cluster report (has domain names = intel, git-ignored)
- reports/graph-<account>.html    readable network graph (domains ↔ shared signals)
- data/clusters.json              ANONYMIZED sizes only, for the public dashboard

Fingerprints are cached to data/fingerprints-<account>.json so re-runs are fast.
Not all signals are equal: shared tracking IDs are strong; a host's generic
nameserver (every o2switch customer) is weak and skipped.

    python src/cluster.py dossier <account>
    python src/cluster.py dossier <account> --refresh   # ignore the cache
"""

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import analytics
import enrich

ROOT = Path(__file__).resolve().parent.parent
DOSSIER_DIR = ROOT / "data" / "dossiers"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

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


def _load_fingerprints(account: str, domains: list, refresh: bool) -> dict:
    cache = DATA_DIR / f"fingerprints-{account}.json"
    if cache.exists() and not refresh:
        print(f"Using cached fingerprints ({cache.name}).")
        return json.loads(cache.read_text())
    fps = {}
    for i, domain in enumerate(domains):
        if i > 0:
            time.sleep(1)
        fps[domain] = fingerprint(domain)
        print(f"  {domain}: ns={len(fps[domain]['nameservers'])}"
              f" track={len(fps[domain]['tracking_ids'])}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(fps, indent=2))
    return fps


def cluster(account: str, refresh: bool = False) -> dict:
    domains = _domains_from_dossier(account)
    print(f"Fingerprinting {len(domains)} domain(s)...")
    fps = _load_fingerprints(account, domains, refresh)

    # Map each distinctive signal value -> the domains carrying it.
    value_to_domains = defaultdict(set)
    for domain in domains:
        fp = fps.get(domain, {"nameservers": [], "tracking_ids": []})
        for ns in fp["nameservers"]:
            if not _generic_ns(ns):
                value_to_domains[f"ns:{ns}"].add(domain)
        for tid in fp["tracking_ids"]:
            value_to_domains[f"track:{tid}"].add(domain)

    uf = _UnionFind(domains)
    shared = {}  # signal value -> sorted member domains (2+)
    for value, ds in value_to_domains.items():
        if len(ds) < 2:
            continue
        ds = sorted(ds)
        shared[value] = ds
        for other in ds[1:]:
            uf.union(ds[0], other)

    clusters = defaultdict(list)
    for domain in domains:
        clusters[uf.find(domain)].append(domain)
    clusters = sorted(clusters.values(), key=len, reverse=True)

    return {"account": account, "fps": fps, "clusters": clusters, "shared": shared}


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
        tag = "Cluster" if len(members) > 1 else "Singleton"
        lines.append(f"## {tag} {i} — {len(members)} domain(s)")
        for d in members:
            reg = fps[d]["registrar"] or "—"
            lines.append(f"- {d}  _(registrar: {reg})_")
        lines.append("")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"cluster-{account}.md"
    path.write_text("\n".join(lines))
    return path


def _write_clusters_json(result: dict) -> Path:
    """Anonymized summary (sizes only, NO domain names) for the public dashboard."""
    clusters = result["clusters"]
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total_domains": sum(len(c) for c in clusters),
        "operators": sum(1 for c in clusters if len(c) > 1),
        "sizes": [len(c) for c in clusters if len(c) > 1],
        "singletons": sum(1 for c in clusters if len(c) == 1),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "clusters.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _write_graph(result: dict) -> Path:
    """Bipartite graph: domain nodes ↔ shared-signal hub nodes. Physics freezes."""
    account, clusters, shared = result["account"], result["clusters"], result["shared"]
    cluster_of = {d: i for i, members in enumerate(clusters) for d in members}

    nodes = [{"id": f"d:{d}", "label": d, "group": cluster_of[d], "shape": "dot",
              "size": 10} for members in clusters for d in members]
    edges = []
    for value, members in shared.items():
        kind, val = value.split(":", 1)
        nodes.append({"id": f"s:{value}", "label": val, "shape": "box",
                      "color": "#30363d", "font": {"color": "#8b949e", "size": 11}})
        for d in members:
            edges.append({"from": f"s:{value}", "to": f"d:{d}"})

    html = """<!doctype html><html><head><meta charset="utf-8">
<title>Network — %s</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/dist/vis-network.min.js"></script>
<style>body{margin:0;background:#0d1117;color:#e6edf3;font:14px sans-serif}
#h{padding:12px 16px}#h small{color:#8b949e}
#net{width:100%%;height:86vh;border-top:1px solid #22282f}</style>
</head><body>
<div id="h"><b>%s</b> — %d sites, %d operator clusters.<br>
<small>Round = site (colour = operator). Grey box = a shared signal (nameserver / tracking ID) that links them.</small></div>
<div id="net"></div>
<script>
const nodes=new vis.DataSet(%s), edges=new vis.DataSet(%s);
const net=new vis.Network(document.getElementById('net'),{nodes,edges},{
  layout:{improvedLayout:true},
  nodes:{font:{color:'#e6edf3'}},
  edges:{color:{color:'#3fb950',opacity:0.35},smooth:false},
  physics:{barnesHut:{gravitationalConstant:-12000,springLength:140,
           centralGravity:0.25,damping:0.6},
           stabilization:{iterations:400}},
  interaction:{hover:true,dragNodes:true}});
net.once('stabilizationIterationsDone',()=>net.setOptions({physics:false}));
</script></body></html>""" % (
        account, account, len([n for n in nodes if n["id"].startswith("d:")]),
        len(clusters), json.dumps(nodes), json.dumps(edges),
    )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"graph-{account}.html"
    path.write_text(html)
    return path


def main() -> None:
    args = sys.argv[1:]
    refresh = "--refresh" in args
    args = [a for a in args if a != "--refresh"]
    if len(args) == 2 and args[0] == "dossier":
        result = cluster(args[1], refresh=refresh)
        report = _write_report(result)
        graph = _write_graph(result)
        cj = _write_clusters_json(result)
        multi = sum(1 for c in result["clusters"] if len(c) > 1)
        print(f"{len(result['clusters'])} cluster(s) ({multi} with 2+ domains).")
        print(f"Saved: {report}\n       {graph}\n       {cj}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
