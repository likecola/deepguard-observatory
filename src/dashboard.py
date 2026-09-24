"""Generate a self-contained HTML dashboard from the findings ledger.

Aggregate only — counts, rates, and dates. No target names or URLs ever reach
the output, so the dashboard is safe to publish (e.g. via GitHub Pages) while
the underlying intelligence stays private.

    python src/dashboard.py        # writes index.html at the repo root
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINDINGS_PATH = ROOT / "data" / "findings.json"
OUT_PATH = ROOT / "index.html"


def _pretty(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip().capitalize() or "—"


def _bars(data: list) -> str:
    """data: list of (label, count). Returns HTML rows with proportional bars."""
    if not data:
        return '<p class="muted">No data yet.</p>'
    top = max(count for _, count in data) or 1
    rows = []
    for label, count in data:
        pct = 100 * count / top
        rows.append(
            f'<div class="row">'
            f'<span class="lbl">{label}</span>'
            f'<span class="track"><span class="fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="num">{count}</span>'
            f"</div>"
        )
    return "\n".join(rows)


def _tile(value, label, accent=False) -> str:
    cls = "tile accent" if accent else "tile"
    return f'<div class="{cls}"><div class="v">{value}</div><div class="l">{label}</div></div>'


def build() -> Path:
    findings = json.loads(FINDINGS_PATH.read_text()) if FINDINGS_PATH.exists() else {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    by_status = Counter(f["status"] for f in findings.values())
    by_source = Counter(f["source"] for f in findings.values())
    by_category = Counter(f["category"] for f in findings.values())
    by_month = Counter(f["first_seen"][:7] for f in findings.values())

    reported_total = by_status["reported"] + by_status["removed"] + by_status["rejected"]
    removed = by_status["removed"]
    removal_rate = f"{100 * removed / reported_total:.0f}%" if reported_total else "—"

    tiles = "".join([
        _tile(len(findings), "Findings tracked", accent=True),
        _tile(by_status["new"], "Awaiting report"),
        _tile(reported_total, "Reported"),
        _tile(removed, "Removed"),
        _tile(removal_rate, "Removal rate"),
    ])

    month_bars = _bars([(m, n) for m, n in sorted(by_month.items())])
    source_bars = _bars([(_pretty(s), n) for s, n in by_source.most_common()])
    category_bars = _bars([(_pretty(c), n) for c, n in by_category.most_common()])

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DeepGuard Observatory</title>
<style>
  :root {{ color-scheme: dark; --bg:#0d1117; --card:#161b22; --line:#22282f;
           --fg:#e6edf3; --muted:#8b949e; --accent:#2f81f7; --accent2:#3fb950; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
          font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }}
  .wrap {{ max-width: 900px; margin:0 auto; padding: 32px 20px 60px; }}
  header h1 {{ margin:0 0 4px; font-size:26px; letter-spacing:-0.5px; }}
  header p {{ margin:0; color:var(--muted); }}
  .stamp {{ font-size:13px; color:var(--muted); margin-top:6px; }}
  .tiles {{ display:flex; flex-wrap:wrap; gap:12px; margin:28px 0; }}
  .tile {{ flex:1 1 120px; background:var(--card); border:1px solid var(--line);
           border-radius:12px; padding:16px; }}
  .tile.accent {{ border-color:var(--accent); }}
  .tile .v {{ font-size:30px; font-weight:700; }}
  .tile .l {{ color:var(--muted); font-size:13px; margin-top:2px; }}
  section {{ background:var(--card); border:1px solid var(--line);
             border-radius:12px; padding:18px 20px; margin:16px 0; }}
  section h2 {{ margin:0 0 14px; font-size:15px; color:var(--muted);
                text-transform:uppercase; letter-spacing:0.5px; }}
  .row {{ display:flex; align-items:center; gap:12px; margin:7px 0; }}
  .lbl {{ flex:0 0 40%; font-size:14px; }}
  .track {{ flex:1; height:10px; background:#0d1117; border-radius:6px; overflow:hidden; }}
  .fill {{ display:block; height:100%; background:linear-gradient(90deg,var(--accent),var(--accent2)); }}
  .num {{ flex:0 0 40px; text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; }}
  .muted {{ color:var(--muted); }}
  footer {{ color:var(--muted); font-size:13px; margin-top:28px; line-height:1.7; }}
  a {{ color:var(--accent); }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>DeepGuard Observatory</h1>
    <p>Detecting, investigating &amp; reporting the networks behind non-consensual deepfake tools.</p>
    <div class="stamp">Updated {now} &middot; aggregate figures only, no target data</div>
  </header>

  <div class="tiles">{tiles}</div>

  <section>
    <h2>Findings by month</h2>
    {month_bars}
  </section>

  <section>
    <h2>By source</h2>
    {source_bars}
  </section>

  <section>
    <h2>By category</h2>
    {category_bars}
  </section>

  <footer>
    Method: public data (OSINT) only &middot; confirmed with an LLM &middot;
    reported through official channels. Target identifiers are kept private and
    never appear here.<br>
    Source &amp; methodology: <a href="https://github.com/likecola/deepguard-observatory">github.com/likecola/deepguard-observatory</a>
  </footer>
</div>
</body>
</html>
"""
    OUT_PATH.write_text(html)
    return OUT_PATH


if __name__ == "__main__":
    path = build()
    print(f"Dashboard written: {path}")
