"""
Pydantic data models for leads, outreach messages, and campaigns.
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, EmailStr, HttpUrl, Field


class LeadSource(str, Enum):
    LINKEDIN = "linkedin"
    LINKEDIN_POST = "linkedin_post"   # lead found via a service-request post
    GOOGLE_MAPS = "google_maps"
    GOOGLE_SEARCH = "google_search"
    MANUAL = "manual"


class LeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    REPLIED = "replied"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATING = "negotiating"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
    NOT_INTERESTED = "not_interested"


class OutreachChannel(str, Enum):
    LINKEDIN_CONNECTION = "linkedin_connection"
    LINKEDIN_MESSAGE = "linkedin_message"
    LINKEDIN_INMAIL = "linkedin_inmail"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class Lead(BaseModel):
    """Core lead record."""
    id: Optional[str] = None

    # Identity
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    title: str = ""          # Job title
    seniority: str = ""      # C-Suite / Director / Manager / etc.

    # Company
    company_name: str = ""
    company_website: Optional[str] = None
    company_size: str = ""
    industry: str = ""
    annual_revenue: str = ""
    company_description: str = ""

    # Contact
    email: Optional[str] = None
    email_verified: bool = False
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None

    # Location
    city: str = ""
    state: str = ""
    country: str = ""
    address: str = ""

    # Google Maps specific
    google_place_id: Optional[str] = None
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    business_hours: Optional[str] = None

    # Scoring & qualification
    lead_score: int = 0           # 0-100
    icp_match: bool = False       # Ideal Customer Profile
    pain_points: List[str] = []
    services_needed: List[str] = []
    buying_signals: List[str] = []

    # Metadata
    source: LeadSource = LeadSource.MANUAL
    status: LeadStatus = LeadStatus.NEW
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    last_contacted_at: Optional[datetime] = None
    notes: str = ""
    tags: List[str] = []


class OutreachMessage(BaseModel):
    """Generated outreach message for a lead."""
    lead_id: str
    channel: OutreachChannel
    subject: Optional[str] = None    # for email
    message: str
    follow_up_1: Optional[str] = None
    follow_up_2: Optional[str] = None
    follow_up_3: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    opened: bool = False
    replied: bool = False


class Campaign(BaseModel):
    """A lead generation campaign configuration."""
    name: str
    description: str = ""
    source: LeadSource
    target_industries: List[str] = []
    target_titles: List[str] = []
    target_locations: List[str] = []
    services_to_pitch: List[str] = []
    max_leads: int = 100
    outreach_channels: List[OutreachChannel] = []
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    leads: List[Lead] = []


class ServiceRequestPost(BaseModel):
    """
    A LinkedIn post where someone is actively asking for a service
    (e.g. 'Looking for a web designer', 'Need help with SEO').
    """
    id: str                              # urn:li:activity:xxxx or generated hash
    post_text: str                       # Full text of the post
    post_url: Optional[str] = None       # Direct link to the post

    # Poster info (the potential lead)
    poster_urn: str = ""
    poster_name: str = ""
    poster_first_name: str = ""
    poster_title: str = ""
    poster_company: str = ""
    poster_linkedin_url: Optional[str] = None
    poster_profile_image: Optional[str] = None

    # What they're asking for
    services_requested: List[str] = []   # e.g. ["Web Design", "SEO"]
    keywords_matched: List[str] = []     # which trigger keywords matched
    urgency: str = "medium"              # low / medium / high
    budget_mentioned: bool = False
    location_mentioned: str = ""

    # Opportunity scoring
    opportunity_score: int = 0           # 0-100
    is_qualified: bool = False

    # Outreach
    dm_sent: bool = False
    dm_sent_at: Optional[datetime] = None
    dm_message: Optional[str] = None

    # Meta
    post_age_hours: Optional[float] = None
    engagement: int = 0                  # likes + comments
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    notes: str = ""

    # Link to lead if profile was fetched
    lead_id: Optional[str] = None

    """Result of a single scraping run."""
    campaign_name: str
    source: LeadSource
    total_found: int = 0
    total_scraped: int = 0
    total_enriched: int = 0
    total_outreach_generated: int = 0
    errors: List[str] = []
    leads: List[Lead] = []
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
