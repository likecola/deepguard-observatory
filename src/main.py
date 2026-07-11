"""Entry point: scan Reddit/GitHub, analyze new findings with Claude, save results."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from analyzer import analyze_batch, usage_summary
from civitai_scanner import scan_civitai
from github_scanner import scan_github
from google_cse_scanner import scan_google_cse
from huggingface_scanner import scan_huggingface
from reddit_scanner import scan_reddit
from report import generate_summary, update_findings
from state import item_key, load_seen_ids, save_seen_ids

load_dotenv()

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _reddit_configured() -> bool:
    return bool(
        os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET")
    )


def _safe_scan(name: str, scan) -> list:
    """Run one scanner; a failing source logs a warning instead of killing the run."""
    try:
        results = scan()
        print(f"{name}: {len(results)} candidate(s)")
        return results
    except Exception as exc:
        print(f"WARNING: {name} scan failed, continuing without it: {exc}")
        return []


def run_scan() -> list:
    findings = []
    if _reddit_configured():
        findings += _safe_scan("Reddit", scan_reddit)
    else:
        print("Reddit credentials not set - skipping Reddit scan.")
    findings += _safe_scan("GitHub", scan_github)
    findings += _safe_scan("Hugging Face", scan_huggingface)
    if os.environ.get("GOOGLE_API_KEY") and os.environ.get("GOOGLE_CSE_ID"):
        findings += _safe_scan("Google CSE", scan_google_cse)
    else:
        print("Google CSE credentials not set - skipping web search.")
    # Civitai region-blocks a growing list of countries (HTTP 451), so this
    # source is opt-in. See README.
    if os.environ.get("CIVITAI_ENABLED", "").lower() == "true":
        findings += _safe_scan("Civitai", scan_civitai)
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

        added = update_findings(results)
        if added:
            print(f"{added} new finding(s) added to data/findings.json.")
    summary_path = generate_summary()
    print(f"Summary updated: {summary_path}")


if __name__ == "__main__":
    main()
