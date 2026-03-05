"""
Meta Comment Monitor
=====================
Polls the Meta Graph API for comments containing "AI Content"
(case-insensitive, any spacing/capitalisation, e.g. "ai content",
"AI CONTENT", "AiContent", "A.I. Content") on a Facebook Page's
posts and Instagram media.

When a matching comment is found the commenter's PSID (Page-Scoped ID)
is returned so a Messenger DM can be queued by the campaign manager.

Processed comment IDs are stored in SQLite so the same comment is
never acted on twice.

Requirements (install via pip):
  requests

Meta permissions required on your App:
  pages_read_engagement, pages_manage_metadata,
  instagram_basic, instagram_manage_comments,
  pages_messaging  (for DMs)
"""

import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import requests

from src.config import meta_cfg, db_cfg
from src.utils.helpers import get_logger

logger = get_logger(__name__)

# Regex: matches "ai content" with any caps, optional punctuation/spaces
AI_CONTENT_PATTERN = re.compile(
    r"\bai[\s.\-_]*content\b",
    re.IGNORECASE,
)

META_GRAPH_BASE = "https://graph.facebook.com/v19.0"


@dataclass
class MetaComment:
    comment_id: str
    post_id: str
    commenter_psid: str          # Facebook Page-Scoped ID of the commenter
    commenter_name: str
    comment_text: str
    platform: str                # "facebook" | "instagram"
    created_time: str
    instagram_user_id: str = ""  # for Instagram DMs
    already_sent_dm: bool = False


# ── SQLite helpers ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_cfg.path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_meta_tables():
    """Create tables for Meta comment tracking if they don't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_processed_comments (
                comment_id   TEXT PRIMARY KEY,
                post_id      TEXT,
                psid         TEXT,
                commenter    TEXT,
                comment_text TEXT,
                platform     TEXT,
                dm_sent      INTEGER DEFAULT 0,
                created_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_leads (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                psid              TEXT UNIQUE,
                instagram_user_id TEXT,
                commenter_name    TEXT,
                comment_text      TEXT,
                platform          TEXT,
                full_name         TEXT,
                phone             TEXT,
                company_email     TEXT,
                company_name      TEXT,
                website           TEXT,
                report_generated  INTEGER DEFAULT 0,
                report_approved   INTEGER DEFAULT 0,
                report_sent       INTEGER DEFAULT 0,
                report_path       TEXT,
                created_at        TEXT DEFAULT (datetime('now')),
                updated_at        TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def _is_comment_processed(comment_id: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM meta_processed_comments WHERE comment_id = ?",
            (comment_id,)
        ).fetchone()
    return row is not None


def _mark_comment_processed(comment: MetaComment):
    with _get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO meta_processed_comments
                (comment_id, post_id, psid, commenter, comment_text, platform)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            comment.comment_id,
            comment.post_id,
            comment.commenter_psid,
            comment.commenter_name,
            comment.comment_text,
            comment.platform,
        ))
        conn.commit()


def _upsert_meta_lead(comment: MetaComment):
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO meta_leads
                (psid, instagram_user_id, commenter_name, comment_text, platform)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(psid) DO UPDATE SET
                updated_at = datetime('now')
        """, (
            comment.commenter_psid,
            comment.instagram_user_id,
            comment.commenter_name,
            comment.comment_text,
            comment.platform,
        ))
        conn.commit()


# ── Meta Graph API helpers ─────────────────────────────────────────────────────

class MetaAPIError(Exception):
    pass


def _graph_get(path: str, params: dict) -> dict:
    """GET request to Meta Graph API with rate-limit awareness."""
    url = f"{META_GRAPH_BASE}/{path.lstrip('/')}"
    params["access_token"] = meta_cfg.page_access_token
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        raise MetaAPIError(f"Graph API HTTP error: {exc.response.text}") from exc


def _get_page_posts(page_id: str, limit: int = 10) -> List[dict]:
    """Fetch the most recent posts from a Facebook Page."""
    data = _graph_get(
        f"{page_id}/feed",
        {
            "fields": "id,message,created_time",
            "limit": limit,
        }
    )
    return data.get("data", [])


def _get_post_comments(post_id: str, limit: int = 100) -> List[dict]:
    """Fetch comments on a post/photo/video."""
    data = _graph_get(
        f"{post_id}/comments",
        {
            "fields": "id,message,from,created_time",
            "limit": limit,
            "filter": "stream",
        }
    )
    return data.get("data", [])


def _get_commenter_psid(comment_from: dict, page_id: str) -> str:
    """
    Extract the commenter's PSID.
    The 'from' field in comment data already contains the page-scoped user id.
    """
    return comment_from.get("id", "")


def _get_instagram_media(ig_account_id: str, limit: int = 10) -> List[dict]:
    """Fetch recent Instagram media for the connected Business Account."""
    data = _graph_get(
        f"{ig_account_id}/media",
        {
            "fields": "id,caption,timestamp",
            "limit": limit,
        }
    )
    return data.get("data", [])


def _get_instagram_comments(media_id: str, limit: int = 100) -> List[dict]:
    """Fetch comments on an Instagram media object."""
    data = _graph_get(
        f"{media_id}/comments",
        {
            "fields": "id,text,username,timestamp,from",
            "limit": limit,
        }
    )
    return data.get("data", [])


# ── Comment Monitor ────────────────────────────────────────────────────────────

class CommentMonitor:
    """
    Polls Meta (Facebook + Instagram) for comments containing
    "AI Content" and returns new unprocessed matching comments.
    """

    def __init__(self):
        _init_meta_tables()
        self.page_id = meta_cfg.page_id
        self.ig_account_id = meta_cfg.instagram_account_id

    def scan_facebook(self, max_posts: int = 20) -> List[MetaComment]:
        """Scan Facebook page posts for matching comments."""
        matching: List[MetaComment] = []

        if not self.page_id:
            logger.warning("META_PAGE_ID not set — skipping Facebook scan.")
            return matching

        logger.info("Scanning Facebook page %s for 'AI Content' comments...", self.page_id)

        try:
            posts = _get_page_posts(self.page_id, limit=max_posts)
        except MetaAPIError as exc:
            logger.error("Failed to fetch Facebook posts: %s", exc)
            return matching

        for post in posts:
            post_id = post["id"]
            try:
                comments = _get_post_comments(post_id)
            except MetaAPIError as exc:
                logger.warning("Could not fetch comments for post %s: %s", post_id, exc)
                continue

            for c in comments:
                comment_id = c["id"]
                text = c.get("message", "")

                if not AI_CONTENT_PATTERN.search(text):
                    continue
                if _is_comment_processed(comment_id):
                    continue

                commenter = c.get("from", {})
                psid = _get_commenter_psid(commenter, self.page_id)
                name = commenter.get("name", "there")

                mc = MetaComment(
                    comment_id=comment_id,
                    post_id=post_id,
                    commenter_psid=psid,
                    commenter_name=name,
                    comment_text=text,
                    platform="facebook",
                    created_time=c.get("created_time", ""),
                )
                matching.append(mc)
                logger.info(
                    "  [FB] New 'AI Content' comment by %s: %s",
                    name, text[:80]
                )

        return matching

    def scan_instagram(self, max_media: int = 20) -> List[MetaComment]:
        """Scan Instagram media for matching comments."""
        matching: List[MetaComment] = []

        if not self.ig_account_id:
            logger.warning("META_IG_ACCOUNT_ID not set — skipping Instagram scan.")
            return matching

        logger.info(
            "Scanning Instagram account %s for 'AI Content' comments...",
            self.ig_account_id
        )

        try:
            media_list = _get_instagram_media(self.ig_account_id, limit=max_media)
        except MetaAPIError as exc:
            logger.error("Failed to fetch Instagram media: %s", exc)
            return matching

        for media in media_list:
            media_id = media["id"]
            try:
                comments = _get_instagram_comments(media_id)
            except MetaAPIError as exc:
                logger.warning("Could not fetch IG comments for %s: %s", media_id, exc)
                continue

            for c in comments:
                comment_id = c["id"]
                text = c.get("text", "")

                if not AI_CONTENT_PATTERN.search(text):
                    continue
                if _is_comment_processed(comment_id):
                    continue

                commenter = c.get("from", {})
                ig_user_id = commenter.get("id", "")
                name = c.get("username", "there")

                mc = MetaComment(
                    comment_id=comment_id,
                    post_id=media_id,
                    commenter_psid=ig_user_id,   # used as DM target for IG
                    commenter_name=name,
                    comment_text=text,
                    platform="instagram",
                    created_time=c.get("timestamp", ""),
                    instagram_user_id=ig_user_id,
                )
                matching.append(mc)
                logger.info(
                    "  [IG] New 'AI Content' comment by @%s: %s",
                    name, text[:80]
                )

        return matching

    def scan_all(self, max_posts: int = 20) -> List[MetaComment]:
        """Scan both Facebook and Instagram, return all new matching comments."""
        fb_matches = self.scan_facebook(max_posts=max_posts)
        ig_matches = self.scan_instagram(max_media=max_posts)
        all_matches = fb_matches + ig_matches

        # Persist to DB
        for mc in all_matches:
            _mark_comment_processed(mc)
            _upsert_meta_lead(mc)

        logger.info(
            "Scan complete. Found %d new 'AI Content' comment(s) "
            "(%d Facebook, %d Instagram).",
            len(all_matches), len(fb_matches), len(ig_matches)
        )
        return all_matches
