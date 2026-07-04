"""Entry point: scan Reddit/GitHub, analyze new findings with Claude, save results."""

import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from analyzer import analyze_batch, usage_summary
from github_scanner import scan_github
from reddit_scanner import scan_reddit
from state import item_key, load_seen_ids, save_seen_ids

load_dotenv()

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def run_scan() -> list:
    findings = scan_reddit() + scan_github()
    if not findings:
        print("No matching content found.")
        return []

    seen = load_seen_ids()
    new_findings = [f for f in findings if item_key(f) not in seen]
    skipped = len(findings) - len(new_findings)
    if skipped:
        print(f"Skipping {skipped} previously analyzed item(s).")
    if not new_findings:
        print("No new content to analyze.")
        return []

    print(f"Found {len(new_findings)} new candidate item(s). Analyzing with Claude...")
    results = analyze_batch(new_findings)

    # Only mark items as seen once they were successfully analyzed.
    save_seen_ids(seen | {item_key(f) for f in new_findings})

    harmful = [r for r in results if r["is_harmful"]]
    print(f"{len(harmful)} item(s) flagged as harmful out of {len(results)} analyzed.")
    print(usage_summary())

    return results


def save_results(results: list) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out_path = REPORTS_DIR / f"scan-{timestamp}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    return out_path


def main() -> None:
    results = run_scan()
    if results:
        out_path = save_results(results)
        print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
