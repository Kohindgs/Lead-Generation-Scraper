"""
Central configuration — loads from .env and exposes typed settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class AgencyConfig:
    name: str = os.getenv("AGENCY_NAME", "DGenius Solutions")
    website: str = os.getenv("AGENCY_WEBSITE", "https://www.dgeniussolutions.com")
    email: str = os.getenv("AGENCY_EMAIL", "hello@dgeniussolutions.com")
    phone: str = os.getenv("AGENCY_PHONE", "")
    sender_name: str = os.getenv("SENDER_NAME", "Business Development")
    sender_title: str = os.getenv("SENDER_TITLE", "Business Development Head")

    # Services offered by DGenius — used for targeting & messaging
    services = [
        "SEO (Search Engine Optimisation)",
        "Google Ads / PPC Management",
        "Social Media Marketing",
        "LinkedIn Lead Generation",
        "Website Design & Development",
        "Content Marketing & Blogging",
        "Email Marketing Automation",
        "Conversion Rate Optimisation",
        "Brand Strategy & Identity",
        "E-commerce Marketing",
        "Video Marketing & YouTube Ads",
        "Reputation Management",
        "Marketing Analytics & Reporting",
        "Influencer Marketing",
        "WhatsApp Marketing Automation",
    ]


class LinkedInConfig:
    email: str = os.getenv("LINKEDIN_EMAIL", "")
    password: str = os.getenv("LINKEDIN_PASSWORD", "")
    session_cookie: str = os.getenv("LINKEDIN_SESSION_COOKIE", "")

    # Search filters (tweak these for each campaign)
    target_industries = [
        "Real Estate", "Legal Services", "Healthcare", "E-commerce",
        "Retail", "Education", "Financial Services", "Hospitality",
        "Construction", "Manufacturing", "SaaS / Technology",
        "Professional Services", "Franchise", "Beauty & Wellness",
    ]

    target_titles = [
        "CEO", "Founder", "Co-Founder", "Managing Director",
        "Marketing Manager", "Marketing Director", "CMO",
        "Head of Marketing", "Digital Marketing Manager",
        "Business Development Manager", "Owner", "Director",
        "VP Marketing", "Growth Manager",
    ]

    target_company_sizes = ["1-10", "11-50", "51-200", "201-500"]
    target_locations = ["United States", "United Kingdom", "Canada",
                        "Australia", "UAE", "India", "Singapore"]
    max_connections_per_day: int = 20   # LinkedIn daily limit safety
    max_messages_per_day: int = 15


class GoogleConfig:
    serpapi_key: str = os.getenv("SERPAPI_KEY", "")
    maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    cse_id: str = os.getenv("GOOGLE_CSE_ID", "")
    api_key: str = os.getenv("GOOGLE_API_KEY", "")

    # Dork queries — businesses that need digital marketing
    search_queries = [
        'site:linkedin.com/in "need digital marketing" "hiring"',
        '"digital marketing" "looking for agency" site:reddit.com',
        '"we need more leads" OR "struggling with SEO" site:linkedin.com',
        '"marketing budget" "2024" OR "2025" site:linkedin.com',
        'intitle:"marketing director" "open to work" site:linkedin.com',
    ]

    # Google Maps business categories that need marketing
    maps_categories = [
        "dental clinic", "law firm", "real estate agency",
        "restaurant", "fitness center", "beauty salon",
        "plumbing service", "roofing contractor",
        "accounting firm", "insurance agency",
        "car dealership", "hotel", "school",
    ]

    maps_search_radius_km: int = 50
    max_results_per_query: int = 100


class ScraperConfig:
    delay_min: float = float(os.getenv("REQUEST_DELAY_MIN", 2))
    delay_max: float = float(os.getenv("REQUEST_DELAY_MAX", 6))
    max_leads_per_run: int = int(os.getenv("MAX_LEADS_PER_RUN", 200))
    headless: bool = os.getenv("HEADLESS_BROWSER", "true").lower() == "true"

    use_proxy: bool = os.getenv("USE_PROXY", "false").lower() == "true"
    proxy_host: str = os.getenv("PROXY_HOST", "")
    proxy_port: str = os.getenv("PROXY_PORT", "")
    proxy_user: str = os.getenv("PROXY_USER", "")
    proxy_pass: str = os.getenv("PROXY_PASS", "")


class DatabaseConfig:
    path: str = str(BASE_DIR / os.getenv("DB_PATH", "data/leads.db"))


class AIConfig:
    anthropic_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = "claude-sonnet-4-6"   # latest Claude Sonnet


class EnrichmentConfig:
    hunter_key: str = os.getenv("HUNTER_API_KEY", "")
    apollo_key: str = os.getenv("APOLLO_API_KEY", "")


class MetaConfig:
    """Meta Graph API + campaign settings for the AI Content Reply System."""

    # Meta App credentials
    page_access_token: str = os.getenv("META_PAGE_ACCESS_TOKEN", "")
    page_id: str = os.getenv("META_PAGE_ID", "")
    instagram_account_id: str = os.getenv("META_IG_ACCOUNT_ID", "")

    # Webhook (receives Google Form submissions)
    webhook_secret: str = os.getenv("META_WEBHOOK_SECRET", "")
    webhook_verify_token: str = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "")

    # Google Form URL (use PSID_PLACEHOLDER for per-user pre-filled links)
    google_form_url: str = os.getenv("META_GOOGLE_FORM_URL", "")

    # Gmail / Google Workspace SMTP for sending brand reports
    smtp_host: str = os.getenv("META_SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("META_SMTP_PORT", 587))
    smtp_user: str = os.getenv("META_SMTP_USER", os.getenv("SMTP_USER", ""))
    smtp_pass: str = os.getenv("META_SMTP_PASS", os.getenv("SMTP_PASS", ""))

    # Google Sheets (lead tracking)
    google_sheet_id: str = os.getenv("GOOGLE_SHEET_ID", "")
    google_service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    # Branding — logo URL used in HTML reports and DM messages
    # Use the white-background logo for emails/reports
    logo_url: str = os.getenv(
        "META_LOGO_URL",
        "https://www.dgeniussolutions.com/wp-content/uploads/dgs-logo-white-bg.png",
    )

    # Polling behaviour
    scan_interval_minutes: int = int(os.getenv("META_SCAN_INTERVAL_MINUTES", 15))
    max_posts_per_scan: int = int(os.getenv("META_MAX_POSTS_PER_SCAN", 25))


# Singleton-style access
agency = AgencyConfig()
linkedin_cfg = LinkedInConfig()
google_cfg = GoogleConfig()
scraper_cfg = ScraperConfig()
db_cfg = DatabaseConfig()
ai_cfg = AIConfig()
enrich_cfg = EnrichmentConfig()
meta_cfg = MetaConfig()
