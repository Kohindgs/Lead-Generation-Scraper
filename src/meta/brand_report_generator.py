"""
Brand Report Generator
======================
Uses Claude AI to research a prospect's brand and produce a
comprehensive, personalised Brand Audit Report covering:

  1. Executive Summary
  2. Current Brand Standing (website, SEO, social media, ad presence)
  3. Identified Gaps & Opportunities
  4. Competitor Landscape snapshot
  5. Recommended Services (from DGenius portfolio)
  6. Priority Action Plan (30 / 60 / 90 days)
  7. Why DGenius Solutions

The report is saved as both a formatted text file and an HTML file
ready to email as an attachment or paste into Gmail.

The report is queued for admin approval before any email is sent.
"""

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import ai_cfg, agency, db_cfg
from src.utils.helpers import get_logger

logger = get_logger(__name__)

REPORTS_DIR = Path("reports/brand_audits")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class LeadFormData:
    """Data captured from the Google Form submission."""
    psid: str                   # Meta page-scoped ID — links back to the commenter
    full_name: str
    phone: str
    company_email: str
    company_name: str
    website: str
    platform: str = "facebook"


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a Senior Brand Strategist and Digital Marketing Consultant
at {agency.name} ({agency.website}).

Your task: produce a detailed, personalised *Brand Audit & Opportunity Report*
for a prospective client who expressed interest in "AI Content" on our
Meta (Facebook/Instagram) campaign.

Tone: Professional, consultative, empathetic. Write like an expert advisor
who genuinely wants to help — not a sales pitch. Lead with insights,
back them up with rationale, then naturally introduce how {agency.name}
can help.

{agency.name} services available to recommend:
{chr(10).join(f'  • {s}' for s in agency.services)}

Always end with a clear, low-pressure call to action: invite them to a
free 30-minute strategy call.
"""

REPORT_PROMPT = """Generate a Brand Audit & Opportunity Report for the following prospect.

Prospect Details:
  Name         : {full_name}
  Company      : {company_name}
  Website      : {website}
  Industry     : {industry_guess}
  Contact Email: {company_email}

Instructions:
Use the website URL to reason about their likely digital presence, industry,
and typical pain points for that sector — even without real-time browsing.
Base insights on common patterns for businesses in this category.

Structure the report EXACTLY as follows (use these headers):

---
BRAND AUDIT REPORT — {company_name}
Prepared by {agency_name} | {report_date}
Confidential — For {full_name} Only
---

## 1. EXECUTIVE SUMMARY
(3-4 sentences. Summarise what we know about the brand, the opportunity, and
the #1 thing they should focus on.)

## 2. CURRENT BRAND STANDING

### 2a. Website & Online Presence
(Evaluate based on domain, likely site age/structure for their industry.
Comment on: mobile-friendliness probability, load speed indicators, CTA
clarity, trust signals.)

### 2b. SEO & Search Visibility
(Comment on typical SEO gaps for their sector. Mention: keyword targeting,
local SEO if applicable, content gaps, backlink profile likely state.)

### 2c. Social Media Presence
(Infer from industry norms: which platforms they likely use, engagement
quality signals, consistency of posting, brand voice.)

### 2d. Paid Advertising (Meta / Google Ads)
(Comment on whether businesses in their space are leveraging paid ads and
where they likely stand — even if not confirmed.)

### 2e. Content & AI Content Strategy
(This is why they're here. Comment on content quality, AI content usage,
thought leadership opportunity, and what a strong content strategy looks
like for their industry.)

## 3. KEY GAPS & OPPORTUNITIES
(3-5 bullet points. Be specific to their industry and website domain.
Each bullet: 1 gap + the opportunity it creates.)

## 4. COMPETITOR LANDSCAPE
(Brief overview of what competitors in their space typically do well.
Name 2-3 generic competitor archetypes, not real company names.)

## 5. RECOMMENDED SERVICES FOR {company_name}
(Pick 3-5 services from the {agency_name} portfolio most relevant to this
brand. For each: name, why it fits them specifically, expected outcome.)

## 6. PRIORITY ACTION PLAN

### 30-Day Quick Wins
(2-3 immediate actions with high impact / low effort)

### 60-Day Growth Moves
(2-3 medium-effort initiatives)

### 90-Day Scale Strategy
(2-3 bigger plays to establish market leadership)

## 7. WHY {agency_name}?
(3-4 sentences. Speak to our track record in their space, our AI-powered
approach, and our commitment to measurable ROI. Do NOT be generic.)

## 8. NEXT STEP
Invite {full_name} to book a FREE 30-minute Brand Strategy Call with our team.
Include a warm, confident CTA.

---
Report prepared by: {sender_name}, {sender_title}
{agency_name} | {agency_email} | {agency_website}
---
"""

SERVICE_PITCH_PROMPT = """Based on the brand audit you just wrote for {company_name},
provide a concise internal *Service Pitch Summary* for the DGenius sales team.

Format as JSON with these keys:
{{
  "top_services": ["service1", "service2", "service3"],
  "pitch_angle": "one-sentence hook tailored to this company's pain",
  "budget_tier": "starter | growth | enterprise",
  "urgency_signals": ["signal1", "signal2"],
  "suggested_opening_line": "the first sentence to say on a discovery call"
}}

Return ONLY valid JSON — no markdown fences.
"""


# ── Generator ──────────────────────────────────────────────────────────────────

class BrandReportGenerator:
    """
    Generates a personalised brand audit report using Claude AI.
    The report is saved locally and queued for admin approval.
    """

    def __init__(self):
        self.client = None
        if ai_cfg.anthropic_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=ai_cfg.anthropic_key)
                logger.info("Anthropic client ready for brand report generation.")
            except ImportError:
                logger.warning("anthropic SDK not installed. Run: pip install anthropic")

    def _call_ai(self, user_prompt: str, max_tokens: int = 3000) -> Optional[str]:
        if not self.client:
            return None
        try:
            response = self.client.messages.create(
                model=ai_cfg.model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.error("Claude API error during brand report generation: %s", exc)
            return None

    def _guess_industry(self, company_name: str, website: str) -> str:
        """Rough heuristic — Claude will do the real reasoning."""
        domain = website.lower().replace("https://", "").replace("http://", "").split("/")[0]
        keywords = {
            "real estate": ["realty", "property", "homes", "estate", "mortgage"],
            "healthcare": ["health", "clinic", "dental", "med", "care", "pharmacy"],
            "legal": ["law", "legal", "attorney", "lawyer", "solicitor"],
            "e-commerce": ["shop", "store", "buy", "market", "ecom"],
            "hospitality": ["hotel", "resort", "stay", "lodge", "restaurant", "cafe"],
            "finance": ["finance", "invest", "capital", "wealth", "fund", "bank"],
            "education": ["school", "academy", "learn", "edu", "tutor", "college"],
            "fitness": ["gym", "fit", "yoga", "wellness", "sport"],
            "beauty": ["salon", "beauty", "spa", "hair", "nail", "skin"],
            "saas / technology": ["tech", "app", "software", "digital", "cloud", "ai"],
        }
        combined = (company_name + " " + domain).lower()
        for industry, terms in keywords.items():
            if any(t in combined for t in terms):
                return industry
        return "Professional Services"

    def generate(self, lead: LeadFormData) -> Optional[dict]:
        """
        Generate the full brand audit report + internal pitch summary.
        Returns a dict with keys: report_text, report_html, pitch_json, report_path
        """
        industry = self._guess_industry(lead.company_name, lead.website)
        today = datetime.now().strftime("%d %B %Y")

        # Build the report prompt
        prompt = REPORT_PROMPT.format(
            full_name=lead.full_name,
            company_name=lead.company_name,
            website=lead.website,
            industry_guess=industry,
            company_email=lead.company_email,
            agency_name=agency.name,
            report_date=today,
            sender_name=agency.sender_name,
            sender_title=agency.sender_title,
            agency_email=agency.email,
            agency_website=agency.website,
        )

        logger.info("Generating brand report for %s (%s)...", lead.company_name, lead.website)
        report_text = self._call_ai(prompt, max_tokens=3500)

        if not report_text:
            report_text = self._fallback_report(lead, industry, today)
            logger.warning("Used fallback report template for %s.", lead.company_name)

        # Generate internal pitch summary
        pitch_prompt = SERVICE_PITCH_PROMPT.format(company_name=lead.company_name)
        pitch_raw = self._call_ai(pitch_prompt, max_tokens=400)
        pitch_json = self._parse_pitch_json(pitch_raw, lead)

        # Save files
        slug = re.sub(r"[^\w\-]", "_", lead.company_name.lower())[:40]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_path = REPORTS_DIR / f"{slug}_{timestamp}.txt"
        html_path = REPORTS_DIR / f"{slug}_{timestamp}.html"

        txt_path.write_text(report_text, encoding="utf-8")
        html_path.write_text(_to_html(report_text, lead, today), encoding="utf-8")

        # Store in DB
        _save_report_to_db(lead, str(txt_path), str(html_path), pitch_json)

        logger.info(
            "Brand report ready for %s — saved to %s",
            lead.company_name, txt_path
        )

        return {
            "report_text": report_text,
            "report_html_path": str(html_path),
            "report_txt_path": str(txt_path),
            "pitch": pitch_json,
            "industry": industry,
        }

    def _parse_pitch_json(self, raw: Optional[str], lead: LeadFormData) -> dict:
        import json
        if raw:
            try:
                cleaned = raw.strip().strip("```json").strip("```").strip()
                return json.loads(cleaned)
            except Exception:
                pass
        return {
            "top_services": ["Social Media Marketing", "Content Marketing & Blogging", "SEO"],
            "pitch_angle": (
                f"Help {lead.company_name} build a consistent, AI-powered content "
                "presence that attracts qualified leads."
            ),
            "budget_tier": "growth",
            "urgency_signals": ["expressed interest in AI Content", "active on Meta"],
            "suggested_opening_line": (
                f"Hi {lead.full_name.split()[0]}, we looked at {lead.company_name} "
                "and found a few quick wins that could make a real difference — "
                "mind if I walk you through them?"
            ),
        }

    def _fallback_report(self, lead: LeadFormData, industry: str, today: str) -> str:
        return f"""BRAND AUDIT REPORT — {lead.company_name}
Prepared by {agency.name} | {today}
Confidential — For {lead.full_name} Only

═══════════════════════════════════════════════════════════════

1. EXECUTIVE SUMMARY
{lead.company_name} operates in the {industry} space and has shown interest
in leveraging AI Content strategies — a clear indicator of forward-thinking
leadership. This report outlines key opportunities to strengthen your digital
brand and generate more qualified leads.

2. CURRENT BRAND STANDING
Based on your website ({lead.website}) and industry norms for {industry},
there are several areas where targeted improvements can drive measurable growth.

Key observations:
• Website optimisation and UX improvements can increase conversion rates
• SEO and content strategy gaps are typical for growing {industry} businesses
• Social media consistency and AI-powered content can dramatically improve reach
• Paid advertising (Meta & Google) remains underutilised in most {industry} businesses

3. KEY GAPS & OPPORTUNITIES
• Content Consistency: Irregular posting reduces algorithmic reach and brand recall
• SEO Foundation: Keyword gaps mean missed organic traffic from high-intent searches
• Social Proof: Testimonials and case studies increase conversion by up to 34%
• Paid Ads: Structured Meta campaigns can 3x qualified lead volume in 90 days
• AI Content Strategy: Early adopters in {industry} are seeing 60%+ faster content production

4. RECOMMENDED SERVICES
• Social Media Marketing — build a consistent, AI-enhanced content calendar
• SEO & Content Marketing — capture organic search intent for {industry} keywords
• Meta Ads Management — targeted lead generation campaigns
• Website Optimisation — improve CTA flow and conversion rate
• Email Marketing Automation — nurture leads through the funnel

5. NEXT STEP
We'd love to walk {lead.full_name} through a tailored 30-minute strategy session
— no obligation. Let's map out exactly what {lead.company_name} needs to grow.

Book your free call: {agency.website}/strategy-call

Report prepared by: {agency.sender_name}, {agency.sender_title}
{agency.name} | {agency.email} | {agency.website}
"""


# ── HTML converter ─────────────────────────────────────────────────────────────

def _to_html(report_text: str, lead: LeadFormData, today: str) -> str:
    """Convert the plain-text report to a branded HTML email body."""
    from src.config import meta_cfg

    paragraphs = []
    in_list = False
    for line in report_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("## "):
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            paragraphs.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("### "):
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            paragraphs.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("---"):
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            paragraphs.append("<hr>")
        elif stripped.startswith("• ") or stripped.startswith("* "):
            if not in_list:
                paragraphs.append("<ul>")
                in_list = True
            paragraphs.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_list:
                paragraphs.append("</ul>")
                in_list = False
            paragraphs.append(f"<p>{stripped}</p>")
    if in_list:
        paragraphs.append("</ul>")

    body = "\n".join(paragraphs)

    # Logo: white-background DGS logo (best for emails)
    logo_url = meta_cfg.logo_url
    logo_html = (
        f'<img src="{logo_url}" alt="DGenius Solutions" '
        f'style="height:64px;width:auto;display:block;margin-bottom:20px;" />'
        if logo_url else
        '<div style="font-size:28px;font-weight:900;letter-spacing:-1px;'
        'background:linear-gradient(90deg,#4fc3f7,#9c27b0,#ff7043);'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
        'margin-bottom:20px;">DGS</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Brand Audit Report — {lead.company_name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', Arial, sans-serif;
      background: #f4f6fb; color: #1a1a2e; line-height: 1.75;
    }}
    .wrapper {{
      max-width: 720px; margin: 0 auto; padding: 32px 16px;
    }}
    /* ── Header banner ── */
    .header {{
      background: #0d0d1a;
      border-radius: 14px 14px 0 0;
      padding: 36px 40px 28px;
      text-align: left;
    }}
    .header-meta {{
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid rgba(255,255,255,0.12);
    }}
    .header-meta p {{
      color: rgba(255,255,255,0.7);
      font-size: 13px;
      margin: 2px 0;
    }}
    .header-meta strong {{ color: #fff; }}
    /* ── Gradient accent bar ── */
    .accent-bar {{
      height: 5px;
      background: linear-gradient(90deg, #4fc3f7 0%, #ab47bc 45%, #ff7043 100%);
    }}
    /* ── Content card ── */
    .content {{
      background: #fff;
      padding: 40px 40px 32px;
      border-radius: 0 0 14px 14px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.07);
    }}
    h2 {{
      color: #0d0d1a;
      font-size: 17px;
      font-weight: 700;
      margin: 36px 0 10px;
      padding-left: 14px;
      border-left: 4px solid;
      border-image: linear-gradient(180deg,#4fc3f7,#ab47bc) 1;
    }}
    h3 {{
      color: #333;
      font-size: 15px;
      font-weight: 600;
      margin: 22px 0 8px;
    }}
    p {{ margin: 10px 0; font-size: 15px; color: #333; }}
    ul {{ padding-left: 20px; margin: 10px 0; }}
    li {{ margin: 6px 0; font-size: 15px; color: #333; }}
    hr {{ border: none; border-top: 1px solid #eee; margin: 28px 0; }}
    /* ── CTA button ── */
    .cta-wrap {{ text-align: center; margin: 40px 0 20px; }}
    .cta {{
      display: inline-block;
      padding: 15px 36px;
      border-radius: 50px;
      font-weight: 700;
      font-size: 15px;
      text-decoration: none;
      color: #fff !important;
      background: linear-gradient(90deg, #4fc3f7 0%, #ab47bc 50%, #ff7043 100%);
      box-shadow: 0 4px 18px rgba(171,71,188,0.35);
      letter-spacing: 0.3px;
    }}
    /* ── Confidential badge ── */
    .badge {{
      display: inline-block;
      background: linear-gradient(90deg,#4fc3f7,#ab47bc,#ff7043);
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1px;
      padding: 3px 10px;
      border-radius: 20px;
      margin-top: 10px;
      text-transform: uppercase;
    }}
    /* ── Footer ── */
    .footer {{
      text-align: center;
      margin-top: 32px;
      padding: 20px;
      font-size: 12px;
      color: #888;
    }}
    .footer a {{ color: #ab47bc; text-decoration: none; }}
  </style>
</head>
<body>
<div class="wrapper">

  <!-- Header -->
  <div class="header">
    {logo_html}
    <div class="header-meta">
      <p><strong>Brand Audit Report</strong></p>
      <p>Prepared for: <strong>{lead.company_name}</strong></p>
      <p>Date: {today} &nbsp;|&nbsp; Prepared by {agency.name}</p>
      <div class="badge">Confidential — For {lead.full_name} Only</div>
    </div>
  </div>

  <!-- Gradient accent bar -->
  <div class="accent-bar"></div>

  <!-- Report content -->
  <div class="content">
    {body}

    <div class="cta-wrap">
      <a href="{agency.website}/strategy-call" class="cta">
        Book Your FREE 30-Min Strategy Call
      </a>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <strong>{agency.sender_name}</strong> &mdash; {agency.sender_title}<br>
    <a href="{agency.website}">{agency.name}</a> &nbsp;&bull;&nbsp;
    <a href="mailto:{agency.email}">{agency.email}</a>
  </div>

</div>
</body>
</html>"""


# ── DB persistence ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_cfg.path)
    conn.row_factory = sqlite3.Row
    return conn


def _save_report_to_db(
    lead: LeadFormData,
    txt_path: str,
    html_path: str,
    pitch: dict,
):
    import json
    with _get_conn() as conn:
        conn.execute("""
            UPDATE meta_leads
            SET
                full_name        = ?,
                phone            = ?,
                company_email    = ?,
                company_name     = ?,
                website          = ?,
                report_generated = 1,
                report_path      = ?,
                updated_at       = datetime('now')
            WHERE psid = ?
        """, (
            lead.full_name,
            lead.phone,
            lead.company_email,
            lead.company_name,
            lead.website,
            html_path,
            lead.psid,
        ))
        # Store pitch recommendations in a separate table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_report_pitches (
                psid          TEXT PRIMARY KEY,
                company_name  TEXT,
                top_services  TEXT,
                pitch_angle   TEXT,
                budget_tier   TEXT,
                urgency       TEXT,
                opening_line  TEXT,
                txt_path      TEXT,
                html_path     TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            INSERT INTO meta_report_pitches
                (psid, company_name, top_services, pitch_angle, budget_tier,
                 urgency, opening_line, txt_path, html_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(psid) DO UPDATE SET
                top_services = excluded.top_services,
                html_path    = excluded.html_path,
                txt_path     = excluded.txt_path
        """, (
            lead.psid,
            lead.company_name,
            json.dumps(pitch.get("top_services", [])),
            pitch.get("pitch_angle", ""),
            pitch.get("budget_tier", "growth"),
            json.dumps(pitch.get("urgency_signals", [])),
            pitch.get("suggested_opening_line", ""),
            txt_path,
            html_path,
        ))
        conn.commit()
