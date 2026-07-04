# DeepGuard Observatory

A community-driven monitoring system for detecting and tracking deepfake-related content in open-source platforms.

## Overview

DeepGuard Observatory monitors public platforms (Reddit, GitHub) for AI models and techniques that could be used to create non-consensual synthetic media. When harmful content is detected, we report it through official channels and maintain transparent statistics about ecosystem health.

**This is a solo weekend project.** The goal is modest but concrete: catch and prevent the deepfakes we can see, document what we find, and let the data speak for itself.

## The Problem

Deepfake technology poses real harm—particularly to women and children. While large AI companies have internal safety teams, open-source communities lack coordinated visibility into how their tools are being misused. 

There's no public record of which platforms respond fastest, what patterns emerge, or how the ecosystem is actually evolving.

## How It Works

```
Scan → Analyze → Report → Track → Repeat
  ↓        ↓        ↓        ↓       ↓
Daily   Claude  Official  Publish  Auto
check   API     channels  stats    run
```

### Process

1. **Scan**: Daily checks of Reddit/GitHub for deepfake-related content
2. **Analyze**: Use Claude API to confirm if content is actually harmful
3. **Report**: Submit through official platform channels
4. **Track**: Record outcomes and response times
5. **Publish**: Monthly transparency report with statistics

### What Gets Reported

- GitHub repos for non-consensual synthetic media generation
- Deepfake tutorial code and guides
- Collections of harmful models or techniques
- Explicit bypass methods for safety filters

### What Doesn't

- Academic deepfake detection research
- Licensed entertainment use cases
- Theoretical security discussions
- Properly-licensed or disclaimed projects

## Quick Start

### Requirements

- Python 3.9+
- Reddit API credentials (free)
- Claude API key (~$1-5/month with the default cost controls, see below)

### Setup (30 minutes)

```bash
git clone https://github.com/[username]/deepguard-observatory.git
cd deepguard-observatory

python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys
```

### Run

```bash
# One-time scan
python src/main.py

# Or enable GitHub Actions for daily automation
# See .github/workflows/daily_scan.yml
```

## Keeping API Costs Low

This is a solo project, so the pipeline is designed to spend as little as possible:

1. **Deduplication** — item IDs that were already analyzed are stored in
   `data/seen_ids.json`, so daily runs only pay for *new* content. This is the
   biggest saving: without it, every run re-analyzes the same recent posts.
2. **Two-tier analysis** — every candidate is screened with a cheap model
   (Haiku 4.5, $1/$5 per MTok). Only items flagged as harmful — or that the
   screen is unsure about — are re-checked with a stronger model (Opus 4.8,
   $5/$25 per MTok) before being treated as harmful. Most candidates are
   noise, so the expensive model runs rarely. Configure via `SCREEN_MODEL` /
   `CONFIRM_MODEL` in `.env`.
3. **Input capping** — post bodies are truncated to 1,500 characters before
   analysis.
4. **Usage logging** — every run prints token usage and estimated cost, so
   drift is visible immediately.

Also recommended: set a monthly spend limit in the
[Anthropic Console](https://console.anthropic.com/) as a hard backstop.

With ~10-30 new items/day this lands around **$1-5/month**. If volume grows
10x, the next lever is the [Message Batches API](https://platform.claude.com/docs/en/build-with-claude/batch-processing)
(50% discount, results within an hour — a fine fit for a daily cron).

## Output

```
reports/
└── scan-[timestamp].json  # Raw analysis results per run

data/
└── seen_ids.json          # Already-analyzed item IDs (dedup state)
```

## Project Structure

```
├── src/
│   ├── main.py             # Entry point
│   ├── reddit_scanner.py   # Reddit keyword scanning
│   ├── github_scanner.py   # GitHub repo search
│   ├── analyzer.py         # Two-tier Claude analysis
│   └── state.py            # Dedup state (seen IDs)
├── reports/                # Per-run scan results
├── data/                   # Dedup state
├── .github/workflows/      # GitHub Actions daily scan
├── requirements.txt
├── .env.example
└── README.md
```

## Roadmap

- [ ] SQLite findings database (`database.py`) for longitudinal stats
- [ ] Reporting helper (`reporter.py`) — drafts for official platform report channels
- [ ] Monthly transparency report generator (`monthly_report.md`)
- [ ] Track report outcomes and platform response times

## Metrics

### What Success Looks Like (Monthly)

| Metric | Target |
|--------|--------|
| Items detected | 15-30 |
| Report success rate | 80%+ |
| Platform removal rate | 60%+ |
| Repository stars | 20-50 (3 months) |

## Legal & Ethics

### We Do

✓ Monitor only publicly available data  
✓ Use official reporting channels  
✓ Keep all reports anonymous  
✓ Publish methodology transparently  
✓ Allow corrections and feedback  

### We Don't

✗ Collect personal information  
✗ Download illegal content  
✗ Send automated spam  
✗ Harass anyone  
✗ Target specific people or companies  

## Limitations

- Only catches what's publicly visible
- Depends on platforms to act on reports
- Limited to platforms with APIs
- Requires ongoing maintenance

**That's okay.** The goal is useful, not perfect.

## Why This Matters

Every deepfake prevented is a real person protected.

If this catches and prevents even 1% of the deepfakes that would otherwise exist, it's worth the time investment.

The secondary goal: prove that individual effort can move the needle on safety. You don't need a corporation to make a difference.

## Contributing

Feedback welcome:
- Report bugs via [Issues](../../issues)
- Suggest improvements via [Discussions](../../discussions)
- Submit methodology improvements via [Pull Requests](../../pulls)

## License

MIT License - do what you want with this code.

---

**Status**: Active development  
**Maintainer**: Solo developer, ~5 hours/week  
**Last Updated**: July 2026  

For Korean documentation, see [README_KO.md](README_KO.md)