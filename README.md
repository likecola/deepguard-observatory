# DeepGuard Observatory

An open-source intelligence (OSINT) pipeline that detects, investigates, and reports the tools and networks behind non-consensual deepfake content.

## Overview

DeepGuard Observatory scans public platforms (GitHub, Hugging Face, Reddit, optionally Civitai) for AI models and tools that can be used to create non-consensual synthetic media, uses the Claude API to confirm which are genuinely harmful, then **investigates the actors and infrastructure behind them** — tracing one finding to the account, the account to its other sites, and those sites to shared registration/hosting that reveals a single operator. Confirmed harm is reported through official channels, and outcomes are tracked for transparent statistics.

The focus is deliberately the *upstream* of the problem — where tools and models are distributed and promoted — rather than shallow coverage of every social network. Walled gardens without public APIs (X, Meta platforms) are out of scope; see Limitations.

**This is a solo weekend project.** The goal is modest but concrete: catch and prevent the deepfakes we can see, document what we find, and let the data speak for itself.

## The Problem

Deepfake technology poses real harm—particularly to women and children. While large AI companies have internal safety teams, open-source communities lack coordinated visibility into how their tools are being misused. 

There's no public record of which platforms respond fastest, what patterns emerge, or how the ecosystem is actually evolving.

## How It Works

```
   ── automated, daily ──          ── manual, deep ──
  Scan → Analyze → Track    →    Investigate → Enrich   →   Report → Publish
   ↓        ↓        ↓                ↓           ↓            ↓         ↓
 multi-  Claude   findings       actor/repo   domain      official  monthly
 source  two-tier  ledger         dossier    registration channels   stats
```

### Process

1. **Scan**: Daily keyword checks of GitHub repos, Hugging Face models/spaces, Reddit posts, and (opt-in) Civitai models
2. **Analyze**: Use the Claude API to confirm which candidates are actually harmful
3. **Track**: Record each harmful finding in a status ledger
4. **Investigate** *(manual)*: Pivot from a finding to the account behind it and build an OSINT dossier — other repos, harvested links, cross-platform presence
5. **Enrich** *(manual)*: Look up domain registration to cluster scattered sites into a single operator
6. **Report**: Submit through official platform channels
7. **Publish**: Monthly transparency report with statistics

Steps 1–3 run automatically via GitHub Actions; steps 4–5 are the investigator's manual deep-dive.

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
- Reddit Data API credentials (free, non-commercial use — requires an
  [access request](https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164);
  optional — the Reddit scan is skipped until credentials are set)
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

Three layers, from raw to human-readable:

```
reports/
├── scan-[timestamp].json  # Raw analysis results per run (append-only log)
└── summary.md             # Auto-generated stats + open findings table

data/
├── findings.json          # Tracker: every harmful finding with a status
└── seen_ids.json          # Already-analyzed item IDs (dedup state)
```

Every harmful finding enters `data/findings.json` with status `new`. After you
act on one, record the outcome — the summary (report/removal rates, monthly
trends) regenerates automatically:

```bash
python src/report.py mark github:12345 reported   # submitted via official channel
python src/report.py mark github:12345 removed    # platform took it down
# other statuses: rejected (platform declined), dismissed (false positive)
```

## Investigating an actor

Scanning is automated and shallow; investigation is manual and deep. Given one
finding, `investigate.py` pivots from the repo to the **account behind it** and
builds a dossier from public sources only (OSINT):

```bash
python src/investigate.py github:<finding-id>   # from a finding key
python src/investigate.py github <account>      # or an account directly
```

It collects the account's profile, every public repo (deepfake-related ones
flagged), external links harvested from bios and repo homepages, domains taken
from repo names, and any Hugging Face models under the same username — then
suggests pivots (linked socials, domains) to investigate next. One flagged repo
routinely expands into dozens of leads when the account runs a promotion
network.

Dossiers are written to `data/dossiers/` and `reports/dossier-*.md`. **They are
git-ignored** — they profile individuals (from public data, but still), so
publishing any specific one is a deliberate choice, not automatic. Everything is
for reporting through official channels, not for contacting anyone.

### Enriching the leads

`enrich.py` looks up who registered a domain and when, via RDAP (the modern
JSON WHOIS — no key, no extra dependency):

```bash
python src/enrich.py example-site.net       # one domain
python src/enrich.py dossier <account>      # every domain in a saved dossier
```

Domains that share a registrar, a registration window, and nameservers are
almost certainly one operator. In testing, 20+ domains from a single account all
traced to the same registrar and the same nameservers within a 6-week window —
infrastructure proof that one actor runs the network.

### Triaging what to report first

`liveness.py` checks which leads are actually online, so you report active harm
first:

```bash
python src/liveness.py example-site.net     # one site
python src/liveness.py dossier <account>     # every domain, sorted by priority
```

It labels each site LIVE / BLOCKED / ERROR / GONE / DEAD from its HTTP response
and sorts live sites to the top. A dead site is deprioritized but still evidence
it existed (its registration record persists). In one tested network, 33 of 34
domains were live — the operation was still active.

### Preparing a report

`reporter.py` assembles an evidence-based abuse-report packet for one site —
where to report and a ready-to-paste draft — by reusing `liveness` and `enrich`:

```bash
python src/reporter.py example-site.net     # one site
python src/reporter.py queue <account>      # all live sites in a dossier, batched
```

The `queue` mode prepares a packet for every live site in a dossier plus a
master checklist (`reports/report-queue-*.md`) — it removes the busywork but
**still submits nothing**: you review, paste, solve the CAPTCHA, and submit each
one. Automated submission is deliberately not built (abuse channels want genuine
human reports; auto-submission gets flagged as spam and undermines credibility).

**It sends nothing.** You review the packet (`reports/report-*.md`) and submit
it yourself through the listed channels (Cloudflare abuse, the registrar, GitHub,
search removal). If the service can produce sexual imagery of minors, that is
CSAM and goes to the NCMEC CyberTipline / IWF, not just abuse channels.

### Mapping the network

`pivot.py` starts from one account and walks outward — its domains → other
accounts that reference those domains → and so on — to map a network of actors
rather than a single one:

```bash
python src/pivot.py github <account>        # depth 1, up to 6 accounts
python src/pivot.py github <account> 2 8    # depth 2, up to 8 accounts
```

A *visited* set prevents loops; depth/account caps and a per-account domain
sample bound the crawl and the API usage. Set a read-only `GITHUB_TOKEN` to raise
the search rate limit. Output is a network map under `data/networks/` and
`reports/network-*.md` (git-ignored).

## Case Study (anonymized)

A single automated scan flagged **one** GitHub repository as a non-consensual
deepfake tool. Running the investigation pipeline on it:

1. **Investigate** — the repo's owner turned out to run **37 repositories**, each
   named after a different AI "girlfriend" / nudify / porn service domain — an
   affiliate-promotion network, not a lone repo. → **34 domain leads**.
2. **Enrich** — RDAP lookups showed **20+ of those domains registered through the
   same registrar, within a 6-week window, sharing the same 2–3 nameservers.**
   Infrastructure evidence that one operator runs the whole set.
3. **Triage** — a liveness sweep found **33 of 34 sites live** — the network was
   actively operating, so reporting was time-sensitive.
4. **Report** — the tool generated evidence-based abuse-report packets (routed to
   the CDN, registrar, and platform channels) for manual submission.

One low-signal finding became a mapped, attributed, actively-operating network —
the difference between *observing* and *investigating*. (Target identifiers are
withheld here and kept out of this public repo.)

## Note on data

The **code** is public; the **intelligence it produces is not.** Findings, scan
results, dossiers, enrichment, and report packets are all written under `data/`
and `reports/`, which are git-ignored and stay on your machine. Scanning runs
locally (see the manual-only GitHub Actions workflow). If you want persistent
automation, run it in a private repo so target data never becomes public.

## Project Structure

```
├── src/
│   ├── main.py                 # Entry point
│   ├── reddit_scanner.py       # Reddit keyword scanning
│   ├── github_scanner.py       # GitHub repo search
│   ├── huggingface_scanner.py  # Hugging Face models/spaces search
│   ├── google_cse_scanner.py   # Web search via Google Programmable Search
│   ├── civitai_scanner.py      # Civitai model search (opt-in — region-blocked in some countries)
│   ├── analyzer.py             # Two-tier Claude analysis
│   ├── report.py               # Findings tracker + summary generation
│   ├── investigate.py          # Actor investigation / dossier builder (OSINT)
│   ├── enrich.py               # Domain infrastructure lookup (RDAP/WHOIS)
│   ├── liveness.py             # Which leads are up now — reporting triage
│   ├── reporter.py             # Builds an abuse-report packet (you submit it)
│   ├── pivot.py                # Recursive pivoting — maps the actor network
│   └── state.py                # Dedup state (seen IDs)
├── reports/                # Per-run scan results
├── data/                   # Dedup state
├── .github/workflows/      # GitHub Actions daily scan
├── requirements.txt
├── .env.example
└── README.md
```

## Roadmap

- [x] Findings tracker with report/removal status (`data/findings.json`)
- [x] Auto-generated summary with monthly trends (`reports/summary.md`)
- [x] Actor investigation / dossier builder (`investigate.py`)
- [x] Infrastructure enrichment via RDAP/WHOIS (`enrich.py`)
- [x] Liveness triage of leads (`liveness.py`)
- [x] Reporting helper — evidence-based abuse-report packets (`reporter.py`)
- [x] Recursive pivoting — map the actor network (`pivot.py`)
- [ ] Shared-analytics-ID clustering (same Google Analytics / AdSense across sites)
- [ ] TTP catalog — how the ecosystem's promotion networks operate
- [ ] Platform response-time tracking (days from `reported` to `removed`)

## Metrics

### What Success Looks Like (Monthly)

| Metric | Target |
|--------|--------|
| Items detected | 15-30 |
| Report success rate | 80%+ |
| Platform removal rate | 60%+ |
| Repository stars | 20-50 (3 months) |

## Legal & Ethics

This project **investigates** — it builds profiles of the actors and
infrastructure behind harmful services. That makes the boundaries below more
important, not less. They reflect what the tooling actually does.

### We Do

✓ Use only publicly available data (OSINT) — public repos, public APIs, public registration records  
✓ Investigate the accounts, sites, and infrastructure behind harmful services, to establish who is responsible  
✓ Report through official platform / registrar / host abuse channels  
✓ Keep dossiers private by default (git-ignored); publish any individual profile only deliberately  
✓ Publish methodology transparently and allow corrections  

### We Don't

✗ Access private data, accounts, or anything requiring a login or a hack  
✗ Contact, confront, dox, or publicly name the people investigated  
✗ Download or store illegal content  
✗ Enter dark-web or illegal marketplaces — that work requires an organization's legal cover, not a solo project  
✗ Send automated spam or harass anyone  

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