"""
AI-Powered Outreach Message Generator
=======================================
Generates highly personalised, conversion-optimised outreach messages
for DGenius Solutions using Claude AI.

Channels:
  - LinkedIn Connection Request (300 char limit)
  - LinkedIn Direct Message / InMail
  - Cold Email (subject + body + 3 follow-ups)

Personalisation variables used per lead:
  - First name, title, company, industry
  - Specific pain points detected
  - Services recommended
  - Buying signals found
  - Google rating / review count (for Maps leads)
"""
import json
from typing import List, Optional

from src.config import ai_cfg, agency
from src.models import Lead, OutreachMessage, OutreachChannel, LeadSource
from src.utils.helpers import get_logger

logger = get_logger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a senior Business Development Executive at {agency.name}
({agency.website}), a full-service digital marketing agency.

Your role: Write short, authentic, highly personalised outreach messages
that feel human — NOT like a mass marketing blast.

Core principles:
1. LEAD WITH VALUE, not a pitch. Show you understand their specific situation.
2. Be BRIEF. LinkedIn ≤ 300 chars for connection requests; messages ≤ 150 words.
3. Use the specific pain points and signals provided — never be generic.
4. One clear call-to-action. Ask for a 15-minute call or reply.
5. Never say "I hope this message finds you well."
6. Sign off as: {agency.sender_name}, {agency.sender_title} at {agency.name}
7. Tone: Confident, direct, peer-to-peer — not salesy.

Services {agency.name} offers:
{chr(10).join(f'  • {s}' for s in agency.services[:8])}
"""

CONNECTION_REQUEST_PROMPT = """Write a LinkedIn CONNECTION REQUEST for this lead.
STRICT LIMIT: Under 300 characters total.
Format: Just the message text, no extra commentary.

Lead details:
{lead_summary}

The message must:
- Mention their specific industry or role
- Hint at a relevant insight or value we can offer
- End with a reason to connect
"""

LINKEDIN_MESSAGE_PROMPT = """Write a LinkedIn DIRECT MESSAGE to this lead (after connection).
LIMIT: Under 150 words.
Format: Plain text, no subject line needed.

Lead details:
{lead_summary}

The message must:
- Reference something specific about their business/role
- Mention 1-2 specific pain points we identified
- Position {agency} as the solution without being pushy
- Single, clear CTA: ask for a 15-min discovery call
- No bullet points, just conversational prose
"""

EMAIL_PROMPT = """Write a COLD EMAIL sequence for this lead.
Return valid JSON with keys: subject, body, follow_up_1, follow_up_2, follow_up_3

Lead details:
{lead_summary}

Requirements:
- subject: ≤60 chars, curiosity-driven, personalised, no clickbait
- body: 100-150 words max. Open with a pattern-interrupt observation,
  identify 1-2 pain points, position {agency} as solution, single CTA.
- follow_up_1 (3 days later): 60-80 words, add social proof / case study hint
- follow_up_2 (7 days later): 40-60 words, value-add — share a quick insight
- follow_up_3 (14 days later): 30-40 words, breakup email, leave door open

Each email must feel like a fresh, standalone message.
Return ONLY valid JSON, no markdown fences.
"""


# ── Lead summary builder ──────────────────────────────────────────────────────

def _build_lead_summary(lead: Lead) -> str:
    """Convert Lead to a compact, prompt-friendly summary string."""
    lines = [
        f"Name: {lead.full_name or 'Unknown'}",
        f"Title: {lead.title or 'Business Owner'}",
        f"Company: {lead.company_name or 'Unknown Company'}",
        f"Industry: {lead.industry or 'Unknown'}",
        f"Location: {', '.join(filter(None, [lead.city, lead.country]))}",
        f"Company website: {lead.company_website or 'None found'}",
    ]
    if lead.company_description:
        lines.append(f"About them: {lead.company_description[:200]}")
    if lead.google_rating:
        lines.append(
            f"Google rating: {lead.google_rating}/5 "
            f"({lead.google_review_count or 0} reviews)"
        )
    if lead.pain_points:
        lines.append(f"Pain points identified: {'; '.join(lead.pain_points[:3])}")
    if lead.services_needed:
        lines.append(f"Services they likely need: {', '.join(lead.services_needed[:3])}")
    if lead.buying_signals:
        lines.append(f"Buying signals: {', '.join(lead.buying_signals[:3])}")
    lines.append(f"Lead score: {lead.lead_score}/100")
    return "\n".join(lines)


# ── AI message generator ──────────────────────────────────────────────────────

class MessageGenerator:
    """
    Generates personalised outreach messages using Claude AI.
    Falls back to template-based messages if API key not available.
    """

    def __init__(self):
        self.client = None
        if ai_cfg.anthropic_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=ai_cfg.anthropic_key)
                logger.info("Anthropic client initialised — AI messages enabled.")
            except ImportError:
                logger.warning("anthropic SDK not installed. Run: pip install anthropic")

    def generate_all(self, lead: Lead) -> List[OutreachMessage]:
        """
        Generate LinkedIn connection request, LinkedIn message,
        and email sequence for a lead.
        """
        messages = []
        lead_summary = _build_lead_summary(lead)

        # LinkedIn connection request
        conn_msg = self._generate_linkedin_connection(lead, lead_summary)
        if conn_msg:
            messages.append(conn_msg)

        # LinkedIn direct message
        dm_msg = self._generate_linkedin_dm(lead, lead_summary)
        if dm_msg:
            messages.append(dm_msg)

        # Cold email sequence (only if email found)
        if lead.email:
            email_msg = self._generate_email_sequence(lead, lead_summary)
            if email_msg:
                messages.append(email_msg)

        return messages

    def _generate_linkedin_connection(
        self, lead: Lead, lead_summary: str
    ) -> Optional[OutreachMessage]:
        prompt = CONNECTION_REQUEST_PROMPT.format(lead_summary=lead_summary)
        text = self._call_ai(prompt) or self._fallback_connection_request(lead)

        # Enforce 300 char limit
        if len(text) > 300:
            text = text[:297] + "..."

        return OutreachMessage(
            lead_id=lead.id or "",
            channel=OutreachChannel.LINKEDIN_CONNECTION,
            message=text,
        )

    def _generate_linkedin_dm(
        self, lead: Lead, lead_summary: str
    ) -> Optional[OutreachMessage]:
        prompt = LINKEDIN_MESSAGE_PROMPT.format(
            lead_summary=lead_summary, agency=agency.name
        )
        text = self._call_ai(prompt) or self._fallback_linkedin_dm(lead)

        return OutreachMessage(
            lead_id=lead.id or "",
            channel=OutreachChannel.LINKEDIN_MESSAGE,
            message=text,
        )

    def _generate_email_sequence(
        self, lead: Lead, lead_summary: str
    ) -> Optional[OutreachMessage]:
        prompt = EMAIL_PROMPT.format(
            lead_summary=lead_summary, agency=agency.name
        )
        raw = self._call_ai(prompt)

        if raw:
            try:
                # Strip markdown fences if present
                cleaned = raw.strip().strip("```json").strip("```").strip()
                data = json.loads(cleaned)
                return OutreachMessage(
                    lead_id=lead.id or "",
                    channel=OutreachChannel.EMAIL,
                    subject=data.get("subject", "Quick question about your marketing"),
                    message=data.get("body", ""),
                    follow_up_1=data.get("follow_up_1"),
                    follow_up_2=data.get("follow_up_2"),
                    follow_up_3=data.get("follow_up_3"),
                )
            except json.JSONDecodeError:
                logger.debug("AI returned non-JSON email — using fallback.")

        return self._fallback_email(lead)

    def _call_ai(self, user_prompt: str) -> Optional[str]:
        """Call Claude API and return the response text."""
        if not self.client:
            return None
        try:
            response = self.client.messages.create(
                model=ai_cfg.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.warning("AI message generation error: %s", exc)
            return None

    # ── Fallback templates (no AI key required) ──────────────────────────────

    def _fallback_connection_request(self, lead: Lead) -> str:
        first = lead.first_name or "there"
        industry = lead.industry or "your industry"
        return (
            f"Hi {first}, I help {industry} businesses scale revenue through "
            f"data-driven digital marketing. Would love to connect and share "
            f"a few ideas specific to your business."
        )[:300]

    def _fallback_linkedin_dm(self, lead: Lead) -> str:
        first = lead.first_name or "there"
        company = lead.company_name or "your company"
        pain = lead.pain_points[0] if lead.pain_points else "growing your online presence"
        service = lead.services_needed[0] if lead.services_needed else "digital marketing"

        return (
            f"Hi {first},\n\n"
            f"I noticed {company} and saw an opportunity around {pain}.\n\n"
            f"At {agency.name}, we've helped similar businesses in {lead.industry or 'your industry'} "
            f"generate more leads through {service} — typically seeing results within 60-90 days.\n\n"
            f"Would it make sense to jump on a 15-min call this week to explore whether "
            f"we could do the same for you?\n\n"
            f"Best,\n{agency.sender_name}\n{agency.sender_title}, {agency.name}\n{agency.website}"
        )

    def _fallback_email(self, lead: Lead) -> OutreachMessage:
        first = lead.first_name or "there"
        company = lead.company_name or "your business"
        pain = lead.pain_points[0] if lead.pain_points else "limited online visibility"
        service = lead.services_needed[0] if lead.services_needed else "digital marketing"
        industry = lead.industry or "your industry"

        subject = f"Quick question about {company}'s online growth"

        body = (
            f"Hi {first},\n\n"
            f"I came across {company} and noticed {pain} — "
            f"something we see a lot with {industry} businesses.\n\n"
            f"At {agency.name} ({agency.website}), we specialise in helping "
            f"{industry} businesses like yours get more qualified leads online "
            f"through {service}. One of our recent clients in a similar space "
            f"saw a 3x increase in inbound leads within 90 days.\n\n"
            f"Would you be open to a 15-minute call this week to see if we'd "
            f"be a good fit?\n\n"
            f"Best regards,\n"
            f"{agency.sender_name}\n"
            f"{agency.sender_title} | {agency.name}\n"
            f"{agency.email} | {agency.website}"
        )

        follow_up_1 = (
            f"Hi {first},\n\n"
            f"Just following up on my last email. "
            f"We recently helped a {industry} business double their Google leads in 90 days — "
            f"happy to share the case study if useful.\n\n"
            f"Still interested in a quick call?\n\n"
            f"{agency.sender_name}"
        )

        follow_up_2 = (
            f"Hi {first},\n\n"
            f"Quick value-add: did you know that 97% of consumers look up "
            f"a local business online before visiting? If {company} isn't "
            f"showing up in the top 3 Google results, you're likely losing "
            f"leads to competitors.\n\n"
            f"Worth a conversation? 15 min is all it takes.\n\n"
            f"{agency.sender_name}"
        )

        follow_up_3 = (
            f"Hi {first},\n\n"
            f"I'll keep this short — I know timing matters. "
            f"If digital marketing ever becomes a priority for {company}, "
            f"I'm here. Happy to share a free audit anytime.\n\n"
            f"{agency.sender_name} | {agency.name}"
        )

        return OutreachMessage(
            lead_id=lead.id or "",
            channel=OutreachChannel.EMAIL,
            subject=subject,
            message=body,
            follow_up_1=follow_up_1,
            follow_up_2=follow_up_2,
            follow_up_3=follow_up_3,
        )


# ── Batch generator ───────────────────────────────────────────────────────────

def generate_outreach_batch(
    leads: List[Lead],
    min_score: int = 50,
) -> List[OutreachMessage]:
    """
    Generate outreach messages for all qualifying leads.
    Only generates for leads scoring >= min_score.
    """
    generator = MessageGenerator()
    all_messages: List[OutreachMessage] = []

    qualifying = [l for l in leads if l.lead_score >= min_score and l.icp_match]
    logger.info(
        "Generating outreach for %d qualifying leads (score >= %d, ICP match).",
        len(qualifying), min_score
    )

    for i, lead in enumerate(qualifying, 1):
        logger.info(
            "  [%d/%d] %s @ %s (score=%d)",
            i, len(qualifying),
            lead.full_name or lead.company_name,
            lead.company_name or "",
            lead.lead_score,
        )
        messages = generator.generate_all(lead)
        all_messages.extend(messages)

    logger.info("Generated %d outreach messages total.", len(all_messages))
    return all_messages
