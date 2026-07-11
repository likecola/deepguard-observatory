"""Findings tracker and summary report generation.

Three layers of output:
- reports/scan-*.json   raw per-run analysis results (append-only log)
- data/findings.json    every item flagged harmful, with a tracked status
- reports/summary.md    regenerated human-readable stats + open findings

Statuses follow the project workflow: "new" (detected, not yet reported),
"reported" (submitted through the platform's official channel), then one of
"removed" (platform took it down), "rejected" (platform declined), or
"dismissed" (we decided it was a false positive).

CLI:
    python src/report.py                     # regenerate summary.md
    python src/report.py mark <key> <status> # e.g. mark github:12345 reported
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINDINGS_PATH = ROOT / "data" / "findings.json"
REPORTS_DIR = ROOT / "reports"
SUMMARY_PATH = REPORTS_DIR / "summary.md"

STATUSES = ("new", "reported", "removed", "rejected", "dismissed")
OPEN_STATUSES = ("new", "reported")


def load_findings() -> dict:
    if FINDINGS_PATH.exists():
        return json.loads(FINDINGS_PATH.read_text())
    return {}


def save_findings(findings: dict) -> None:
    FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FINDINGS_PATH.write_text(
        json.dumps(findings, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )


def update_findings(results: list) -> int:
    """Merge newly flagged harmful items into the tracker. Returns count added."""
    findings = load_findings()
    added = 0

    for result in results:
        if not result.get("is_harmful"):
            continue
        item = result.get("item", {})
        key = f"{item.get('source', 'unknown')}:{item.get('id', '')}"
        if key in findings:
            continue

        findings[key] = {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source": item.get("source", "unknown"),
            "category": result.get("category", ""),
            "confidence": result.get("confidence", ""),
            "reasoning": result.get("reasoning", ""),
            "recommended_action": result.get("recommended_action", ""),
            "first_seen": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "status": "new",
            "status_updated": None,
        }
        added += 1

    if added:
        save_findings(findings)
    return added


def mark(key: str, status: str) -> None:
    """Update one finding's status and regenerate the summary."""
    if status not in STATUSES:
        raise SystemExit(f"Unknown status {status!r}. Valid: {', '.join(STATUSES)}")

    findings = load_findings()
    if key not in findings:
        raise SystemExit(f"No finding with key {key!r}. Known keys:\n  " +
                         "\n  ".join(sorted(findings)))

    findings[key]["status"] = status
    findings[key]["status_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_findings(findings)
    generate_summary()
    print(f"{key} -> {status}")


def _percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def generate_summary() -> Path:
    findings = load_findings()
    scan_count = len(list(REPORTS_DIR.glob("scan-*.json")))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    by_status = Counter(f["status"] for f in findings.values())
    by_source = Counter(f["source"] for f in findings.values())
    by_category = Counter(f["category"] for f in findings.values())
    by_month = Counter(f["first_seen"][:7] for f in findings.values())

    # Response stats: of everything we reported, what did platforms do?
    reported_total = sum(by_status[s] for s in ("reported", "removed", "rejected"))
    removed = by_status["removed"]

    lines = [
        "# DeepGuard Observatory — Summary",
        "",
        f"_Auto-generated {now}. Do not edit by hand — run `python src/report.py`._",
        "",
        "## Totals",
        "",
        f"- Scan runs recorded: **{scan_count}**",
        f"- Harmful findings tracked: **{len(findings)}**",
        f"- Awaiting report (status `new`): **{by_status['new']}**",
        f"- Reported to platforms: **{reported_total}**",
        f"- Removed by platforms: **{removed}**"
        f" (removal rate: {_percent(removed, reported_total)})",
        f"- Dismissed as false positives: **{by_status['dismissed']}**",
        "",
        "## Findings by month (first seen)",
        "",
        "| Month | Findings |",
        "|---|---|",
    ]
    lines += [f"| {m} | {n} |" for m, n in sorted(by_month.items(), reverse=True)]

    lines += ["", "## Findings by source", "", "| Source | Findings |", "|---|---|"]
    lines += [f"| {s} | {n} |" for s, n in by_source.most_common()]

    lines += ["", "## Findings by category", "", "| Category | Findings |", "|---|---|"]
    lines += [f"| {c} | {n} |" for c, n in by_category.most_common()]

    open_items = {k: f for k, f in findings.items() if f["status"] in OPEN_STATUSES}
    lines += [
        "",
        "## Open findings",
        "",
        "| Key | Title | Source | Category | Confidence | First seen | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, f in sorted(open_items.items(), key=lambda kv: kv[1]["first_seen"]):
        title = f["title"].replace("|", "\\|")[:60]
        lines.append(
            f"| `{key}` | [{title}]({f['url']}) | {f['source']} |"
            f" {f['category']} | {f['confidence']} | {f['first_seen']} |"
            f" {f['status']} |"
        )
    if not open_items:
        lines.append("| — | no open findings | | | | | |")

    lines += [
        "",
        "---",
        "",
        "To update a finding after acting on it:",
        "`python src/report.py mark <key> reported|removed|rejected|dismissed`",
        "",
    ]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines))
    return SUMMARY_PATH


def main() -> None:
    args = sys.argv[1:]
    if not args:
        path = generate_summary()
        print(f"Summary regenerated: {path}")
    elif args[0] == "mark" and len(args) == 3:
        mark(args[1], args[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
