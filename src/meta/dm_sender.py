"""
Meta DM Sender
==============
Sends Messenger (Facebook) and Instagram Direct Messages to users who
commented "AI Content" on our posts/ads.

The DM contains a warm, personalised intro + a link to our Google Form
so the lead can share their business details for a free brand audit.

Meta APIs used:
  - Facebook Messenger Send API  (v19.0 /me/messages)
  - Instagram Messaging API      (v19.0 /{ig-user-id}/messages)

Permissions required on your Meta App:
  pages_messaging, instagram_manage_messages
"""

import sqlite3
import time
from typing import Optional

import requests

from src.config import meta_cfg, agency, db_cfg
from src.meta.comment_monitor import MetaComment
from src.utils.helpers import get_logger

logger = get_logger(__name__)

META_GRAPH_BASE = "https://graph.facebook.com/v19.0"

# ── DM Template ───────────────────────────────────────────────────────────────

DM_TEMPLATE = """Hi {name}!

Thanks for your interest in AI Content — you've landed in the right place!

At {agency_name} we help brands like yours elevate their digital presence using smart, AI-driven strategies.

To kick things off, we'd love to put together a *FREE personalised brand report* for you — covering your current online standing and exactly where you can grow.

It takes less than 2 minutes to fill in your details here:
{form_url}

We'll review your brand and share insights + a tailored recommendation report — no obligation at all.

Looking forward to connecting!

{sender_name}
{agency_name}
{agency_website}"""


# ── SQLite helper ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_cfg.path)
    conn.row_factory = sqlite3.Row
    return conn


def _mark_dm_sent(comment_id: str, psid: str):
    with _get_conn() as conn:
        conn.execute(
            "UPDATE meta_processed_comments SET dm_sent = 1 WHERE comment_id = ?",
            (comment_id,)
        )
        conn.execute(
            "UPDATE meta_leads SET updated_at = datetime('now') WHERE psid = ?",
            (psid,)
        )
        conn.commit()


# ── Facebook Messenger Send API ────────────────────────────────────────────────

def _send_facebook_dm(psid: str, message_text: str) -> bool:
    """
    Send a Messenger DM to a Facebook user identified by their PSID.
    Returns True on success.
    """
    url = f"{META_GRAPH_BASE}/me/messages"
    payload = {
        "recipient": {"id": psid},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE",
        "access_token": meta_cfg.page_access_token,
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if "message_id" in data or "recipient_id" in data:
            logger.info("Facebook DM sent to PSID %s", psid)
            return True
        logger.warning("Unexpected Messenger response: %s", data)
        return False
    except requests.HTTPError as exc:
        logger.error(
            "Failed to send Facebook DM to %s: %s",
            psid, exc.response.text if exc.response else exc
        )
        return False


# ── Instagram Messaging API ────────────────────────────────────────────────────

def _send_instagram_dm(ig_user_id: str, message_text: str) -> bool:
    """
    Send an Instagram Direct Message to a user via their Instagram User ID.
    Requires instagram_manage_messages permission.
    Returns True on success.
    """
    url = f"{META_GRAPH_BASE}/{meta_cfg.instagram_account_id}/messages"
    payload = {
        "recipient": {"id": ig_user_id},
        "message": {"text": message_text},
        "access_token": meta_cfg.page_access_token,
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if "message_id" in data or "recipient_id" in data:
            logger.info("Instagram DM sent to user %s", ig_user_id)
            return True
        logger.warning("Unexpected IG messaging response: %s", data)
        return False
    except requests.HTTPError as exc:
        logger.error(
            "Failed to send Instagram DM to %s: %s",
            ig_user_id, exc.response.text if exc.response else exc
        )
        return False


# ── Public sender ──────────────────────────────────────────────────────────────

class DMSender:
    """
    Sends personalised DMs containing the Google Form link to commenters
    who typed "AI Content" on our Meta posts.
    """

    def __init__(self):
        self.form_url = meta_cfg.google_form_url
        self.page_access_token = meta_cfg.page_access_token

    def build_dm_text(self, commenter_name: str, psid: str = "") -> str:
        first_name = commenter_name.split()[0] if commenter_name else "there"
        form_url = self.form_url.replace("PSID_PLACEHOLDER", psid) if psid else self.form_url
        return DM_TEMPLATE.format(
            name=first_name,
            agency_name=agency.name,
            form_url=form_url,
            sender_name=agency.sender_name,
            agency_website=agency.website,
        )

    def send(self, comment: MetaComment, dry_run: bool = False) -> bool:
        """
        Send a DM for a matched comment. Returns True if sent (or would be sent
        in dry_run mode).
        """
        message = self.build_dm_text(comment.commenter_name, comment.commenter_psid)

        if dry_run:
            print(f"\n{'─'*60}")
            print(f"[DRY RUN] Would DM {comment.commenter_name} ({comment.platform})")
            print(f"PSID / IG User ID: {comment.commenter_psid}")
            print(f"Message:\n{message}")
            print(f"{'─'*60}")
            return True

        if not self.page_access_token:
            logger.error(
                "META_PAGE_ACCESS_TOKEN not configured — cannot send DM."
            )
            return False

        if not self.form_url:
            logger.error(
                "META_GOOGLE_FORM_URL not configured — "
                "set it in .env before sending DMs."
            )
            return False

        sent = False
        if comment.platform == "facebook":
            sent = _send_facebook_dm(comment.commenter_psid, message)
        elif comment.platform == "instagram":
            sent = _send_instagram_dm(comment.instagram_user_id, message)
        else:
            logger.warning("Unknown platform '%s' — skipping DM.", comment.platform)

        if sent:
            _mark_dm_sent(comment.comment_id, comment.commenter_psid)
            # Respect Meta rate limits
            time.sleep(1)

        return sent

    def send_batch(
        self,
        comments: list,
        dry_run: bool = False,
    ) -> dict:
        """Send DMs to a batch of matched commenters."""
        stats = {"sent": 0, "failed": 0, "skipped": 0}

        for comment in comments:
            if comment.already_sent_dm:
                stats["skipped"] += 1
                continue

            ok = self.send(comment, dry_run=dry_run)
            if ok:
                stats["sent"] += 1
            else:
                stats["failed"] += 1

        logger.info(
            "DM batch complete — Sent: %d | Failed: %d | Skipped: %d",
            stats["sent"], stats["failed"], stats["skipped"]
        )
        return stats
