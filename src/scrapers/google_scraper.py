"""
Google Lead Scraper for DGenius Solutions
==========================================
Two scraping strategies:

1. Google Maps API  — finds local businesses needing digital marketing
   (uses googlemaps SDK + Places API)

2. Google Search / SerpAPI — searches for business decision-makers,
   company directories, and buying-intent pages

Businesses with low review counts, no website, or poor online presence
are flagged as HIGH-PRIORITY leads.
"""
import time
import re
from typing import List, Optional, Dict, Any
from urllib.parse import quote_plus

import requests

from src.config import google_cfg, scraper_cfg, agency
from src.models import Lead, LeadSource, LeadStatus
from src.utils.database import upsert_lead
from src.utils.helpers import (
    clean_text, extract_email, extract_phone,
    generate_lead_id, get_logger, human_delay,
    build_proxy_dict, random_user_agent,
)

logger = get_logger(__name__)


# ── Priority scoring weights ──────────────────────────────────────────────────

def _score_google_maps_lead(place: dict) -> int:
    """
    Score a Google Maps business lead from 0-100.
    Higher score = stronger need for digital marketing.
    """
    score = 30  # baseline

    # Low rating = needs reputation management
    rating = place.get("rating", 5.0)
    if rating and rating < 3.5:
        score += 20
    elif rating and rating < 4.0:
        score += 10

    # Few reviews = low online presence
    reviews = place.get("user_ratings_total", 0)
    if reviews < 10:
        score += 25
    elif reviews < 50:
        score += 15
    elif reviews < 100:
        score += 8

    # No website = needs web development
    if not place.get("website"):
        score += 20

    # Claimed vs unclaimed (if available)
    if not place.get("business_status") == "OPERATIONAL":
        score += 5

    return min(score, 100)


# ── Google Maps Scraper ───────────────────────────────────────────────────────

class GoogleMapsScraper:
    """
    Scrapes local businesses from Google Maps using the Places API.
    Prioritises businesses with weak online presence.
    """

    def __init__(self):
        self.client = None
        if google_cfg.maps_api_key:
            try:
                import googlemaps
                self.client = googlemaps.Client(key=google_cfg.maps_api_key)
                logger.info("Google Maps client initialised.")
            except ImportError:
                logger.warning("googlemaps not installed. Run: pip install googlemaps")

    def scrape(
        self,
        categories: Optional[List[str]] = None,
        location: str = "New York, USA",
        radius_km: int = 50,
        limit: int = 100,
    ) -> List[Lead]:
        """
        Search Google Maps for businesses in given categories near a location.
        Returns enriched Lead objects with priority scores.
        """
        if not self.client:
            logger.warning("Google Maps client not available — skipping.")
            return []

        categories = categories or google_cfg.maps_categories
        leads: List[Lead] = []
        seen_place_ids: set = set()

        # Geocode the location string to lat/lng
        try:
            geo = self.client.geocode(location)
            if not geo:
                logger.error("Could not geocode location: %s", location)
                return []
            lat_lng = geo[0]["geometry"]["location"]
        except Exception as exc:
            logger.error("Geocode error: %s", exc)
            return []

        for category in categories:
            if len(leads) >= limit:
                break

            logger.info("Searching Google Maps: '%s' near %s", category, location)

            try:
                response = self.client.places_nearby(
                    location=lat_lng,
                    radius=radius_km * 1000,
                    keyword=category,
                    type="establishment",
                )
                results = response.get("results", [])

                # Handle pagination (up to 3 pages)
                for _page in range(3):
                    for place in results:
                        if len(leads) >= limit:
                            break
                        place_id = place.get("place_id", "")
                        if place_id in seen_place_ids:
                            continue
                        seen_place_ids.add(place_id)

                        lead = self._place_to_lead(place, category)
                        if lead:
                            leads.append(lead)
                            upsert_lead(lead)
                            logger.debug(
                                "  ✓ [score=%d] %s",
                                lead.lead_score, lead.company_name
                            )

                    next_token = response.get("next_page_token")
                    if not next_token or len(leads) >= limit:
                        break
                    time.sleep(2)  # Google requires a delay before next_page_token
                    try:
                        response = self.client.places_nearby(
                            page_token=next_token
                        )
                        results = response.get("results", [])
                    except Exception:
                        break

            except Exception as exc:
                logger.warning("Maps search error ('%s'): %s", category, exc)

            human_delay()

        logger.info("Google Maps scrape complete. Collected %d leads.", len(leads))
        return leads

    def _place_to_lead(self, place: dict, category: str) -> Optional[Lead]:
        """Convert a Places API result to a Lead."""
        try:
            name = clean_text(place.get("name", ""))
            place_id = place.get("place_id", "")
            if not name or not place_id:
                return None

            # Attempt to get full place details (phone, website, hours)
            details = {}
            try:
                detail_resp = self.client.place(
                    place_id,
                    fields=["name", "formatted_address", "formatted_phone_number",
                            "website", "rating", "user_ratings_total",
                            "opening_hours", "business_status", "types"]
                )
                details = detail_resp.get("result", {})
            except Exception:
                details = place

            rating = details.get("rating") or place.get("rating")
            review_count = (
                details.get("user_ratings_total")
                or place.get("user_ratings_total", 0)
            )
            website = details.get("website", "")
            phone = details.get("formatted_phone_number", "")
            address = details.get("formatted_address", "")
            hours_raw = details.get("opening_hours", {})
            business_hours = "; ".join(
                hours_raw.get("weekday_text", [])
            ) if hours_raw else ""

            # Parse location from address
            city, state, country = self._parse_address(address)

            lead_id = generate_lead_id("google_maps", place_id)
            score = _score_google_maps_lead(details or place)

            # Infer pain points
            pain_points = []
            services_needed = []

            if not website:
                pain_points.append("No website found")
                services_needed.extend(["Website Design & Development", "SEO"])
            if review_count and review_count < 20:
                pain_points.append(f"Only {review_count} Google reviews")
                services_needed.append("Reputation Management")
            if rating and rating < 4.0:
                pain_points.append(f"Low Google rating: {rating}")
                services_needed.append("Reputation Management")
            if not pain_points:
                services_needed.extend(["Google Ads / PPC", "Social Media Marketing"])

            return Lead(
                id=lead_id,
                company_name=name,
                industry=self._category_to_industry(category),
                company_website=website or None,
                phone=phone or None,
                address=address,
                city=city,
                state=state,
                country=country,
                google_place_id=place_id,
                google_rating=rating,
                google_review_count=review_count,
                business_hours=business_hours,
                lead_score=score,
                pain_points=pain_points,
                services_needed=services_needed,
                source=LeadSource.GOOGLE_MAPS,
                status=LeadStatus.NEW,
                tags=[category],
            )
        except Exception as exc:
            logger.debug("Could not parse place: %s", exc)
            return None

    @staticmethod
    def _parse_address(address: str):
        """Rough city/state/country extraction from a formatted address."""
        parts = [p.strip() for p in address.split(",")]
        country = parts[-1] if len(parts) >= 1 else ""
        state = parts[-2] if len(parts) >= 2 else ""
        city = parts[-3] if len(parts) >= 3 else ""
        return city, state, country

    @staticmethod
    def _category_to_industry(category: str) -> str:
        mapping = {
            "dental": "Healthcare",
            "law": "Legal Services",
            "real estate": "Real Estate",
            "restaurant": "Food & Beverage",
            "fitness": "Health & Wellness",
            "beauty salon": "Beauty & Wellness",
            "plumbing": "Home Services",
            "roofing": "Construction",
            "accounting": "Financial Services",
            "insurance": "Financial Services",
            "car dealer": "Automotive",
            "hotel": "Hospitality",
            "school": "Education",
        }
        for k, v in mapping.items():
            if k in category.lower():
                return v
        return "Local Business"


# ── Google Search / SerpAPI Scraper ──────────────────────────────────────────

class GoogleSearchScraper:
    """
    Uses SerpAPI to find business leads via Google Search.
    Targets buying-intent queries: companies announcing growth,
    hiring marketers, or explicitly seeking marketing help.
    """

    SERPAPI_BASE = "https://serpapi.com/search.json"

    def __init__(self):
        self.api_key = google_cfg.serpapi_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": random_user_agent()})
        proxies = build_proxy_dict()
        if proxies:
            self.session.proxies.update(proxies)

    def scrape(
        self,
        queries: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Lead]:
        """
        Run Google search queries and extract business leads from results.
        """
        if not self.api_key:
            logger.warning("No SERPAPI_KEY set — using fallback HTML scraper.")
            return self._fallback_scrape(queries or google_cfg.search_queries, limit)

        queries = queries or self._build_queries()
        leads: List[Lead] = []
        seen_urls: set = set()

        for query in queries:
            if len(leads) >= limit:
                break

            logger.info("Google search: %s", query)
            results = self._serpapi_search(query)

            for result in results.get("organic_results", []):
                if len(leads) >= limit:
                    break
                url = result.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                lead = self._result_to_lead(result, query)
                if lead:
                    leads.append(lead)
                    upsert_lead(lead)
                    logger.debug("  ✓ %s", lead.company_name or lead.company_website)

            human_delay()

        logger.info("Google Search complete. Collected %d leads.", len(leads))
        return leads

    def _serpapi_search(self, query: str, page: int = 0) -> dict:
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google",
            "num": 10,
            "start": page * 10,
            "hl": "en",
            "gl": "us",
        }
        try:
            resp = self.session.get(self.SERPAPI_BASE, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("SerpAPI error: %s", exc)
            return {}

    def _result_to_lead(self, result: dict, query: str) -> Optional[Lead]:
        """Parse a single Google search result into a Lead."""
        try:
            title = clean_text(result.get("title", ""))
            url = result.get("link", "")
            snippet = clean_text(result.get("snippet", ""))

            if not url or not title:
                return None

            # Skip non-business results
            skip_domains = ["wikipedia.org", "reddit.com", "quora.com",
                            "youtube.com", "amazon.com"]
            if any(d in url for d in skip_domains):
                return None

            lead_id = generate_lead_id("google_search", url)

            # Extract company from title (heuristic: "Company | Page Title")
            company = title.split(" | ")[0].split(" - ")[0].strip()
            email = extract_email(snippet)
            phone = extract_phone(snippet)

            return Lead(
                id=lead_id,
                company_name=company,
                company_website=url,
                company_description=snippet,
                email=email,
                phone=phone,
                lead_score=35,
                services_needed=["SEO", "Google Ads / PPC", "Social Media Marketing"],
                source=LeadSource.GOOGLE_SEARCH,
                status=LeadStatus.NEW,
                tags=["google_search", query[:30]],
            )
        except Exception as exc:
            logger.debug("Could not parse search result: %s", exc)
            return None

    def _fallback_scrape(self, queries: List[str], limit: int) -> List[Lead]:
        """Fallback: use requests + BeautifulSoup to scrape Google."""
        leads: List[Lead] = []
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup4 not installed — skipping fallback.")
            return leads

        for query in queries:
            if len(leads) >= limit:
                break

            url = f"https://www.google.com/search?q={quote_plus(query)}&num=10"
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code == 429:
                    logger.warning("Google rate limit hit. Pausing 60s …")
                    time.sleep(60)
                    continue
                soup = BeautifulSoup(resp.text, "lxml")
                for g in soup.select("div.g"):
                    link = g.select_one("a")
                    snippet_el = g.select_one(".VwiC3b")
                    href = link["href"] if link else ""
                    snippet = snippet_el.get_text() if snippet_el else ""
                    title_el = g.select_one("h3")
                    title = title_el.get_text() if title_el else ""

                    lead = self._result_to_lead(
                        {"title": title, "link": href, "snippet": snippet}, query
                    )
                    if lead:
                        leads.append(lead)
                        upsert_lead(lead)

                human_delay(5, 10)
            except Exception as exc:
                logger.warning("Fallback scrape error: %s", exc)

        return leads

    @staticmethod
    def _build_queries() -> List[str]:
        """
        Build buying-intent search queries targeting businesses that need
        DGenius Solutions' digital marketing services.
        """
        base_industries = [
            "dental clinic", "law firm", "real estate agency",
            "e-commerce store", "restaurant", "fitness studio",
            "beauty salon", "roofing company", "accounting firm",
        ]
        pain_phrases = [
            "how to get more clients",
            "how to rank on Google",
            "hiring digital marketing agency",
            "marketing help for small business",
            "increase website traffic",
            "not getting leads online",
        ]
        queries = []
        for ind in base_industries[:5]:
            for pain in pain_phrases[:3]:
                queries.append(f"{ind} {pain}")
        return queries
