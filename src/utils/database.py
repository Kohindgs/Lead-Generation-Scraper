"""
SQLite persistence layer for leads, outreach messages, and campaign results.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.config import db_cfg
from src.models import Lead, OutreachMessage, LeadStatus, LeadSource, ServiceRequestPost
from src.utils.helpers import get_logger

logger = get_logger(__name__)


def _get_db_path() -> Path:
    path = Path(db_cfg.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_connection():
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            full_name TEXT,
            title TEXT,
            seniority TEXT,
            company_name TEXT,
            company_website TEXT,
            company_size TEXT,
            industry TEXT,
            annual_revenue TEXT,
            company_description TEXT,
            email TEXT,
            email_verified INTEGER DEFAULT 0,
            phone TEXT,
            linkedin_url TEXT,
            twitter_url TEXT,
            city TEXT,
            state TEXT,
            country TEXT,
            address TEXT,
            google_place_id TEXT,
            google_rating REAL,
            google_review_count INTEGER,
            business_hours TEXT,
            lead_score INTEGER DEFAULT 0,
            icp_match INTEGER DEFAULT 0,
            pain_points TEXT,
            services_needed TEXT,
            buying_signals TEXT,
            source TEXT,
            status TEXT DEFAULT 'new',
            scraped_at TEXT,
            last_contacted_at TEXT,
            notes TEXT,
            tags TEXT
        );

        CREATE TABLE IF NOT EXISTS outreach_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT,
            channel TEXT,
            subject TEXT,
            message TEXT,
            follow_up_1 TEXT,
            follow_up_2 TEXT,
            follow_up_3 TEXT,
            generated_at TEXT,
            sent_at TEXT,
            opened INTEGER DEFAULT 0,
            replied INTEGER DEFAULT 0,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        CREATE TABLE IF NOT EXISTS campaign_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_name TEXT,
            source TEXT,
            total_found INTEGER,
            total_scraped INTEGER,
            total_enriched INTEGER,
            total_outreach INTEGER,
            errors TEXT,
            started_at TEXT,
            finished_at TEXT,
            duration_seconds REAL
        );

        CREATE TABLE IF NOT EXISTS service_request_posts (
            id TEXT PRIMARY KEY,
            post_text TEXT,
            post_url TEXT,
            poster_urn TEXT,
            poster_name TEXT,
            poster_first_name TEXT,
            poster_title TEXT,
            poster_company TEXT,
            poster_linkedin_url TEXT,
            services_requested TEXT,
            keywords_matched TEXT,
            urgency TEXT,
            budget_mentioned INTEGER DEFAULT 0,
            location_mentioned TEXT,
            opportunity_score INTEGER DEFAULT 0,
            is_qualified INTEGER DEFAULT 0,
            dm_sent INTEGER DEFAULT 0,
            dm_sent_at TEXT,
            dm_message TEXT,
            post_age_hours REAL,
            engagement INTEGER DEFAULT 0,
            scraped_at TEXT,
            notes TEXT,
            lead_id TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
        CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
        CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(lead_score);
        CREATE INDEX IF NOT EXISTS idx_leads_industry ON leads(industry);
        CREATE INDEX IF NOT EXISTS idx_outreach_lead ON outreach_messages(lead_id);
        CREATE INDEX IF NOT EXISTS idx_posts_score ON service_request_posts(opportunity_score);
        CREATE INDEX IF NOT EXISTS idx_posts_dm ON service_request_posts(dm_sent);
        """)
    logger.info("Database initialised at %s", db_cfg.path)


def upsert_lead(lead: Lead) -> bool:
    """Insert or update a lead. Returns True if newly inserted."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM leads WHERE id = ?", (lead.id,)
        ).fetchone()

        data = (
            lead.id, lead.first_name, lead.last_name, lead.full_name,
            lead.title, lead.seniority, lead.company_name,
            lead.company_website, lead.company_size, lead.industry,
            lead.annual_revenue, lead.company_description, lead.email,
            int(lead.email_verified), lead.phone, lead.linkedin_url,
            lead.twitter_url, lead.city, lead.state, lead.country,
            lead.address, lead.google_place_id, lead.google_rating,
            lead.google_review_count, lead.business_hours,
            lead.lead_score, int(lead.icp_match),
            json.dumps(lead.pain_points),
            json.dumps(lead.services_needed),
            json.dumps(lead.buying_signals),
            lead.source.value, lead.status.value,
            lead.scraped_at.isoformat(),
            lead.last_contacted_at.isoformat() if lead.last_contacted_at else None,
            lead.notes, json.dumps(lead.tags),
        )

        if existing:
            conn.execute("""
                UPDATE leads SET
                    first_name=?, last_name=?, full_name=?, title=?,
                    seniority=?, company_name=?, company_website=?,
                    company_size=?, industry=?, annual_revenue=?,
                    company_description=?, email=?, email_verified=?,
                    phone=?, linkedin_url=?, twitter_url=?, city=?,
                    state=?, country=?, address=?, google_place_id=?,
                    google_rating=?, google_review_count=?, business_hours=?,
                    lead_score=?, icp_match=?, pain_points=?,
                    services_needed=?, buying_signals=?, source=?,
                    status=?, scraped_at=?, last_contacted_at=?,
                    notes=?, tags=?
                WHERE id=?
            """, data[1:] + (lead.id,))
            return False
        else:
            conn.execute("""
                INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, data)
            return True


def save_outreach(msg: OutreachMessage):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO outreach_messages
            (lead_id, channel, subject, message, follow_up_1, follow_up_2,
             follow_up_3, generated_at, sent_at, opened, replied)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            msg.lead_id, msg.channel.value, msg.subject, msg.message,
            msg.follow_up_1, msg.follow_up_2, msg.follow_up_3,
            msg.generated_at.isoformat(),
            msg.sent_at.isoformat() if msg.sent_at else None,
            int(msg.opened), int(msg.replied),
        ))


def get_leads(
    status: Optional[str] = None,
    source: Optional[str] = None,
    min_score: int = 0,
    limit: int = 1000,
) -> List[dict]:
    query = "SELECT * FROM leads WHERE lead_score >= ?"
    params: list = [min_score]
    if status:
        query += " AND status = ?"
        params.append(status)
    if source:
        query += " AND source = ?"
        params.append(source)
    query += " ORDER BY lead_score DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_lead_status(lead_id: str, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE leads SET status=? WHERE id=?", (status, lead_id)
        )


def upsert_service_post(post: ServiceRequestPost):
    """Insert or update a service-request post."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO service_request_posts
            (id, post_text, post_url, poster_urn, poster_name, poster_first_name,
             poster_title, poster_company, poster_linkedin_url, services_requested,
             keywords_matched, urgency, budget_mentioned, location_mentioned,
             opportunity_score, is_qualified, dm_sent, dm_sent_at, dm_message,
             post_age_hours, engagement, scraped_at, notes, lead_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                dm_sent=excluded.dm_sent,
                dm_sent_at=excluded.dm_sent_at,
                dm_message=excluded.dm_message,
                opportunity_score=excluded.opportunity_score,
                lead_id=excluded.lead_id
        """, (
            post.id, post.post_text, post.post_url, post.poster_urn,
            post.poster_name, post.poster_first_name, post.poster_title,
            post.poster_company, post.poster_linkedin_url,
            json.dumps(post.services_requested),
            json.dumps(post.keywords_matched),
            post.urgency, int(post.budget_mentioned), post.location_mentioned,
            post.opportunity_score, int(post.is_qualified),
            int(post.dm_sent),
            post.dm_sent_at.isoformat() if post.dm_sent_at else None,
            post.dm_message, post.post_age_hours, post.engagement,
            post.scraped_at.isoformat(), post.notes, post.lead_id,
        ))


def get_seen_post_ids() -> set:
    """Return set of post IDs already in the database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM service_request_posts").fetchall()
    return {r["id"] for r in rows}


def get_service_posts_today() -> List[dict]:
    """Return service posts scraped today."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM service_request_posts WHERE scraped_at LIKE ?",
            (f"{today}%",)
        ).fetchall()
    return [dict(r) for r in rows]


def get_leads_today() -> List[dict]:
    """Return leads scraped today."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE scraped_at LIKE ?",
            (f"{today}%",)
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM leads GROUP BY status"
        ).fetchall()
        by_source = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM leads GROUP BY source"
        ).fetchall()
        avg_score = conn.execute(
            "SELECT ROUND(AVG(lead_score),1) FROM leads"
        ).fetchone()[0]
        top_industries = conn.execute(
            "SELECT industry, COUNT(*) as cnt FROM leads "
            "GROUP BY industry ORDER BY cnt DESC LIMIT 10"
        ).fetchall()

    return {
        "total_leads": total,
        "avg_score": avg_score or 0,
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "by_source": {r["source"]: r["cnt"] for r in by_source},
        "top_industries": [(r["industry"], r["cnt"]) for r in top_industries],
    }
