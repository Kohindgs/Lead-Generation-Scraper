"""
Lead Enrichment & ICP Scoring Engine
======================================
Enriches raw lead data with:
  1. Email discovery (Hunter.io / Apollo.io)
  2. Company website analysis (SEO audit signals)
  3. Social presence audit (LinkedIn, Facebook, Instagram)
  4. ICP (Ideal Customer Profile) matching
  5. Lead scoring (0-100) — used to prioritise outreach

ICP for DGenius Solutions:
  - B2B or B2C businesses with 1-200 employees
  - In a high-margin industry (Real Estate, Legal, Healthcare, etc.)
  - Decision-maker reachable via LinkedIn or email
  - Currently under-investing in digital marketing
    (few reviews / low social presence / no Google ranking)
"""
import re
from typing import List, Optional
from urllib.parse import urlparse

import requests

from src.config import enrich_cfg, agency
from src.models import Lead, LeadSource
from src.utils.helpers import (
    clean_text, extract_domain, get_logger, human_delay, build_proxy_dict,
)

logger = get_logger(__name__)

# ── ICP criteria ──────────────────────────────────────────────────────────────

ICP_INDUSTRIES = {
    # High-value: digital marketing ROI is very clear
    "tier_1": [
        "Real Estate", "Legal Services", "Healthcare", "Financial Services",
        "E-commerce", "SaaS / Technology", "Insurance",
    ],
    # Good fit
    "tier_2": [
        "Education", "Hospitality", "Retail", "Fitness", "Beauty & Wellness",
        "Automotive", "Construction", "Professional Services",
    ],
    # Lower priority
    "tier_3": [
        "Local Business", "Food & Beverage", "Manufacturing",
        "Non-Profit", "Government",
    ],
}

ICP_SENIORITY = ["c-suite", "owner", "director"]

ICP_COMPANY_SIZES = {
    "1-10": 1.0,
    "11-50": 1.2,
    "51-200": 1.1,
    "201-500": 0.8,
    "501-1000": 0.5,
    "1001+": 0.2,
}


# ── Email finder ─────────────────────────────────────────────────────────────

class EmailFinder:
    """Finds verified business emails using Hunter.io or Apollo.io APIs."""

    def __init__(self):
        self.hunter_key = enrich_cfg.hunter_key
        self.apollo_key = enrich_cfg.apollo_key
        self.session = requests.Session()
        proxies = build_proxy_dict()
        if proxies:
            self.session.proxies.update(proxies)

    def find_email(self, lead: Lead) -> Optional[str]:
        """Try to find a verified email for a lead."""
        # Skip if we already have one
        if lead.email:
            return lead.email

        if self.hunter_key:
            email = self._hunter_find(lead)
            if email:
                return email

        if self.apollo_key:
            email = self._apollo_find(lead)
            if email:
                return email

        # Fallback: pattern guessing
        return self._guess_email(lead)

    def _hunter_find(self, lead: Lead) -> Optional[str]:
        """Use Hunter.io email finder."""
        domain = extract_domain(lead.company_website or "")
        if not domain or not lead.first_name:
            return None
        try:
            resp = self.session.get(
                "https://api.hunter.io/v2/email-finder",
                params={
                    "domain": domain,
                    "first_name": lead.first_name,
                    "last_name": lead.last_name,
                    "api_key": self.hunter_key,
                },
                timeout=10,
            )
            data = resp.json().get("data", {})
            email = data.get("email")
            score = data.get("score", 0)
            if email and score >= 50:
                logger.debug("Hunter found email for %s: %s (score=%d)", lead.full_name, email, score)
                return email
        except Exception as exc:
            logger.debug("Hunter error: %s", exc)
        return None

    def _apollo_find(self, lead: Lead) -> Optional[str]:
        """Use Apollo.io people search to find email."""
        try:
            resp = self.session.post(
                "https://api.apollo.io/v1/people/match",
                json={
                    "first_name": lead.first_name,
                    "last_name": lead.last_name,
                    "organization_name": lead.company_name,
                    "domain": extract_domain(lead.company_website or ""),
                },
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": self.apollo_key,
                },
                timeout=10,
            )
            person = resp.json().get("person", {})
            email = person.get("email")
            if email and "apollo" not in email:
                logger.debug("Apollo found email for %s: %s", lead.full_name, email)
                return email
        except Exception as exc:
            logger.debug("Apollo error: %s", exc)
        return None

    @staticmethod
    def _guess_email(lead: Lead) -> Optional[str]:
        """
        Heuristic email pattern guessing.
        Not verified — mark lead as unverified.
        Common patterns: first.last@domain.com, first@domain.com, etc.
        """
        domain = extract_domain(lead.company_website or "")
        if not domain or not lead.first_name:
            return None

        first = lead.first_name.lower()
        last = lead.last_name.lower() if lead.last_name else ""

        patterns = []
        if last:
            patterns = [
                f"{first}.{last}@{domain}",
                f"{first[0]}{last}@{domain}",
                f"{first}@{domain}",
                f"info@{domain}",
                f"hello@{domain}",
                f"contact@{domain}",
            ]
        else:
            patterns = [f"info@{domain}", f"hello@{domain}", f"contact@{domain}"]

        return patterns[0]  # return most likely; mark as unverified


# ── Website presence auditor ─────────────────────────────────────────────────

class WebsiteAuditor:
    """
    Quick audit of a business's online presence.
    Identifies pain points that DGenius Solutions can address.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; DGeniusBot/1.0)"
        })
        self.session.timeout = 8
        proxies = build_proxy_dict()
        if proxies:
            self.session.proxies.update(proxies)

    def audit(self, lead: Lead) -> dict:
        """
        Returns a dict with audit results:
          - has_website, has_ssl, has_og_tags, has_schema,
            page_speed_guess, social_links, pain_points
        """
        url = lead.company_website
        if not url:
            return {
                "has_website": False,
                "pain_points": ["No website"],
                "services_recommended": ["Website Design & Development", "SEO"],
            }

        if not url.startswith("http"):
            url = "https://" + url

        result = {
            "has_website": False,
            "has_ssl": url.startswith("https"),
            "has_og_tags": False,
            "has_schema": False,
            "has_google_analytics": False,
            "has_facebook_pixel": False,
            "has_chatbot": False,
            "mobile_friendly": None,
            "social_links": [],
            "pain_points": [],
            "services_recommended": [],
        }

        try:
            resp = self.session.get(url, timeout=8, allow_redirects=True)
            if resp.status_code == 200:
                result["has_website"] = True
                html = resp.text.lower()

                result["has_og_tags"] = 'og:title' in html
                result["has_schema"] = 'application/ld+json' in html
                result["has_google_analytics"] = (
                    'google-analytics.com' in html or 'gtag(' in html
                )
                result["has_facebook_pixel"] = 'fbevents.js' in html
                result["has_chatbot"] = any(
                    k in html for k in ["intercom", "drift.com", "tawk.to", "crisp.chat"]
                )

                # Social links
                for sn in ["facebook.com", "instagram.com", "linkedin.com",
                            "twitter.com", "youtube.com"]:
                    if sn in html:
                        result["social_links"].append(sn.split(".")[0])

                # Pain points analysis
                if not result["has_ssl"]:
                    result["pain_points"].append("No SSL certificate")
                    result["services_recommended"].append("Website Development")
                if not result["has_og_tags"]:
                    result["pain_points"].append("No Open Graph / social sharing tags")
                    result["services_recommended"].append("SEO & Content Marketing")
                if not result["has_schema"]:
                    result["pain_points"].append("No Schema markup")
                    result["services_recommended"].append("SEO")
                if not result["has_google_analytics"]:
                    result["pain_points"].append("No Google Analytics tracking")
                    result["services_recommended"].append("Marketing Analytics")
                if not result["has_facebook_pixel"]:
                    result["pain_points"].append("No Facebook/Meta Pixel")
                    result["services_recommended"].append("Social Media Advertising")
                if len(result["social_links"]) < 2:
                    result["pain_points"].append("Limited social media presence")
                    result["services_recommended"].append("Social Media Marketing")
        except requests.exceptions.SSLError:
            result["has_ssl"] = False
            result["has_website"] = True
            result["pain_points"].append("SSL certificate error")
        except Exception as exc:
            result["pain_points"].append(f"Website not accessible: {type(exc).__name__}")
            result["services_recommended"].append("Website Development")

        return result


# ── ICP Scorer ───────────────────────────────────────────────────────────────

class ICPScorer:
    """
    Scores leads against DGenius Solutions' Ideal Customer Profile (ICP).
    Produces a 0-100 score + boolean ICP match flag.
    """

    @staticmethod
    def score(lead: Lead, audit: Optional[dict] = None) -> tuple[int, bool]:
        """
        Returns (score: int, icp_match: bool).
        score >= 60 → qualified lead.
        score >= 75 → hot lead.
        """
        score = 0

        # 1. Industry tier (max 25 pts)
        industry = lead.industry or ""
        if any(ind.lower() in industry.lower() for ind in ICP_INDUSTRIES["tier_1"]):
            score += 25
        elif any(ind.lower() in industry.lower() for ind in ICP_INDUSTRIES["tier_2"]):
            score += 15
        elif any(ind.lower() in industry.lower() for ind in ICP_INDUSTRIES["tier_3"]):
            score += 8

        # 2. Seniority (max 20 pts)
        if lead.seniority in ICP_SENIORITY:
            score += 20
        elif lead.seniority == "manager":
            score += 12

        # 3. Contact completeness (max 15 pts)
        if lead.email:
            score += 8
        if lead.linkedin_url:
            score += 4
        if lead.phone:
            score += 3

        # 4. Pain points (max 20 pts — more pain = hotter lead)
        pain_count = len(lead.pain_points)
        score += min(pain_count * 5, 20)

        # 5. Website audit insights (max 15 pts)
        if audit:
            if not audit.get("has_website"):
                score += 15
            else:
                audit_pain = len(audit.get("pain_points", []))
                score += min(audit_pain * 3, 12)

        # 6. Buying signals (max 5 pts)
        score += min(len(lead.buying_signals) * 2, 5)

        # Cap & determine ICP match
        score = min(score, 100)
        icp_match = score >= 55

        return score, icp_match


# ── Main enrichment pipeline ─────────────────────────────────────────────────

class LeadEnricher:
    """
    Orchestrates enrichment: email finding, website audit, ICP scoring.
    Mutates the Lead objects in-place and returns updated list.
    """

    def __init__(self):
        self.email_finder = EmailFinder()
        self.website_auditor = WebsiteAuditor()
        self.icp_scorer = ICPScorer()

    def enrich(self, leads: List[Lead], audit_websites: bool = True) -> List[Lead]:
        """Enrich a batch of leads."""
        logger.info("Enriching %d leads …", len(leads))

        for i, lead in enumerate(leads, 1):
            logger.debug("  [%d/%d] %s", i, len(leads), lead.full_name or lead.company_name)

            # Email discovery
            email = self.email_finder.find_email(lead)
            if email and not lead.email:
                lead.email = email
                lead.email_verified = False  # mark as unverified guess

            # Website audit
            audit_result = {}
            if audit_websites and lead.company_website:
                try:
                    audit_result = self.website_auditor.audit(lead)
                    # Merge pain points
                    for pain in audit_result.get("pain_points", []):
                        if pain not in lead.pain_points:
                            lead.pain_points.append(pain)
                    for svc in audit_result.get("services_recommended", []):
                        if svc not in lead.services_needed:
                            lead.services_needed.append(svc)
                except Exception as exc:
                    logger.debug("Audit error for %s: %s", lead.company_website, exc)

            # ICP scoring
            score, icp_match = self.icp_scorer.score(lead, audit_result)
            lead.lead_score = score
            lead.icp_match = icp_match

            human_delay(0.5, 1.5)

        # Sort by score descending
        leads.sort(key=lambda l: l.lead_score, reverse=True)
        logger.info(
            "Enrichment complete. ICP matches: %d / %d",
            sum(1 for l in leads if l.icp_match), len(leads)
        )
        return leads
