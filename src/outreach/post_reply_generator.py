"""
LinkedIn Post Reply / DM Generator
====================================
Generates highly personalised, context-aware DMs for service-request posts.

The DM must feel like a genuine, helpful response — NOT a copy-paste pitch.
It references the specific service they asked for, their title/company (if known),
and positions DGenius Solutions as the natural answer to their request.

Two generation modes:
  1. AI mode  — uses Claude/OpenAI API for maximum personalisation
  2. Template mode — rule-based fallback (no API key needed)
"""
from __future__ import annotations

import os
import random
from typing import Optional

from src.config import agency
from src.models import ServiceRequestPost
from src.utils.helpers import get_logger

logger = get_logger(__name__)

# ── Load AI settings ──────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
USE_AI            = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE LIBRARY
# Short, conversational DMs under 300 chars (LinkedIn DM best practice)
# ─────────────────────────────────────────────────────────────────────────────

DM_TEMPLATES: dict[str, list[str]] = {
    "Web Design & Development": [
        "Hi {first_name}! Saw your post about needing a website — we specialise in "
        "high-converting sites for {industry} businesses. Happy to share some examples "
        "and a quick quote if useful?",

        "Hey {first_name}, your post caught my eye — we build clean, fast websites "
        "that actually bring in leads. Could send over a couple of examples relevant "
        "to your industry if you're still looking?",

        "Hi {first_name}! We've built websites for several {industry} businesses — "
        "results-focused, fast turnaround. Would love to help. Want me to send a few "
        "recent examples?",
    ],
    "SEO": [
        "Hi {first_name}! Noticed you're looking for SEO help — we've taken several "
        "{industry} businesses to page 1 of Google. Happy to do a quick free audit "
        "of your site if that would be helpful?",

        "Hey {first_name}, your SEO post resonated — it's one of our core strengths. "
        "I can pull a quick report showing exactly where your site stands and what's "
        "holding it back. Interested?",

        "Hi {first_name}! We specialise in local & national SEO for {industry} "
        "businesses. I could do a free audit and show you what quick wins are "
        "available — no obligation. Worth a look?",
    ],
    "Social Media Marketing": [
        "Hi {first_name}! Saw your post about social media management — we handle "
        "content, growth, and ads for {industry} businesses. Happy to share our "
        "approach and some results if you're still searching?",

        "Hey {first_name}, social media for business can be a full-time job! We "
        "manage it end-to-end so you can focus on running things. Want to see some "
        "examples from similar businesses?",

        "Hi {first_name}! We run social media for several {industry} businesses "
        "— content, scheduling, engagement, ads. Could share a portfolio and pricing "
        "overview if helpful?",
    ],
    "Google Ads / PPC": [
        "Hi {first_name}! We manage Google Ads campaigns for {industry} businesses "
        "— focused on ROI, not just clicks. Happy to review your current setup (or "
        "start fresh) and show you what's possible?",

        "Hey {first_name}, saw you're looking for ads help. We run PPC campaigns "
        "that actually convert. Could share a quick case study relevant to your "
        "niche if you're still considering your options?",

        "Hi {first_name}! Google Ads done right can transform lead flow for "
        "{industry} businesses. I could do a free account audit or estimate — "
        "would that be useful?",
    ],
    "Digital Marketing (General)": [
        "Hi {first_name}! We're a digital marketing agency that works specifically "
        "with {industry} businesses — strategy, leads, and growth. Happy to jump "
        "on a quick call to see if we're a good fit?",

        "Hey {first_name}, your post about marketing help caught my eye — it's "
        "exactly what we do for {industry} businesses. Could share some results "
        "and a quick overview of our approach?",

        "Hi {first_name}! Growing a business online is tough without the right "
        "team. We handle the full digital side so you can focus on delivery. "
        "Worth a 15-min call to explore?",
    ],
    "Reputation Management": [
        "Hi {first_name}! Reputation management is something we're strong at — "
        "we help {industry} businesses grow their Google reviews and manage their "
        "online image. Happy to show you how it works?",

        "Hey {first_name}, getting consistent quality reviews is a system — "
        "we've built it for lots of businesses. Could share how it works in a "
        "quick overview if you're interested?",
    ],
    "Video Marketing": [
        "Hi {first_name}! Video marketing is one of the best ROI channels right "
        "now. We produce short-form promo content for {industry} businesses — "
        "could share some examples?",

        "Hey {first_name}, your post about video content resonated — we do this "
        "for {industry} businesses. From scripting to final edit. Happy to share "
        "some samples?",
    ],
    "Branding & Logo": [
        "Hi {first_name}! Branding done well makes everything else easier — we "
        "specialise in brand identity for {industry} businesses. Happy to share "
        "some recent work?",

        "Hey {first_name}, saw you need branding / design help — it's a core "
        "part of what we do. Could send over a portfolio and quick outline of "
        "our process if useful?",
    ],
}

# Generic fallback
GENERIC_TEMPLATES = [
    "Hi {first_name}! Your post caught my attention — we help {industry} "
    "businesses with exactly that. Happy to share some relevant work and see "
    "if we could be a good fit?",

    "Hey {first_name}! This is right in our wheelhouse — we've helped several "
    "{industry} businesses with this. Would love to connect and share some "
    "results. Worth a quick chat?",

    "Hi {first_name}! Saw your post and thought I could genuinely help. We "
    "specialise in digital growth for {industry} businesses. Could share some "
    "relevant examples if you're still looking?",
]

# Follow-up DMs (sent 3-5 days later if no reply)
FOLLOW_UP_TEMPLATES = [
    "Hi {first_name}! Just circling back on my earlier message — did you "
    "manage to find someone for your {service} needs? Happy to help if not!",

    "Hey {first_name}, I know inboxes get busy! Just wanted to check if my "
    "message about {service} was useful. No worries if you've sorted it — "
    "happy to connect either way.",
]


# ─────────────────────────────────────────────────────────────────────────────
# GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class PostReplyGenerator:
    """Generates personalised DM replies to LinkedIn service-request posts."""

    def generate(self, post: ServiceRequestPost) -> str:
        """Return a ready-to-send DM message for the given post."""
        if USE_AI:
            dm = self._generate_with_ai(post)
            if dm:
                return dm
        return self._generate_from_template(post)

    def generate_follow_up(self, post: ServiceRequestPost) -> str:
        """Generate a follow-up DM."""
        service = post.services_requested[0] if post.services_requested else "your project"
        template = random.choice(FOLLOW_UP_TEMPLATES)
        return template.format(
            first_name=post.poster_first_name or post.poster_name.split()[0],
            service=service,
        )

    # ── AI generation ─────────────────────────────────────────────────────────

    def _generate_with_ai(self, post: ServiceRequestPost) -> Optional[str]:
        """Generate DM using Claude or OpenAI API."""
        prompt = self._build_ai_prompt(post)

        if ANTHROPIC_API_KEY:
            return self._call_claude(prompt)
        elif OPENAI_API_KEY:
            return self._call_openai(prompt)
        return None

    def _build_ai_prompt(self, post: ServiceRequestPost) -> str:
        services_str = ", ".join(post.services_requested) or "digital marketing"
        return f"""You are a senior sales consultant at {agency.name}, a digital marketing agency.

Write a SHORT, GENUINE LinkedIn DM (under 280 characters) to this person who posted asking for help:

POSTER: {post.poster_name}
THEIR TITLE: {post.poster_title or 'Business Owner'}
THEIR POST: "{post.post_text[:400]}"
SERVICES THEY NEED: {services_str}
URGENCY: {post.urgency}

DM RULES:
- Start with their first name only ('{post.poster_first_name or post.poster_name.split()[0]}')
- Reference their SPECIFIC request naturally (don't be generic)
- Mention we specialise in this for businesses like theirs
- End with a soft, low-pressure CTA (offer examples / audit / quick call)
- DO NOT use emojis, buzzwords, or corporate speak
- Sound like a real person, not a bot
- Keep under 280 characters total
- Do NOT include any hashtags or links

Return ONLY the DM text, nothing else."""

    def _call_claude(self, prompt: str) -> Optional[str]:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            logger.debug("Claude DM generated (%d chars)", len(text))
            return text
        except Exception as exc:
            logger.warning("Claude API error: %s", exc)
            return None

    def _call_openai(self, prompt: str) -> Optional[str]:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.choices[0].message.content.strip()
            logger.debug("OpenAI DM generated (%d chars)", len(text))
            return text
        except Exception as exc:
            logger.warning("OpenAI API error: %s", exc)
            return None

    # ── Template generation ───────────────────────────────────────────────────

    def _generate_from_template(self, post: ServiceRequestPost) -> str:
        """Pick best-matching template and fill variables."""
        first_name = post.poster_first_name or (
            post.poster_name.split()[0] if post.poster_name else "there"
        )
        industry = self._infer_industry(post.poster_title, post.poster_company)

        # Find matching template group
        templates = GENERIC_TEMPLATES
        for service in post.services_requested:
            if service in DM_TEMPLATES:
                templates = DM_TEMPLATES[service]
                break

        template = random.choice(templates)
        return template.format(
            first_name=first_name,
            industry=industry,
            service=post.services_requested[0] if post.services_requested else "digital marketing",
            agency_name=agency.name,
        ).strip()

    @staticmethod
    def _infer_industry(title: str, company: str) -> str:
        """Infer a readable industry label from title/company."""
        text = f"{title} {company}".lower()
        if any(w in text for w in ["dental", "dentist", "clinic", "medical", "health"]):
            return "healthcare"
        if any(w in text for w in ["law", "legal", "solicitor", "attorney"]):
            return "legal"
        if any(w in text for w in ["real estate", "property", "realtor"]):
            return "real estate"
        if any(w in text for w in ["restaurant", "cafe", "food", "catering"]):
            return "hospitality"
        if any(w in text for w in ["gym", "fitness", "yoga", "wellness"]):
            return "fitness"
        if any(w in text for w in ["salon", "beauty", "spa", "barber"]):
            return "beauty"
        if any(w in text for w in ["retail", "store", "shop", "boutique"]):
            return "retail"
        if any(w in text for w in ["coach", "consultant", "trainer", "advisor"]):
            return "coaching"
        return "local"
