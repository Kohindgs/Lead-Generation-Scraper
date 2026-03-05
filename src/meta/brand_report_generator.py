"""
Brand Report Generator
======================
Uses Claude AI to research a prospect's brand and produce a
comprehensive, personalised Brand Audit Report covering:

  1. Executive Summary
  2. Website Analysis
  3. SEO & Search Visibility
  4. Social Media Presence
  5. Generative AI Strategy
  6. What You're Missing Out On (FOMO — real industry stats)
  7. Key Gaps & Opportunities
  8. Competitor Landscape
  9. Recommended Services (from DGenius portfolio)
  10. Priority Action Plan (30 / 60 / 90 days)
  11. Why DGenius Solutions

The report is saved as both a formatted text file and an HTML file
ready to email as an attachment or paste into Gmail.

The report is queued for ADMIN APPROVAL (x2) before any email is sent:
  • Approval 1: Admin reviews generated report content
  • Approval 2: Admin previews the email and confirms before sending
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
Use REAL industry statistics and data points to back every claim.

Structure the report EXACTLY as follows (use these headers):

---
BRAND AUDIT REPORT — {company_name}
Prepared by {agency_name} | {report_date}
Confidential — For {full_name} Only
---

## 1. EXECUTIVE SUMMARY
(3-4 sentences. Summarise what we know about the brand, the opportunity, and
the single most urgent action they should take. Be direct and specific.)

## 2. WEBSITE ANALYSIS
(Evaluate based on domain and industry norms. Cover each of these specifically:
  • Mobile-friendliness: 60%+ of searches are mobile — assess their likely state
  • Page load speed: A 1-second delay reduces conversions by 7% — are they at risk?
  • CTA clarity: Are they likely capturing leads or just getting visitors who leave?
  • Trust signals: SSL, testimonials, case studies, review badges
  • UX & conversion flow: Is the visitor journey clear or confusing?
Give a realistic score out of 10 and state what it would take to reach 10/10.)

## 3. SEO & SEARCH VISIBILITY
(Be specific and data-driven. Cover:
  • Organic ranking likelihood for their top 3-5 industry keywords
  • Local SEO — if applicable, Google Business Profile strength
  • Content gaps: Are they publishing thought-leadership content regularly?
  • Backlink profile: Typical state for businesses at their stage
  • Technical SEO: Site structure, schema markup, page indexing issues typical in their sector
  • Voice & AI search: Are they optimised for how modern users search?
Give a realistic score out of 10. Name specific keywords they are likely missing.)

## 4. SOCIAL MEDIA PRESENCE
(Analyse platform-by-platform relevance for their industry. Cover:
  • Which platforms drive ROI for {industry_guess} businesses (with data)
  • Posting frequency benchmark vs. what they likely do
  • Content mix: educational / promotional / social proof — ideal ratio
  • Engagement quality: followers vs. real community
  • Brand voice consistency across platforms
  • Influencer & UGC opportunities in their sector
Give a realistic score out of 10 and a specific improvement recommendation.)

## 5. GENERATIVE AI STRATEGY
(This is the core reason they reached out. Be insightful and forward-looking:
  • AI Content creation: How can they use AI to 10x their content output?
  • AI for customer service: chatbots, automated replies, lead qualification
  • AI-powered personalisation: email sequences, ad creative, landing pages
  • AI for SEO: programmatic content, topical authority building
  • Competitor AI adoption: What are forward-thinking companies in {industry_guess} doing?
  • Specific AI tools relevant to their business (mention real tools: ChatGPT, Claude,
    Jasper, Midjourney, HeyGen, etc.)
  • Risk of NOT adopting: early movers in their sector are gaining 6-12 month advantages
Give a realistic score out of 10 for their current AI readiness.)

## 6. WHAT {company_name} IS MISSING OUT ON RIGHT NOW
(This is the FOMO section. Use REAL statistics. Be direct and specific.
Show the cost of inaction in hard numbers. Format as a powerful list:

  WEBSITE:
  • [Stat about businesses losing revenue from poor websites — e.g., "75% of users judge
    a company's credibility based on its website design (Stanford)"]
  • What {company_name} is likely losing monthly from website gaps

  SEO:
  • [Stat — e.g., "The #1 Google result gets 31.7% of all clicks (Backlinko)"]
  • ["68% of online experiences begin with a search engine (BrightEdge)"]
  • Estimated monthly searches they are missing for their top keywords

  SOCIAL MEDIA:
  • [Stat — e.g., "Businesses that post consistently see 3x more leads (HubSpot)"]
  • ["54% of social browsers use social media to research products before buying"]
  • What inconsistent posting is costing them in brand awareness

  GENERATIVE AI:
  • [Stat — e.g., "Businesses using AI content tools produce 5-10x more content at 60%
    lower cost (McKinsey 2024)"]
  • ["Marketers who use AI are 6x more likely to see improved ROI (Salesforce)"]
  • The competitive gap opening between AI-adopters and non-adopters in {industry_guess}

  OVERALL COST OF INACTION:
  • Estimate the monthly revenue opportunity they are leaving on the table
  • How many leads per month competitors are capturing that should be theirs)

## 7. KEY GAPS & OPPORTUNITIES
(3-5 bullet points. Each: 1 specific gap + the business opportunity it creates.
Be industry-specific — not generic advice.)

## 8. COMPETITOR LANDSCAPE
(Brief overview of what forward-thinking competitors in their space are doing.
Describe 2-3 competitor archetypes (no real names) and what they do well.
Show where {company_name} sits relative to the pack.)

## 9. RECOMMENDED SERVICES FOR {company_name}
(Pick 3-5 services from the {agency_name} portfolio most relevant to this brand.
For each: service name | why it fits | specific expected outcome with numbers.)

## 10. PRIORITY ACTION PLAN

### 30-Day Quick Wins
(2-3 immediate, high-impact / low-effort actions they can start this week)

### 60-Day Growth Moves
(2-3 medium-effort initiatives that build momentum)

### 90-Day Scale Strategy
(2-3 bigger plays that establish market leadership in their sector)

## 11. WHY {agency_name}?
(3-4 sentences. Reference our AI-powered approach, measurable ROI focus, and
why we are specifically suited for {industry_guess} businesses. Not generic.)

## 12. NEXT STEP
Invite {full_name} to book a FREE 30-minute Brand Strategy Call.
Reference 1-2 specific findings from THIS report to make the CTA feel personal.
Warm, confident, no pressure.

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
        report_text = self._call_ai(prompt, max_tokens=5000)

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

## 1. EXECUTIVE SUMMARY
{lead.company_name} operates in the {industry} space and has expressed interest
in AI Content strategies — a strong signal of forward-thinking leadership.
This audit identifies the key gaps holding the business back from capturing
more leads online, and maps a clear path to digital growth.

## 2. WEBSITE ANALYSIS
Based on {lead.website} and {industry} industry benchmarks:
• Mobile experience is critical — 60%+ of your potential customers search on mobile
• Page load speed directly impacts conversions: a 1-second delay = 7% drop in sales
• Clear CTAs and trust signals (reviews, case studies) are typically underdeveloped
• Estimated score: 5/10 — significant room to improve conversion rate
Reaching 10/10 requires: speed optimisation, mobile UX overhaul, and a clear lead capture flow.

## 3. SEO & SEARCH VISIBILITY
• Most {industry} businesses miss the top 5 Google results for their core keywords
• Local SEO is often unclaimed — Google Business Profile optimisation alone can drive 30%+ more calls
• Content publishing is sporadic, causing low topical authority
• Backlink profile is typical for a growing brand — needs structured outreach
• Estimated score: 4/10 — organic traffic is being left for competitors to capture

## 4. SOCIAL MEDIA PRESENCE
• {industry} businesses that post 4-5x per week generate 3x more engagement than those posting once weekly
• Content mix should be 60% educational, 20% social proof, 20% promotional
• Inconsistent brand voice reduces trust and algorithmic reach
• AI-powered content scheduling can close the consistency gap immediately
• Estimated score: 5/10 — posting more consistently would deliver quick wins

## 5. GENERATIVE AI STRATEGY
• AI content tools allow businesses to produce 5-10x more content at 60% lower cost
• Businesses using AI for marketing are 6x more likely to report improved ROI (Salesforce 2024)
• Key opportunities: AI-written blog posts, AI video scripts, automated email sequences,
  AI chatbot for lead qualification on the website
• Tools to explore: ChatGPT, Claude, Jasper for copy; HeyGen for AI video; ManyChat for DM automation
• {industry} is in early adoption phase — NOW is the time to become the AI-forward brand
• Estimated AI readiness score: 3/10 — strong first-mover opportunity

## 6. WHAT {lead.company_name} IS MISSING OUT ON RIGHT NOW

WEBSITE:
• 75% of users judge company credibility based on website design (Stanford University)
• Poor UX is likely costing {lead.company_name} 20-40% of potential enquiries monthly

SEO:
• The #1 Google result captures 31.7% of all clicks (Backlinko)
• 68% of online experiences begin with a search engine (BrightEdge)
• Competitors ranking above {lead.company_name} are receiving hundreds of qualified visitors per month that should be yours

SOCIAL MEDIA:
• 54% of social browsers research products/services on social before buying
• Inconsistent posting is likely causing {lead.company_name} to lose brand recall to more active competitors

GENERATIVE AI:
• Marketers using AI report 40% faster campaign execution and significantly lower content costs
• Every month without an AI content strategy is a month competitors build an insurmountable lead advantage

OVERALL COST OF INACTION:
• Estimated 15-30 qualified leads per month being captured by competitors instead
• The revenue opportunity left on the table each month: significant and growing

## 7. KEY GAPS & OPPORTUNITIES
• Website Conversion: Lack of clear CTAs = visitors leaving without enquiring — fix = 2x lead capture
• SEO Content: No consistent publishing = Google deprioritises the site — fix = rank for 20+ new keywords in 90 days
• Social Consistency: Irregular posting = low reach — fix = AI content calendar produces daily posts in 1 hour/week
• AI Adoption: No AI tools in use = slower, costlier content — fix = 5x output at fraction of current cost
• Email Nurture: No automated follow-up = cold leads go cold — fix = 30-50% more conversions from existing enquiries

## 8. COMPETITOR LANDSCAPE
• The "Digital-First" competitor: Active on 3+ platforms, publishing weekly blogs, running Google Ads — capturing organic + paid traffic
• The "Local Authority" competitor: Dominates Google Maps and local search, consistent 5-star reviews, strong referral engine
• {lead.company_name} has the opportunity to outmanoeuvre both by becoming the AI Content leader in the space

## 9. RECOMMENDED SERVICES FOR {lead.company_name}
• AI Content & Social Media Marketing — build a consistent, AI-powered content engine (outcome: 3x reach in 60 days)
• SEO & Content Marketing — capture organic search intent (outcome: page 1 ranking for priority keywords in 90 days)
• Website Optimisation — improve CTA flow and conversion rate (outcome: 20-40% more enquiries from existing traffic)
• Email Marketing Automation — nurture leads through the funnel (outcome: 30%+ uplift in conversion rate)
• Meta / Google Ads Management — targeted paid lead generation (outcome: predictable qualified leads monthly)

## 10. PRIORITY ACTION PLAN

### 30-Day Quick Wins
• Set up AI content calendar — 30 days of posts written in one session using AI tools
• Claim and optimise Google Business Profile — quick local SEO win with direct impact on calls
• Add 2-3 strong CTAs to website homepage — capture visitors already landing on the site

### 60-Day Growth Moves
• Launch SEO blog programme — 2 AI-assisted posts/week to build topical authority
• Implement email nurture sequence for all enquiries — stop leads going cold
• A/B test ad creative using AI-generated variations

### 90-Day Scale Strategy
• Establish {lead.company_name} as the go-to thought leader in {industry} via AI video content
• Deploy AI chatbot on website for 24/7 lead qualification
• Build a referral programme powered by email automation

## 11. WHY {agency.name}?
We specialise in helping {industry} businesses compete online using AI-powered strategies
that deliver measurable results — not vanity metrics. Our approach combines human strategy
with cutting-edge AI execution, which means faster results at lower cost. We've worked with
businesses at exactly {lead.company_name}'s stage and know precisely which levers to pull first.

## 12. NEXT STEP
{lead.full_name}, based on what we've uncovered — particularly the SEO and AI content gaps —
a 30-minute strategy call would give us the chance to map out a precise action plan for
{lead.company_name}. No pressure, no sales pitch — just clear, actionable insights.

Book your free strategy call: {agency.website}/strategy-call

---
Report prepared by: {agency.sender_name}, {agency.sender_title}
{agency.name} | {agency.email} | {agency.website}
---
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
