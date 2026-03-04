# DGenius Solutions — Lead Generation Scraper

> **Full-stack B2B lead generation system for [DGenius Solutions](https://www.dgeniussolutions.com)**
> Built for a digital marketing agency targeting decision-makers via LinkedIn and Google.

---

## What This Does

```
LinkedIn / Google
      ↓
   Scrape Leads
      ↓
  Enrich + Score (ICP matching, email discovery, website audit)
      ↓
  Generate AI Outreach (LinkedIn DMs, connection requests, email sequences)
      ↓
  Export (Excel, CSV, JSON, HTML Report)
      ↓
  CRM / Your Inbox
```

---

## Features

| Feature | Detail |
|---------|--------|
| **LinkedIn Scraper** | Scrapes decision-makers by title, industry, location using the LinkedIn API |
| **Google Maps Scraper** | Finds local businesses with weak online presence (low reviews, no website) |
| **Google Search Scraper** | Finds intent-based prospects via SerpAPI |
| **Lead Enrichment** | Email discovery (Hunter.io/Apollo), website SEO audit, social presence check |
| **ICP Scoring** | 0–100 score based on industry, seniority, pain points, website signals |
| **AI Outreach Generator** | Claude AI writes personalised LinkedIn + email sequences per lead |
| **Excel Export** | Colour-coded, ready for CRM import (HubSpot, Salesforce, Pipedrive) |
| **HTML Report** | Visual dashboard per campaign run |
| **SQLite Database** | Persistent lead storage, no external DB needed |

---

## Quick Start

### 1. Clone and install
```bash
git clone <repo-url>
cd Lead-Generation-Scraper
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure credentials
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run your first campaign

**Option A — No API keys needed (generate search URLs)**
```bash
python main.py urls
# Opens LinkedIn search URLs in your browser — prospect manually
```

**Option B — Google Maps (needs Google Maps API key)**
```bash
python main.py google-maps --location "New York, USA" --max-leads 100
```

**Option C — LinkedIn (needs LinkedIn credentials)**
```bash
python main.py linkedin --max-leads 50
```

**Option D — Run everything**
```bash
python main.py all --location "Los Angeles, CA" --max-leads 50
```

---

## CLI Reference

```
python main.py <command> [options]

Commands:
  linkedin      Scrape LinkedIn decision-makers
  google-maps   Scrape Google Maps local businesses
  google-search Scrape Google Search results
  all           Run all scrapers in sequence
  urls          Generate LinkedIn search URLs (no login needed)
  stats         Show database stats
  export        Export leads from database

Options (linkedin):
  --name          Campaign name
  --industries    Target industries (space-separated)
  --titles        Target job titles
  --locations     Target locations
  --max-leads     Max leads per run (default: 50)
  --no-outreach   Skip AI message generation

Options (google-maps):
  --location      City/region to search (default: "New York, USA")
  --radius        Search radius in km (default: 50)
  --categories    Business types to search
  --max-leads     Max leads (default: 100)

Options (export):
  --format        excel | csv | json (default: excel)
  --min-score     Minimum lead score filter
  --status        Filter by status (new/contacted/qualified/etc.)
  --source        Filter by source (linkedin/google_maps/google_search)
```

---

## Project Structure

```
Lead-Generation-Scraper/
├── main.py                    # CLI entry point
├── requirements.txt
├── .env.example               # Config template
├── STRATEGY.md                # Full B2B lead gen strategy playbook
│
├── src/
│   ├── config.py              # All settings from .env
│   ├── models.py              # Pydantic data models (Lead, Campaign, etc.)
│   ├── orchestrator.py        # Campaign orchestrator (glues everything)
│   │
│   ├── scrapers/
│   │   ├── linkedin_scraper.py   # LinkedIn API + URL builder
│   │   └── google_scraper.py     # Google Maps + Search scrapers
│   │
│   ├── enrichment/
│   │   └── enricher.py          # Email finder, website audit, ICP scorer
│   │
│   ├── outreach/
│   │   └── message_generator.py  # Claude AI outreach message writer
│   │
│   ├── export/
│   │   └── exporter.py          # Excel, CSV, JSON, HTML report
│   │
│   └── utils/
│       ├── database.py          # SQLite persistence
│       └── helpers.py           # Logging, delays, proxies, text utils
│
├── data/                      # SQLite database (gitignored)
├── exports/                   # Generated Excel/CSV/JSON (gitignored)
├── reports/                   # HTML reports (gitignored)
└── logs/                      # Daily log files (gitignored)
```

---

## API Keys You'll Need

| Key | Where to Get | Cost |
|-----|-------------|------|
| `LINKEDIN_EMAIL/PASSWORD` | Your LinkedIn account | Free |
| `SERPAPI_KEY` | https://serpapi.com | $50/mo |
| `GOOGLE_MAPS_API_KEY` | Google Cloud Console | ~$0.017/request |
| `HUNTER_API_KEY` | https://hunter.io | Free tier: 25/mo |
| `APOLLO_API_KEY` | https://apollo.io | Free tier: 50/mo |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com | Pay-per-use |

> **Minimum viable setup**: Just `GOOGLE_MAPS_API_KEY` + `HUNTER_API_KEY` is enough to start.

---

## Lead Scoring

| Score | Meaning | Action |
|-------|---------|--------|
| 75–100 | 🔴 Hot lead | Contact within 24 hours |
| 55–74 | 🟡 Warm lead | Contact within 48 hours |
| 30–54 | 🟢 Cold lead | Nurture sequence |
| 0–29 | ⚪ Not qualified | Archive |

---

## Target Industries for DGenius Solutions

**Tier 1 (highest ROI)**:
Real Estate • Legal • Healthcare • Financial Services • E-commerce • SaaS

**Tier 2 (good fit)**:
Education • Hospitality • Retail • Fitness • Beauty • Construction

---

## Outreach Generated Per Lead

For each qualified lead (score ≥ 50), the system generates:
1. **LinkedIn Connection Request** — personalised ≤300 chars
2. **LinkedIn Direct Message** — conversational, problem-aware
3. **Cold Email Sequence** — subject + body + 3 follow-ups (day 3, 7, 14)

All messages are personalised using the lead's specific pain points,
industry, company details, and buying signals detected during scraping.

---

## Legal & Ethical Use

- Respect LinkedIn's Terms of Service — do not exceed daily limits
- Use data for legitimate B2B prospecting only
- Comply with GDPR/CAN-SPAM for email outreach
- Always include opt-out options in emails
- Verify emails before sending to reduce bounce rate

---

## See Also

- [`STRATEGY.md`](./STRATEGY.md) — Full B2B lead generation strategy playbook
- [DGenius Solutions](https://www.dgeniussolutions.com) — Agency website
