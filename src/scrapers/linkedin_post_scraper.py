"""
LinkedIn Service-Requirement Post Scraper
==========================================
Automatically finds LinkedIn posts where people are ACTIVELY ASKING for
digital marketing / web / SEO / social media services — then extracts
the poster as a hot lead and generates a contextual DM reply.

How it works:
  1. Searches LinkedIn posts using keyword phrases like:
       "looking for a web designer", "need SEO help",
       "anyone recommend a digital marketing agency", etc.
  2. Filters posts by recency (< 48 h), relevance, and poster seniority
  3. Fetches poster's profile (title, company, location)
  4. Scores opportunity 0–100 based on urgency, seniority, services fit
  5. Saves qualified posts to DB and generates a personalised DM
  6. Optionally sends the DM automatically (controlled by config)

Run standalone:
  python main.py post-scraper --max-posts 50
  python main.py post-scraper --max-posts 50 --send-dms
  python main.py post-scraper --dry-run

Run on auto-schedule:
  python main.py scheduler start
"""
from __future__ import annotations

import hashlib
import json
import time
import random
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from src.config import linkedin_cfg, agency
from src.models import Lead, LeadSource, LeadStatus, ServiceRequestPost
from src.utils.helpers import clean_text, generate_lead_id, get_logger, human_delay
from src.utils.database import upsert_lead, upsert_service_post, get_seen_post_ids

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE REQUIREMENT KEYWORD GROUPS
#
# Each group maps to one or more DGenius services.
# We search ALL of these automatically.
# ─────────────────────────────────────────────────────────────────────────────

SERVICE_KEYWORD_GROUPS: dict[str, List[str]] = {
    "Web Design & Development": [
        "looking for a web designer",
        "need a website built",
        "need a web developer",
        "anyone recommend a good website designer",
        "need someone to build my website",
        "looking to redesign my website",
        "need a new website",
        "website developer needed",
        "looking for web developer",
        "need help with my website",
    ],
    "SEO": [
        "looking for SEO help",
        "need help with SEO",
        "anyone recommend SEO agency",
        "SEO expert needed",
        "want to rank on Google",
        "need to improve Google ranking",
        "looking for SEO specialist",
        "anyone done SEO for their business",
        "need organic traffic",
        "not showing on Google",
    ],
    "Social Media Marketing": [
        "need a social media manager",
        "looking for social media help",
        "anyone recommend social media agency",
        "need someone to manage my Instagram",
        "need someone to run my Facebook",
        "looking for content creator",
        "need social media content",
        "Instagram growth help",
        "Facebook ads help needed",
        "social media strategy needed",
    ],
    "Google Ads / PPC": [
        "need help with Google Ads",
        "looking for Google Ads expert",
        "anyone run PPC campaigns",
        "need someone to manage my ads",
        "Facebook ads not working",
        "need advertising help",
        "looking for paid ads specialist",
        "PPC management needed",
        "Google Ads agency needed",
        "need to run ads",
    ],
    "Digital Marketing (General)": [
        "looking for digital marketing agency",
        "need a marketing agency",
        "anyone recommend a good marketing company",
        "need digital marketing help",
        "marketing help for small business",
        "need to grow my business online",
        "online marketing needed",
        "need a marketing strategy",
        "digital marketing for my business",
        "need online visibility",
    ],
    "Reputation Management": [
        "need more Google reviews",
        "how to get more reviews",
        "bad reviews hurting my business",
        "reputation management needed",
        "need help with online reputation",
        "customers leaving bad reviews",
        "Google rating low",
    ],
    "Video Marketing": [
        "need a videographer",
        "looking for video editor",
        "need promo video",
        "anyone recommend video marketing",
        "need YouTube content",
        "need video content for business",
        "looking for video production",
    ],
    "Branding & Logo": [
        "need a logo designed",
        "looking for a graphic designer",
        "need branding help",
        "brand identity needed",
        "need a brand designer",
        "rebranding my business",
        "logo designer needed",
    ],
}

# All keywords flattened for fast scanning
ALL_KEYWORDS = [kw for kws in SERVICE_KEYWORD_GROUPS.values() for kw in kws]

# High-urgency signal words (boost score)
URGENCY_HIGH = [
    "asap", "urgent", "immediately", "today", "this week",
    "ready to pay", "ready to hire", "budget ready", "start now",
]
URGENCY_MEDIUM = [
    "soon", "looking to", "planning to", "thinking about",
    "next month", "want to",
]

# Seniority boost keywords in poster title
SENIORITY_BOOST_TITLES = [
    "ceo", "founder", "owner", "director", "head of", "vp",
    "managing director", "md", "partner", "co-founder",
]

# Disqualifiers — skip posts with these (employees looking for jobs, etc.)
DISQUALIFIERS = [
    "job seeker", "open to work", "looking for a job",
    "looking for employment", "seeking a position",
    "resume", "cv attached", "hire me",
    "internship", "graduate",
]


def _keyword_matches(text: str) -> Tuple[List[str], List[str]]:
    """
    Return (matched_keywords, matched_services) for a post's text.
    """
    text_lower = text.lower()
    matched_kws: List[str] = []
    matched_services: List[str] = []

    for service, kws in SERVICE_KEYWORD_GROUPS.items():
        for kw in kws:
            if kw in text_lower and kw not in matched_kws:
                matched_kws.append(kw)
                if service not in matched_services:
                    matched_services.append(service)

    return matched_kws, matched_services


def _is_disqualified(text: str) -> bool:
    text_lower = text.lower()
    return any(d in text_lower for d in DISQUALIFIERS)


def _score_urgency(text: str) -> Tuple[str, int]:
    """Return (urgency_label, score_boost)."""
    text_lower = text.lower()
    if any(u in text_lower for u in URGENCY_HIGH):
        return "high", 25
    if any(u in text_lower for u in URGENCY_MEDIUM):
        return "medium", 10
    return "low", 0


def _score_post(
    post_text: str,
    poster_title: str,
    matched_keywords: List[str],
    post_age_hours: float,
) -> int:
    """Score opportunity 0–100."""
    score = 0

    # Keyword match depth
    score += min(len(matched_keywords) * 8, 30)

    # Recency — posts < 6 hours are gold
    if post_age_hours <= 6:
        score += 25
    elif post_age_hours <= 24:
        score += 15
    elif post_age_hours <= 48:
        score += 5

    # Poster seniority
    title_lower = poster_title.lower()
    if any(t in title_lower for t in SENIORITY_BOOST_TITLES):
        score += 20

    # Urgency
    _, urgency_boost = _score_urgency(post_text)
    score += urgency_boost

    # Budget mention
    if re.search(r'\$\d+|budget|spend|invest|per month', post_text, re.I):
        score += 10

    return min(score, 100)


def _parse_post_age(time_str: str) -> float:
    """
    Parse LinkedIn's relative time string (e.g. '3h', '2d', '5m')
    into hours as float. Returns 999 if unknown.
    """
    if not time_str:
        return 999.0
    time_str = time_str.strip().lower()
    m = re.match(r"(\d+)\s*([smhdw])", time_str)
    if not m:
        return 999.0
    val, unit = int(m.group(1)), m.group(2)
    return {"s": val / 3600, "m": val / 60, "h": val,
            "d": val * 24, "w": val * 168}.get(unit, 999.0)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCRAPER CLASS
# ─────────────────────────────────────────────────────────────────────────────

class LinkedInPostScraper:
    """
    Automated scraper that:
      1. Searches LinkedIn posts for service requirements
      2. Qualifies and scores each opportunity
      3. Extracts poster as Lead
      4. Generates personalised DM
      5. Optionally sends DM automatically
    """

    MAX_POST_AGE_HOURS = 48    # ignore posts older than this
    MIN_SCORE_TO_QUALIFY = 45  # minimum opportunity score to save

    def __init__(self):
        self.api = None
        self._authenticated = False
        self._seen_post_ids: set = set()

    def authenticate(self) -> bool:
        try:
            from linkedin_api import Linkedin
            logger.info("Authenticating with LinkedIn for post scraping …")
            self.api = Linkedin(linkedin_cfg.email, linkedin_cfg.password)
            self._authenticated = True
            logger.info("LinkedIn authentication OK.")
            return True
        except ImportError:
            logger.error("linkedin-api not installed. Run: pip install linkedin-api")
            return False
        except Exception as exc:
            logger.error("LinkedIn auth failed: %s", exc)
            return False

    def run(
        self,
        max_posts: int = 100,
        send_dms: bool = False,
        dry_run: bool = False,
        min_score: int = 45,
        max_post_age_hours: float = 48.0,
        services_filter: Optional[List[str]] = None,
    ) -> List[ServiceRequestPost]:
        """
        Full automated run:
          - Search posts across all keyword groups
          - Score and qualify
          - Save to DB
          - Generate DMs
          - Optionally send DMs

        Args:
            max_posts: Total posts to collect across all searches
            send_dms: If True, send DMs via LinkedIn API
            dry_run: Preview only, no saving or sending
            min_score: Minimum opportunity score (0-100)
            max_post_age_hours: Ignore posts older than this many hours
            services_filter: Only search specific service categories (or None for all)
        """
        if not self._authenticated and not self.authenticate():
            logger.error("Cannot run — LinkedIn not authenticated.")
            return []

        # Load already-processed post IDs to avoid duplicates
        self._seen_post_ids = get_seen_post_ids()
        logger.info("Loaded %d already-seen post IDs.", len(self._seen_post_ids))

        results: List[ServiceRequestPost] = []
        keyword_groups = SERVICE_KEYWORD_GROUPS

        if services_filter:
            keyword_groups = {
                k: v for k, v in keyword_groups.items()
                if k in services_filter
            }

        posts_per_service = max(5, max_posts // max(len(keyword_groups), 1))

        for service, keywords in keyword_groups.items():
            if len(results) >= max_posts:
                break

            logger.info("Searching posts for service: %s", service)

            # Rotate through keywords for this service
            random.shuffle(keywords)
            for keyword in keywords[:4]:  # up to 4 keywords per service
                if len(results) >= max_posts:
                    break

                batch = self._search_posts_for_keyword(
                    keyword=keyword,
                    service=service,
                    limit=posts_per_service,
                    max_age_hours=max_post_age_hours,
                    min_score=min_score,
                    dry_run=dry_run,
                )
                results.extend(batch)
                human_delay(3, 8)  # polite pause between searches

        # Generate DMs for all qualified posts
        if results:
            self._generate_dms(results)

        # Optionally send DMs
        if send_dms and not dry_run:
            self._send_dms(results)
        elif dry_run:
            self._preview_results(results)

        logger.info(
            "Post scraping complete. Found %d qualified service-request posts.",
            len(results)
        )
        return results

    def _search_posts_for_keyword(
        self,
        keyword: str,
        service: str,
        limit: int,
        max_age_hours: float,
        min_score: int,
        dry_run: bool,
    ) -> List[ServiceRequestPost]:
        """Search LinkedIn for posts matching a keyword, return qualified posts."""
        qualified: List[ServiceRequestPost] = []

        logger.debug("  Keyword: '%s'", keyword)

        try:
            # linkedin-api search with CONTENT filter (posts, articles)
            raw_results = self.api.search(
                params={
                    "keywords": keyword,
                    "filters": json.dumps({"resultType": "CONTENT"}),
                },
                limit=limit * 3,  # fetch extra as many won't qualify
            )
        except Exception as exc:
            logger.warning("  Search error for '%s': %s", keyword, exc)
            return []

        for raw in raw_results:
            post = self._parse_post_result(raw, service)
            if not post:
                continue

            # Skip already seen
            if post.id in self._seen_post_ids:
                continue

            # Skip if too old
            if post.post_age_hours and post.post_age_hours > max_age_hours:
                continue

            # Skip disqualified
            if _is_disqualified(post.post_text):
                continue

            # Skip if score too low
            if post.opportunity_score < min_score:
                logger.debug("  ✗ Low score (%d): %s", post.opportunity_score,
                             post.poster_name[:40])
                continue

            post.is_qualified = True
            self._seen_post_ids.add(post.id)

            logger.info(
                "  ✓ [score:%d/%s] %s (%s) — %s",
                post.opportunity_score, post.urgency,
                post.poster_name, post.poster_title[:30],
                keyword
            )

            if not dry_run:
                # Convert poster to Lead and save
                lead = self._post_to_lead(post)
                if lead:
                    upsert_lead(lead)
                    post.lead_id = lead.id
                upsert_service_post(post)

            qualified.append(post)

            human_delay(0.5, 2)

        return qualified

    def _parse_post_result(self, raw: dict, service: str) -> Optional[ServiceRequestPost]:
        """Parse a raw LinkedIn search result into a ServiceRequestPost."""
        try:
            # Extract post text (various field locations depending on API version)
            post_text = (
                raw.get("commentary", {}).get("text", "")
                or raw.get("text", {}).get("text", "")
                or raw.get("description", {}).get("text", "")
                or raw.get("headline", {}).get("text", "")
                or ""
            )
            post_text = clean_text(post_text)

            if len(post_text) < 20:  # too short to be meaningful
                return None

            # Check keyword match
            matched_kws, matched_services = _keyword_matches(post_text)
            if not matched_kws:
                return None

            # Extract post ID/URN
            urn = (
                raw.get("entityUrn", "")
                or raw.get("urn", "")
                or raw.get("id", "")
            )
            if not urn:
                # generate deterministic ID from text
                urn = "local:" + hashlib.md5(post_text[:100].encode()).hexdigest()

            post_id = urn.replace("urn:li:activity:", "").replace("urn:li:", "")

            # Extract actor (poster)
            actor = (
                raw.get("actor", {})
                or raw.get("author", {})
                or raw.get("owner", {})
                or {}
            )
            actor_name_obj = (
                actor.get("name", {})
                or actor.get("fullName", {})
                or {}
            )
            poster_name = (
                actor_name_obj.get("text", "")
                or actor.get("name", "")
                or raw.get("authorName", "")
                or ""
            )
            poster_name = clean_text(poster_name)

            actor_title_obj = actor.get("description", {}) or {}
            poster_title = clean_text(
                actor_title_obj.get("text", "")
                or actor.get("headline", "")
                or actor.get("title", "")
                or ""
            )

            poster_urn = actor.get("urn", "") or actor.get("entityUrn", "")
            public_id = ""
            if "fsd_profile:" in poster_urn:
                public_id = poster_urn.split("fsd_profile:")[-1]
            elif "miniProfile:" in poster_urn:
                public_id = poster_urn.split("miniProfile:")[-1]

            poster_linkedin_url = (
                f"https://www.linkedin.com/in/{public_id}" if public_id else None
            )

            # Age
            time_str = raw.get("createdAt", "") or raw.get("time", "")
            post_age_hours = _parse_post_age(str(time_str)) if time_str else None

            # Engagement
            social = raw.get("socialDetail", {}) or {}
            reaction_count = (
                social.get("totalSocialActivityCounts", {})
                .get("numLikes", 0)
            )
            comment_count = (
                social.get("totalSocialActivityCounts", {})
                .get("numComments", 0)
            )
            engagement = (reaction_count or 0) + (comment_count or 0)

            urgency, _ = _score_urgency(post_text)
            score = _score_post(
                post_text, poster_title, matched_kws,
                post_age_hours or 999.0
            )

            # Budget mentioned?
            budget_mentioned = bool(
                re.search(r'\$\d+|budget|spend|invest|per month', post_text, re.I)
            )

            # Location in post
            loc_match = re.search(
                r'\b(london|manchester|dubai|new york|los angeles|sydney|'
                r'toronto|singapore|johannesburg|cape town|nairobi|lagos)\b',
                post_text, re.I
            )
            location_mentioned = loc_match.group(0).title() if loc_match else ""

            # Split poster name
            parts = poster_name.split(" ", 1)
            first = parts[0] if parts else ""

            return ServiceRequestPost(
                id=post_id,
                post_text=post_text,
                post_url=f"https://www.linkedin.com/feed/update/{urn}/",
                poster_urn=poster_urn,
                poster_name=poster_name,
                poster_first_name=first,
                poster_title=poster_title,
                poster_company="",  # fetched separately if needed
                poster_linkedin_url=poster_linkedin_url,
                services_requested=matched_services or [service],
                keywords_matched=matched_kws,
                urgency=urgency,
                budget_mentioned=budget_mentioned,
                location_mentioned=location_mentioned,
                opportunity_score=score,
                post_age_hours=post_age_hours,
                engagement=engagement,
            )

        except Exception as exc:
            logger.debug("Failed to parse post result: %s", exc)
            return None

    def _post_to_lead(self, post: ServiceRequestPost) -> Optional[Lead]:
        """Convert a service post's poster into a Lead record."""
        if not post.poster_name:
            return None

        try:
            # Try to fetch full profile for email / company
            profile_data = {}
            if post.poster_linkedin_url:
                public_id = post.poster_linkedin_url.rstrip("/").split("/")[-1]
                try:
                    profile_data = self.api.get_profile(public_id) or {}
                    human_delay(1, 3)
                except Exception:
                    pass

            company = (
                post.poster_company
                or (profile_data.get("experience") or [{}])[0].get("companyName", "")
                or ""
            )
            industry = profile_data.get("industryName", "")
            city = profile_data.get("geoLocationName", "")
            country = profile_data.get("geoCountryName", "")

            emails = profile_data.get("emailAddresses", [])
            email = emails[0].get("emailAddress") if emails else None

            phones = profile_data.get("phoneNumbers", [])
            phone = phones[0].get("number") if phones else None

            first = post.poster_first_name
            last = post.poster_name.split(" ", 1)[1] if " " in post.poster_name else ""

            lead_id = generate_lead_id("linkedin_post", post.id)

            from src.scrapers.linkedin_scraper import infer_seniority
            return Lead(
                id=lead_id,
                first_name=first,
                last_name=last,
                full_name=post.poster_name,
                title=post.poster_title,
                seniority=infer_seniority(post.poster_title),
                company_name=clean_text(company),
                industry=industry,
                email=email,
                phone=phone,
                city=city or post.location_mentioned,
                country=country,
                linkedin_url=post.poster_linkedin_url,
                services_needed=post.services_requested,
                pain_points=[f"Actively seeking: {s}" for s in post.services_requested],
                buying_signals=[f"Posted: '{kw}'" for kw in post.keywords_matched[:3]],
                lead_score=post.opportunity_score,
                icp_match=post.opportunity_score >= 60,
                source=LeadSource.LINKEDIN_POST,
                status=LeadStatus.NEW,
                tags=["service-request", "hot-lead"] + post.services_requested[:2],
                notes=(
                    f"Found via LinkedIn post search.\n"
                    f"Post: {post.post_text[:300]}\n"
                    f"Urgency: {post.urgency} | Score: {post.opportunity_score}"
                ),
            )
        except Exception as exc:
            logger.debug("Could not convert post to lead: %s", exc)
            return None

    def _generate_dms(self, posts: List[ServiceRequestPost]):
        """Generate personalised DMs for all qualified posts."""
        from src.outreach.post_reply_generator import PostReplyGenerator
        generator = PostReplyGenerator()
        for post in posts:
            if not post.dm_message:
                post.dm_message = generator.generate(post)
                logger.debug("  DM generated for %s", post.poster_name)

    def _send_dms(self, posts: List[ServiceRequestPost]):
        """Send DMs via LinkedIn API to poster of each qualified post."""
        sent = 0
        failed = 0
        daily_limit = linkedin_cfg.max_dms_per_day if hasattr(linkedin_cfg, 'max_dms_per_day') else 20

        for post in posts:
            if sent >= daily_limit:
                logger.warning("Daily DM limit (%d) reached. Stopping.", daily_limit)
                break
            if not post.poster_urn or not post.dm_message:
                continue
            if post.dm_sent:
                continue

            try:
                self.api.send_message(
                    message_body=post.dm_message,
                    recipients=[post.poster_urn],
                )
                post.dm_sent = True
                post.dm_sent_at = datetime.utcnow()
                upsert_service_post(post)
                logger.info("  ✓ DM sent to %s", post.poster_name)
                sent += 1

                # Human-like delay 30–90s between DMs (LinkedIn rate limit)
                delay = random.uniform(30, 90)
                logger.debug("  Waiting %.0fs before next DM …", delay)
                time.sleep(delay)

            except Exception as exc:
                logger.warning("  ✗ DM failed for %s: %s", post.poster_name, exc)
                failed += 1

        logger.info("DMs — Sent: %d | Failed: %d", sent, failed)

    def _preview_results(self, posts: List[ServiceRequestPost]):
        """Print dry-run preview of found posts and DMs."""
        print(f"\n{'='*65}")
        print(f"  DRY RUN — Found {len(posts)} qualified service-request posts")
        print(f"{'='*65}")
        for i, post in enumerate(posts[:10], 1):
            print(f"\n  [{i}] {post.poster_name} ({post.poster_title})")
            print(f"      Score: {post.opportunity_score}/100 | Urgency: {post.urgency}")
            print(f"      Services: {', '.join(post.services_requested)}")
            print(f"      Post: {post.post_text[:120]}…")
            if post.dm_message:
                print(f"      DM preview: {post.dm_message[:120]}…")
        if len(posts) > 10:
            print(f"\n  … and {len(posts) - 10} more")
        print(f"\n{'='*65}")
