"""
LeadsGorilla Importer
======================
Imports leads exported from LeadsGorilla (CSV or Excel) into our system.

LeadsGorilla exports local business leads from Google Maps & Facebook with:
  - Business name, address, phone, website
  - Google rating, review count
  - SEO score / website audit flags
  - Email (if available)
  - Business category / niche

Workflow:
  1. Export leads from LeadsGorilla → save as CSV or Excel
  2. Run: python main.py leadsgorilla --file path/to/export.csv
  3. System enriches, scores, and generates AI outreach
  4. Send via LeadsGorilla emailer OR our built-in SMTP emailer
"""
import csv
import json
from pathlib import Path
from typing import List, Optional

from src.models import Lead, LeadSource, LeadStatus
from src.utils.database import upsert_lead
from src.utils.helpers import clean_text, generate_lead_id, get_logger

logger = get_logger(__name__)


# ── LeadsGorilla CSV column name mappings ─────────────────────────────────────
# LeadsGorilla may use slightly different column names depending on version.
# We handle the most common variants below.

COLUMN_MAP = {
    # Business identity
    "business_name":    ["Business Name", "Name", "Company", "business name", "name"],
    "category":         ["Category", "Niche", "Type", "Business Type", "category"],
    "website":          ["Website", "Website URL", "URL", "website"],
    "email":            ["Email", "Email Address", "Contact Email", "email"],
    "phone":            ["Phone", "Phone Number", "Tel", "Telephone", "phone"],

    # Location
    "address":          ["Address", "Full Address", "Street Address", "address"],
    "city":             ["City", "city"],
    "state":            ["State", "Province", "state"],
    "country":          ["Country", "country"],
    "zip":              ["Zip", "Zip Code", "Postal Code", "zip"],

    # Google signals
    "google_rating":    ["Rating", "Google Rating", "Stars", "rating"],
    "review_count":     ["Reviews", "Review Count", "Total Reviews", "reviews", "review count"],
    "place_id":         ["Place ID", "Google Place ID", "place_id"],

    # LeadsGorilla audit scores
    "seo_score":        ["SEO Score", "SEO", "seo score"],
    "has_website":      ["Has Website", "Website Status", "has website"],
    "claimed":          ["Claimed", "Google Claimed", "claimed"],
    "mobile_friendly":  ["Mobile Friendly", "Mobile", "mobile friendly"],
    "has_video":        ["Has Video", "Video", "has video"],
    "social_media":     ["Social Media", "Social", "social media"],
    "on_first_page":    ["On First Page", "First Page", "on first page"],
    "facebook_page":    ["Facebook", "Facebook Page", "facebook"],

    # Contact person (if LeadsGorilla found one)
    "contact_name":     ["Contact Name", "Owner Name", "contact name"],
    "contact_title":    ["Contact Title", "Title", "contact title"],
}


def _find_column(headers: List[str], candidates: List[str]) -> Optional[str]:
    """Find the first matching column from a list of candidate names."""
    headers_lower = {h.lower(): h for h in headers}
    for candidate in candidates:
        if candidate.lower() in headers_lower:
            return headers_lower[candidate.lower()]
    return None


def _build_column_lookup(headers: List[str]) -> dict:
    """Build a {field_name: actual_column_header} mapping."""
    lookup = {}
    for field, candidates in COLUMN_MAP.items():
        col = _find_column(headers, candidates)
        if col:
            lookup[field] = col
    return lookup


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in ["yes", "true", "1", "✓", "✔"]


def _parse_float(value: str) -> Optional[float]:
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_int(value: str) -> Optional[int]:
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _infer_pain_points(row_data: dict) -> List[str]:
    """Infer pain points from LeadsGorilla audit fields."""
    pain_points = []

    rating = _parse_float(row_data.get("google_rating", ""))
    reviews = _parse_int(row_data.get("review_count", ""))
    seo_score = _parse_int(row_data.get("seo_score", ""))

    if not _parse_bool(row_data.get("has_website", "")):
        pain_points.append("No website found")
    if rating and rating < 3.5:
        pain_points.append(f"Low Google rating: {rating}/5")
    elif rating and rating < 4.0:
        pain_points.append(f"Below-average Google rating: {rating}/5")
    if reviews is not None and reviews < 10:
        pain_points.append(f"Very few Google reviews: only {reviews}")
    elif reviews is not None and reviews < 30:
        pain_points.append(f"Low Google review count: {reviews}")
    if seo_score is not None and seo_score < 40:
        pain_points.append(f"Poor SEO score: {seo_score}/100")
    if not _parse_bool(row_data.get("mobile_friendly", "")):
        pain_points.append("Website not mobile-friendly")
    if not _parse_bool(row_data.get("claimed", "")):
        pain_points.append("Google Business Profile not claimed")
    if not _parse_bool(row_data.get("has_video", "")):
        pain_points.append("No video content / YouTube presence")
    if not _parse_bool(row_data.get("social_media", "")):
        pain_points.append("No social media presence detected")
    if not _parse_bool(row_data.get("on_first_page", "")):
        pain_points.append("Not appearing on Google's first page")

    return pain_points


def _infer_services_needed(pain_points: List[str], row_data: dict) -> List[str]:
    """Map pain points to DGenius services."""
    services = []
    pain_str = " ".join(pain_points).lower()

    if "no website" in pain_str:
        services.append("Website Design & Development")
    if "seo" in pain_str or "first page" in pain_str:
        services.append("SEO (Search Engine Optimisation)")
    if "rating" in pain_str or "review" in pain_str or "claimed" not in pain_str:
        services.append("Reputation Management")
    if "social media" in pain_str:
        services.append("Social Media Marketing")
    if "mobile" in pain_str:
        services.append("Website Design & Development")
    if "video" in pain_str:
        services.append("Video Marketing & YouTube Ads")
    if not services:
        # Default services for any local business
        services.extend(["Google Ads / PPC Management", "Local SEO"])

    return list(dict.fromkeys(services))  # deduplicate while preserving order


def _row_to_lead(row: dict, col_lookup: dict) -> Optional[Lead]:
    """Convert a LeadsGorilla CSV row to a Lead object."""
    # Extract raw values using column lookup
    def get(field: str) -> str:
        col = col_lookup.get(field)
        return clean_text(row.get(col, "") or "") if col else ""

    business_name = get("business_name")
    if not business_name:
        return None  # skip empty rows

    category = get("category")
    website = get("website") or None
    email = get("email") or None
    phone = get("phone") or None
    address = get("address")
    city = get("city")
    state = get("state")
    country = get("country")
    place_id = get("place_id") or None
    contact_name = get("contact_name")
    contact_title = get("contact_title")

    google_rating = _parse_float(get("google_rating"))
    review_count = _parse_int(get("review_count"))

    # Build raw data dict for pain point inference
    raw_flags = {k: get(k) for k in [
        "has_website", "claimed", "mobile_friendly", "has_video",
        "social_media", "on_first_page", "seo_score",
        "google_rating", "review_count",
    ]}

    pain_points = _infer_pain_points(raw_flags)
    services_needed = _infer_services_needed(pain_points, raw_flags)

    # Parse contact name
    first_name, last_name = "", ""
    if contact_name:
        parts = contact_name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

    lead_id = generate_lead_id("leadsgorilla", place_id or business_name)

    return Lead(
        id=lead_id,
        first_name=first_name,
        last_name=last_name,
        full_name=contact_name or "",
        title=contact_title or "Business Owner",
        seniority="owner",
        company_name=business_name,
        company_website=website,
        industry=_category_to_industry(category),
        email=email,
        email_verified=bool(email),
        phone=phone,
        address=address,
        city=city,
        state=state,
        country=country or "United States",
        google_place_id=place_id,
        google_rating=google_rating,
        google_review_count=review_count,
        pain_points=pain_points,
        services_needed=services_needed,
        source=LeadSource.GOOGLE_MAPS,   # LeadsGorilla pulls from Google Maps
        status=LeadStatus.NEW,
        tags=["leadsgorilla", category] if category else ["leadsgorilla"],
        notes=f"Imported from LeadsGorilla. Category: {category}",
    )


def _category_to_industry(category: str) -> str:
    """Map LeadsGorilla business category to our industry taxonomy."""
    if not category:
        return "Local Business"
    c = category.lower()
    mapping = {
        ("dental", "dentist", "orthodont"): "Healthcare",
        ("doctor", "medical", "clinic", "health", "hospital", "pharmacy"): "Healthcare",
        ("law", "attorney", "legal", "solicitor"): "Legal Services",
        ("real estate", "realtor", "property", "mortgage"): "Real Estate",
        ("restaurant", "cafe", "food", "pizza", "bakery", "catering"): "Food & Beverage",
        ("gym", "fitness", "yoga", "personal trainer", "crossfit"): "Health & Wellness",
        ("salon", "beauty", "spa", "nail", "barber", "hair"): "Beauty & Wellness",
        ("plumb", "hvac", "electric", "roofing", "contractor", "construction"): "Construction",
        ("account", "tax", "bookkeeping", "cpa", "financial"): "Financial Services",
        ("insurance",): "Financial Services",
        ("school", "tutor", "education", "academy", "college"): "Education",
        ("hotel", "motel", "b&b", "airbnb", "hospitality"): "Hospitality",
        ("car", "auto", "vehicle", "mechanic", "dealership"): "Automotive",
        ("retail", "shop", "store", "boutique"): "Retail",
        ("ecommerce", "e-commerce", "online store"): "E-commerce",
    }
    for keywords, industry in mapping.items():
        if any(k in c for k in keywords):
            return industry
    return "Local Business"


# ── Public import functions ───────────────────────────────────────────────────

def import_from_csv(file_path: str) -> List[Lead]:
    """
    Import leads from a LeadsGorilla CSV export file.
    Returns list of Lead objects saved to the database.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error("File not found: %s", file_path)
        return []

    leads: List[Lead] = []
    errors = 0

    with open(path, "r", encoding="utf-8-sig") as f:  # utf-8-sig handles BOM
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        col_lookup = _build_column_lookup(list(headers))

        logger.info("LeadsGorilla CSV columns detected: %s", list(col_lookup.keys()))

        for i, row in enumerate(reader, 1):
            lead = _row_to_lead(row, col_lookup)
            if lead:
                is_new = upsert_lead(lead)
                leads.append(lead)
                status = "NEW" if is_new else "updated"
                logger.debug("  [%d] %s — %s (%s)", i, lead.company_name, status,
                             f"score will be set after enrichment")
            else:
                errors += 1

    logger.info(
        "Imported %d leads from LeadsGorilla CSV (%d rows skipped).",
        len(leads), errors
    )
    return leads


def import_from_excel(file_path: str) -> List[Lead]:
    """
    Import leads from a LeadsGorilla Excel export file.
    Returns list of Lead objects saved to the database.
    """
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas not installed. Run: pip install pandas openpyxl")
        return []

    path = Path(file_path)
    if not path.exists():
        logger.error("File not found: %s", file_path)
        return []

    leads: List[Lead] = []
    errors = 0

    try:
        # Read all sheets and use the first one with data
        xl = pd.ExcelFile(str(path))
        df = None
        for sheet in xl.sheet_names:
            candidate = xl.parse(sheet)
            if not candidate.empty:
                df = candidate
                logger.info("Reading sheet: '%s' (%d rows)", sheet, len(candidate))
                break

        if df is None or df.empty:
            logger.error("No data found in Excel file: %s", file_path)
            return []

        # Convert NaN to empty string
        df = df.fillna("")
        headers = list(df.columns)
        col_lookup = _build_column_lookup(headers)

        logger.info("LeadsGorilla Excel columns detected: %s", list(col_lookup.keys()))

        for i, row in df.iterrows():
            row_dict = {col: str(row[col]) for col in df.columns}
            lead = _row_to_lead(row_dict, col_lookup)
            if lead:
                is_new = upsert_lead(lead)
                leads.append(lead)
                logger.debug("  [%d] %s (%s)", i + 1, lead.company_name,
                             "new" if is_new else "updated")
            else:
                errors += 1

    except Exception as exc:
        logger.error("Excel import error: %s", exc)
        return []

    logger.info(
        "Imported %d leads from LeadsGorilla Excel (%d rows skipped).",
        len(leads), errors
    )
    return leads


def import_leads(file_path: str) -> List[Lead]:
    """
    Auto-detect CSV or Excel and import accordingly.
    Main function to call from CLI or orchestrator.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    logger.info("Importing LeadsGorilla export: %s", path.name)

    if suffix == ".csv":
        return import_from_csv(file_path)
    elif suffix in [".xlsx", ".xls"]:
        return import_from_excel(file_path)
    else:
        logger.error("Unsupported file format: %s (use .csv or .xlsx)", suffix)
        return []
