"""
LinkedIn Lead Scraper for DGenius Solutions
============================================
Scrapes decision-maker profiles from LinkedIn using:
  1. linkedin-api (unofficial API wrapper — fastest, no browser needed)
  2. Selenium fallback for Sales Navigator / deep scraping

IMPORTANT: Always comply with LinkedIn's Terms of Service.
Use this tool only for legitimate B2B prospecting.
"""
import random
import time
import uuid
from typing import List, Optional
from urllib.parse import quote_plus

import requests

from src.config import linkedin_cfg, scraper_cfg, agency
from src.models import Lead, LeadSource, LeadStatus
from src.utils.database import upsert_lead
from src.utils.helpers import (
    clean_text, extract_email, extract_phone,
    generate_lead_id, get_logger, human_delay,
)

logger = get_logger(__name__)


# ── Title → seniority mapping ─────────────────────────────────────────────────

SENIORITY_MAP = {
    "c-suite":  ["ceo", "coo", "cmo", "cto", "cfo", "chief"],
    "director": ["director", "vp ", "vice president", "head of"],
    "manager":  ["manager", "lead", "supervisor"],
    "owner":    ["owner", "founder", "co-founder", "partner", "proprietor"],
}


def infer_seniority(title: str) -> str:
    t = title.lower()
    for seniority, keywords in SENIORITY_MAP.items():
        if any(k in t for k in keywords):
            return seniority
    return "individual_contributor"


# ── Keyword signals ───────────────────────────────────────────────────────────

BUYING_SIGNALS = [
    "hiring", "growing", "expansion", "new office", "launching",
    "raised funding", "series a", "series b", "ipo", "partnership",
    "open to opportunities", "looking for", "need help", "struggling",
]

PAIN_SIGNALS = [
    "no online presence", "low traffic", "few reviews",
    "poor social media", "no website", "bad google ranking",
    "no digital marketing", "traditional marketing only",
]


# ── LinkedIn API Scraper ──────────────────────────────────────────────────────

class LinkedInScraper:
    """
    Uses the unofficial LinkedIn API (linkedin-api package) to search
    for decision-makers matching DGenius Solutions' ideal customer profile.
    """

    def __init__(self):
        self.api = None
        self._authenticated = False

    def authenticate(self) -> bool:
        """Authenticate with LinkedIn."""
        try:
            from linkedin_api import Linkedin
            logger.info("Authenticating with LinkedIn as %s …", linkedin_cfg.email)
            self.api = Linkedin(linkedin_cfg.email, linkedin_cfg.password)
            self._authenticated = True
            logger.info("LinkedIn authentication successful.")
            return True
        except ImportError:
            logger.warning(
                "linkedin-api not installed. Run: pip install linkedin-api"
            )
            return False
        except Exception as exc:
            logger.error("LinkedIn auth failed: %s", exc)
            return False

    def search_people(
        self,
        keywords: Optional[str] = None,
        industries: Optional[List[str]] = None,
        titles: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        company_sizes: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Lead]:
        """
        Search LinkedIn for people matching the given filters.
        Returns a list of Lead objects.
        """
        if not self._authenticated and not self.authenticate():
            logger.error("Cannot search — not authenticated.")
            return []

        industries = industries or linkedin_cfg.target_industries
        titles = titles or linkedin_cfg.target_titles
        locations = locations or linkedin_cfg.target_locations

        leads: List[Lead] = []
        scraped_ids: set = set()

        # Rotate through title + industry combos for diversity
        combos = [
            (t, ind)
            for t in titles[:5]        # top 5 titles
            for ind in industries[:4]  # top 4 industries
        ]
        random.shuffle(combos)

        for title_kw, industry in combos:
            if len(leads) >= limit:
                break

            search_kw = keywords or f"{title_kw} {industry}"
            logger.info("Searching LinkedIn: '%s' | industry: %s", search_kw, industry)

            try:
                results = self.api.search_people(
                    keywords=search_kw,
                    keyword_title=title_kw,
                    limit=min(25, limit - len(leads)),
                )
            except Exception as exc:
                logger.warning("Search error (%s / %s): %s", title_kw, industry, exc)
                human_delay(5, 10)
                continue

            for result in results:
                profile_id = result.get("urn_id") or result.get("entityUrn", "")
                if profile_id in scraped_ids:
                    continue
                scraped_ids.add(profile_id)

                lead = self._result_to_lead(result, profile_id, industry)
                if lead:
                    leads.append(lead)
                    upsert_lead(lead)
                    logger.debug("  ✓ %s – %s @ %s", lead.full_name, lead.title, lead.company_name)

                human_delay(1, 3)

            human_delay()  # polite pause between searches

        logger.info("LinkedIn search complete. Collected %d leads.", len(leads))
        return leads

    def get_profile(self, linkedin_url: str) -> Optional[Lead]:
        """Fetch a single profile by URL."""
        if not self._authenticated and not self.authenticate():
            return None

        try:
            # Extract the public identifier from URL
            public_id = linkedin_url.rstrip("/").split("/")[-1]
            profile = self.api.get_profile(public_id)
            return self._profile_to_lead(profile)
        except Exception as exc:
            logger.error("Failed to fetch profile %s: %s", linkedin_url, exc)
            return None

    # ── Private helpers ──────────────────────────────────────────────────────

    def _result_to_lead(self, result: dict, profile_id: str, industry: str) -> Optional[Lead]:
        """Convert a search result dict to a Lead."""
        try:
            name = result.get("name", "")
            parts = name.split(" ", 1)
            first = parts[0] if parts else ""
            last = parts[1] if len(parts) > 1 else ""

            title = clean_text(result.get("jobtitle") or result.get("headline", ""))
            company = clean_text(result.get("subline", "").split(" at ")[-1])
            location = clean_text(result.get("location", ""))

            linkedin_url = (
                f"https://www.linkedin.com/in/{result.get('publicIdentifier', profile_id)}"
            )

            lead_id = generate_lead_id("linkedin", profile_id)

            # Parse location
            city, country = "", ""
            if "," in location:
                parts = location.split(",")
                city = parts[0].strip()
                country = parts[-1].strip()
            else:
                country = location

            signals = self._detect_buying_signals(f"{title} {company} {location}")

            return Lead(
                id=lead_id,
                first_name=first,
                last_name=last,
                full_name=name,
                title=title,
                seniority=infer_seniority(title),
                company_name=company,
                industry=industry,
                city=city,
                country=country,
                linkedin_url=linkedin_url,
                source=LeadSource.LINKEDIN,
                status=LeadStatus.NEW,
                buying_signals=signals,
            )
        except Exception as exc:
            logger.debug("Could not parse search result: %s | %s", result, exc)
            return None

    def _profile_to_lead(self, profile: dict) -> Optional[Lead]:
        """Convert a full profile dict to a Lead."""
        try:
            first = clean_text(profile.get("firstName", ""))
            last = clean_text(profile.get("lastName", ""))
            full = f"{first} {last}".strip()

            experience = profile.get("experience", [{}])
            current = experience[0] if experience else {}

            title = clean_text(current.get("title", ""))
            company = clean_text(
                (current.get("companyName") or current.get("company", {}).get("name", ""))
            )

            industry = clean_text(profile.get("industryName", ""))
            location = clean_text(profile.get("locationName", ""))
            city = clean_text(profile.get("geoLocationName", ""))
            country = clean_text(profile.get("geoCountryName", ""))
            summary = clean_text(profile.get("summary", ""))

            public_id = profile.get("publicIdentifier", "")
            linkedin_url = f"https://www.linkedin.com/in/{public_id}" if public_id else None
            profile_id = profile.get("entityUrn", public_id or str(uuid.uuid4()))
            lead_id = generate_lead_id("linkedin", profile_id)

            # Extract contact info from profile
            contact = profile.get("phoneNumbers", [])
            phone = contact[0].get("number") if contact else None

            emails_data = profile.get("emailAddresses", [])
            email = emails_data[0].get("emailAddress") if emails_data else None

            signals = self._detect_buying_signals(f"{title} {company} {summary}")

            return Lead(
                id=lead_id,
                first_name=first,
                last_name=last,
                full_name=full,
                title=title,
                seniority=infer_seniority(title),
                company_name=company,
                industry=industry,
                company_description=summary[:500],
                email=email,
                phone=phone,
                city=city,
                country=country,
                linkedin_url=linkedin_url,
                source=LeadSource.LINKEDIN,
                status=LeadStatus.NEW,
                buying_signals=signals,
            )
        except Exception as exc:
            logger.debug("Could not parse profile: %s", exc)
            return None

    @staticmethod
    def _detect_buying_signals(text: str) -> List[str]:
        text_lower = text.lower()
        return [s for s in BUYING_SIGNALS if s in text_lower]


# ── LinkedIn Search-URL builder (for manual outreach) ────────────────────────

class LinkedInSearchURLBuilder:
    """
    Builds LinkedIn Search URLs that a sales rep can open directly
    (no API needed — just click the link).
    """
    BASE = "https://www.linkedin.com/search/results/people/?"

    @staticmethod
    def build(
        keywords: str = "",
        titles: Optional[List[str]] = None,
        industries: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
    ) -> str:
        params = []
        if keywords:
            params.append(f"keywords={quote_plus(keywords)}")
        if titles:
            joined = quote_plus(" OR ".join(f'"{t}"' for t in titles))
            params.append(f"titleFilter={joined}")
        if locations:
            joined = quote_plus(" OR ".join(locations))
            params.append(f"geoUrn={joined}")
        return LinkedInSearchURLBuilder.BASE + "&".join(params)

    @staticmethod
    def generate_campaign_urls() -> List[dict]:
        """
        Generate a set of ready-to-use LinkedIn search URLs for DGenius campaigns.
        Returns a list of dicts with {name, url, description}.
        """
        campaigns = []

        for industry in linkedin_cfg.target_industries[:6]:
            for title_group in [
                ["CEO", "Founder", "Owner"],
                ["Marketing Director", "CMO", "Head of Marketing"],
                ["Marketing Manager", "Digital Marketing Manager"],
            ]:
                name = f"{industry} – {title_group[0]}"
                url = LinkedInSearchURLBuilder.build(
                    keywords=f"{industry} marketing",
                    titles=title_group,
                    locations=linkedin_cfg.target_locations[:3],
                )
                campaigns.append({
                    "name": name,
                    "url": url,
                    "target_titles": title_group,
                    "target_industry": industry,
                    "description": (
                        f"Decision-makers in {industry} who may need "
                        "digital marketing services from DGenius Solutions"
                    ),
                })

        return campaigns
