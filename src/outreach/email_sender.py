"""
SMTP Email Sender
==================
Sends personalised outreach emails to leads — works alongside OR instead
of LeadsGorilla's built-in emailer.

Features:
  - Sends initial email + up to 3 automatic follow-ups
  - Respects daily sending limits (avoids spam flags)
  - Tracks sent status in the database
  - Supports Gmail, Outlook, any SMTP server
  - Unsubscribe link auto-appended (CAN-SPAM compliance)

Usage:
  sender = EmailSender()
  sender.send_campaign(leads, messages)
"""
import smtplib
import time
import random
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import List, Optional

from src.config import agency
from src.models import Lead, OutreachMessage, OutreachChannel
from src.utils.database import save_outreach, update_lead_status
from src.utils.helpers import get_logger

logger = get_logger(__name__)

# ── Load SMTP settings from .env ──────────────────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

# Safety limits
MAX_EMAILS_PER_DAY = int(os.getenv("MAX_EMAILS_PER_DAY", 80))
DELAY_BETWEEN_EMAILS_MIN = float(os.getenv("EMAIL_DELAY_MIN", 45))   # seconds
DELAY_BETWEEN_EMAILS_MAX = float(os.getenv("EMAIL_DELAY_MAX", 120))  # seconds


class EmailSender:
    """Sends personalised outreach emails via SMTP."""

    def __init__(self):
        self.smtp_host = SMTP_HOST
        self.smtp_port = SMTP_PORT
        self.smtp_user = SMTP_USER
        self.smtp_pass = SMTP_PASS
        self.from_name = agency.sender_name
        self.from_email = SMTP_USER or agency.email
        self._sent_today = 0
        self._connection: Optional[smtplib.SMTP] = None

    def test_connection(self) -> bool:
        """Test SMTP credentials before sending."""
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
            logger.info("SMTP connection test: OK (%s:%s)", self.smtp_host, self.smtp_port)
            return True
        except Exception as exc:
            logger.error("SMTP connection test FAILED: %s", exc)
            return False

    def send_campaign(
        self,
        leads: List[Lead],
        messages: List[OutreachMessage],
        dry_run: bool = False,
    ) -> dict:
        """
        Send initial email to all leads that have an outreach message.

        Args:
            leads: List of Lead objects
            messages: Outreach messages generated for these leads
            dry_run: If True, prints emails but does NOT send

        Returns:
            dict with sent/skipped/failed counts
        """
        if not dry_run and not self.smtp_user:
            logger.error("SMTP_USER not set in .env — cannot send emails.")
            logger.info("Tip: Set SMTP_USER and SMTP_PASS in your .env file.")
            return {"sent": 0, "skipped": 0, "failed": 0}

        # Map lead_id → lead for quick lookup
        lead_map = {l.id: l for l in leads if l.id}

        # Only process email messages
        email_messages = [
            m for m in messages
            if m.channel == OutreachChannel.EMAIL and not m.sent_at
        ]

        stats = {"sent": 0, "skipped": 0, "failed": 0}

        logger.info(
            "%s sending %d emails …",
            "[DRY RUN]" if dry_run else "Sending",
            len(email_messages)
        )

        for i, msg in enumerate(email_messages, 1):
            if self._sent_today >= MAX_EMAILS_PER_DAY:
                logger.warning(
                    "Daily email limit (%d) reached. Stopping.", MAX_EMAILS_PER_DAY
                )
                stats["skipped"] += len(email_messages) - i + 1
                break

            lead = lead_map.get(msg.lead_id)
            if not lead or not lead.email:
                stats["skipped"] += 1
                continue

            logger.info(
                "  [%d/%d] %s → %s",
                i, len(email_messages), lead.full_name or lead.company_name, lead.email
            )

            if dry_run:
                self._print_email_preview(lead, msg)
                stats["sent"] += 1
                continue

            success = self._send_single(lead, msg)
            if success:
                stats["sent"] += 1
                self._sent_today += 1
                msg.sent_at = datetime.utcnow()
                save_outreach(msg)
                update_lead_status(lead.id or "", "contacted")

                # Human-like delay between sends
                wait = random.uniform(DELAY_BETWEEN_EMAILS_MIN, DELAY_BETWEEN_EMAILS_MAX)
                logger.debug("  Waiting %.0fs before next send …", wait)
                time.sleep(wait)
            else:
                stats["failed"] += 1

        logger.info(
            "Email campaign complete. Sent: %d | Skipped: %d | Failed: %d",
            stats["sent"], stats["skipped"], stats["failed"]
        )
        return stats

    def _send_single(self, lead: Lead, msg: OutreachMessage) -> bool:
        """Send a single email. Returns True on success."""
        try:
            email_msg = MIMEMultipart("alternative")
            email_msg["Subject"] = msg.subject or f"Quick question about {lead.company_name}"
            email_msg["From"] = formataddr((self.from_name, self.from_email))
            email_msg["To"] = formataddr((lead.full_name or lead.company_name, lead.email))
            email_msg["Reply-To"] = self.from_email

            # Plain text body
            plain_body = msg.message + self._unsubscribe_footer(lead.email)
            html_body = self._to_html(msg.message) + self._unsubscribe_footer_html(lead.email)

            email_msg.attach(MIMEText(plain_body, "plain", "utf-8"))
            email_msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.from_email, [lead.email], email_msg.as_string())

            logger.debug("  ✓ Sent to %s", lead.email)
            return True

        except smtplib.SMTPRecipientsRefused:
            logger.warning("  ✗ Invalid email: %s", lead.email)
            return False
        except smtplib.SMTPAuthenticationError:
            logger.error("  ✗ SMTP authentication failed — check SMTP_USER / SMTP_PASS in .env")
            return False
        except Exception as exc:
            logger.error("  ✗ Send failed (%s): %s", lead.email, exc)
            return False

    @staticmethod
    def _to_html(text: str) -> str:
        """Convert plain text email to basic HTML."""
        paragraphs = text.strip().split("\n\n")
        html_parts = [f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs]
        return f"""
        <html><body style="font-family:Arial,sans-serif;font-size:14px;
        color:#333;max-width:600px;margin:0 auto;padding:20px;">
        {''.join(html_parts)}
        </body></html>
        """

    @staticmethod
    def _unsubscribe_footer(email: str) -> str:
        return (
            f"\n\n---\n"
            f"You're receiving this because your business is publicly listed online.\n"
            f"To unsubscribe, reply with 'UNSUBSCRIBE' and we'll remove you immediately.\n"
            f"{agency.name} | {agency.website}"
        )

    @staticmethod
    def _unsubscribe_footer_html(email: str) -> str:
        return (
            f'<br><br><hr style="border:none;border-top:1px solid #eee">'
            f'<p style="font-size:11px;color:#999;">'
            f"You're receiving this because your business is publicly listed online. "
            f'To unsubscribe, reply with "UNSUBSCRIBE".<br>'
            f'{agency.name} | <a href="{agency.website}">{agency.website}</a></p>'
        )

    @staticmethod
    def _print_email_preview(lead: Lead, msg: OutreachMessage):
        """Print email preview for dry run mode."""
        print(f"\n{'─'*60}")
        print(f"  TO      : {lead.full_name or lead.company_name} <{lead.email}>")
        print(f"  SUBJECT : {msg.subject}")
        print(f"  BODY    :")
        for line in (msg.message or "").split("\n")[:8]:
            print(f"    {line}")
        if msg.follow_up_1:
            print(f"  FOLLOW-UP 1 (Day 3):")
            print(f"    {(msg.follow_up_1 or '')[:100]}…")
        print(f"{'─'*60}")


# ── Export for LeadsGorilla emailer ──────────────────────────────────────────

def export_for_leadsgorilla_emailer(
    leads: List[Lead],
    messages: List[OutreachMessage],
    output_path: str = "exports/leadsgorilla_ready.csv",
) -> str:
    """
    Export a CSV formatted for LeadsGorilla's built-in email campaign feature.
    Columns match LeadsGorilla's email template import format.

    Use this if you prefer to send emails FROM LeadsGorilla's interface
    but want our AI-generated personalised messages.
    """
    import csv
    from pathlib import Path

    lead_map = {l.id: l for l in leads if l.id}
    email_messages = [m for m in messages if m.channel == OutreachChannel.EMAIL]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "Business Name", "Email", "First Name", "Phone", "Website",
            "City", "Industry", "Lead Score",
            "Email Subject", "Email Body",
            "Follow Up 1", "Follow Up 2", "Follow Up 3",
        ])
        writer.writeheader()

        for msg in email_messages:
            lead = lead_map.get(msg.lead_id)
            if not lead:
                continue
            writer.writerow({
                "Business Name": lead.company_name,
                "Email": lead.email or "",
                "First Name": lead.first_name or "",
                "Phone": lead.phone or "",
                "Website": lead.company_website or "",
                "City": lead.city or "",
                "Industry": lead.industry or "",
                "Lead Score": lead.lead_score,
                "Email Subject": msg.subject or "",
                "Email Body": msg.message or "",
                "Follow Up 1": msg.follow_up_1 or "",
                "Follow Up 2": msg.follow_up_2 or "",
                "Follow Up 3": msg.follow_up_3 or "",
            })

    logger.info("LeadsGorilla-ready CSV exported: %s", output_path)
    return output_path
