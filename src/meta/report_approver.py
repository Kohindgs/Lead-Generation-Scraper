"""
Report Approval Workflow
========================
CLI tool for the DGenius team to review, approve, edit, and send
brand audit reports BEFORE they reach the prospect.

Workflow:
  1. Brand report is generated (by webhook handler after form submission)
  2. Admin runs: python main.py meta-reply review
  3. Admin sees pending reports one by one
  4. Admin can: approve → send | skip | reject | edit subject/note
  5. Approved reports are sent via Gmail (Google Business) to the lead's email

Usage:
  python main.py meta-reply review          # interactive review queue
  python main.py meta-reply list            # list all pending reports
  python main.py meta-reply send --psid X   # force-send a specific report
"""

import json
import smtplib
import sqlite3
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from src.config import meta_cfg, agency, db_cfg
from src.utils.helpers import get_logger

logger = get_logger(__name__)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_cfg.path)
    conn.row_factory = sqlite3.Row
    return conn


def get_pending_reports() -> list:
    """Return leads that have a generated report not yet approved."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT
                ml.psid, ml.commenter_name, ml.platform,
                ml.full_name, ml.company_name, ml.website,
                ml.company_email, ml.phone,
                ml.report_generated, ml.report_approved, ml.report_sent,
                ml.report_path, ml.created_at,
                rp.top_services, rp.pitch_angle, rp.budget_tier,
                rp.opening_line, rp.txt_path, rp.html_path
            FROM meta_leads ml
            LEFT JOIN meta_report_pitches rp ON ml.psid = rp.psid
            WHERE ml.report_generated = 1
              AND ml.report_approved = 0
              AND ml.report_sent = 0
            ORDER BY ml.created_at ASC
        """).fetchall()
    return [dict(r) for r in rows]


def get_approved_reports() -> list:
    """Return approved, not-yet-sent reports."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT
                ml.psid, ml.full_name, ml.company_name,
                ml.company_email, ml.report_path,
                rp.html_path, rp.txt_path, rp.pitch_angle
            FROM meta_leads ml
            LEFT JOIN meta_report_pitches rp ON ml.psid = rp.psid
            WHERE ml.report_approved = 1
              AND ml.report_sent = 0
        """).fetchall()
    return [dict(r) for r in rows]


def _mark_approved(psid: str):
    with _get_conn() as conn:
        conn.execute(
            "UPDATE meta_leads SET report_approved = 1, updated_at = datetime('now') WHERE psid = ?",
            (psid,)
        )
        conn.commit()


def _mark_rejected(psid: str):
    with _get_conn() as conn:
        conn.execute(
            """UPDATE meta_leads
               SET report_generated = 0, report_approved = 0, updated_at = datetime('now')
               WHERE psid = ?""",
            (psid,)
        )
        conn.commit()


def _mark_sent(psid: str):
    with _get_conn() as conn:
        conn.execute(
            "UPDATE meta_leads SET report_sent = 1, updated_at = datetime('now') WHERE psid = ?",
            (psid,)
        )
        conn.commit()


# ── Email sender (via Google Business / Gmail SMTP) ────────────────────────────

class ReportEmailSender:
    """
    Sends approved brand audit reports to leads via Gmail SMTP
    using the configured Google Business / Google Workspace account.
    """

    def __init__(self):
        self.smtp_host = meta_cfg.smtp_host
        self.smtp_port = meta_cfg.smtp_port
        self.smtp_user = meta_cfg.smtp_user
        self.smtp_pass = meta_cfg.smtp_pass

    def _build_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        html_report_path: str,
        custom_note: str = "",
    ) -> MIMEMultipart:
        first_name = (to_name or "there").split()[0]
        subject = (
            f"Your Free Brand Audit Report — {company_name} | {agency.name}"
        )

        # Email body (short, warm intro — report is attached as HTML)
        body_html = f"""
<html><body style="font-family:'Segoe UI',Arial,sans-serif;max-width:600px;
margin:0 auto;padding:24px;color:#1a1a2e;line-height:1.7;">

<p>Hi <strong>{first_name}</strong>,</p>

<p>Thank you for reaching out! As promised, we've put together your
personalised <strong>Brand Audit Report</strong> for <em>{company_name}</em>.</p>

<p>Inside you'll find:</p>
<ul>
  <li>Your current brand standing across website, SEO, and social</li>
  <li>Key gaps and the biggest growth opportunities we identified</li>
  <li>Our recommended services tailored specifically for {company_name}</li>
  <li>A 30/60/90-day priority action plan</li>
</ul>

{f'<p><em>{custom_note}</em></p>' if custom_note else ''}

<p>We'd love to walk you through these findings on a quick
<strong>FREE 30-minute strategy call</strong> — no pressure, just genuine insights.</p>

<p style="text-align:center;margin:32px 0;">
  <a href="{agency.website}/strategy-call"
     style="background:#e94560;color:#fff;padding:14px 28px;border-radius:8px;
            text-decoration:none;font-weight:600;display:inline-block;">
    Book Your Free Strategy Call
  </a>
</p>

<p>Looking forward to speaking with you!</p>

<p>Warm regards,<br>
<strong>{agency.sender_name}</strong><br>
{agency.sender_title}<br>
<a href="{agency.website}">{agency.name}</a> |
<a href="mailto:{agency.email}">{agency.email}</a>
</p>
</body></html>"""

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"{agency.name} <{self.smtp_user}>"
        msg["To"] = f"{to_name} <{to_email}>"

        # HTML body
        msg.attach(MIMEText(body_html, "html"))

        # Attach the brand report as HTML
        report_path = Path(html_report_path)
        if report_path.exists():
            with open(report_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            safe_name = f"Brand_Audit_{company_name.replace(' ','_')}.html"
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=safe_name,
            )
            msg.attach(part)

        return msg

    def send_report(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        html_report_path: str,
        custom_note: str = "",
        dry_run: bool = False,
    ) -> bool:
        msg = self._build_email(
            to_email, to_name, company_name, html_report_path, custom_note
        )

        if dry_run:
            print(f"\n{'─'*60}")
            print(f"[DRY RUN] Would email report to: {to_name} <{to_email}>")
            print(f"Subject : {msg['Subject']}")
            print(f"Report  : {html_report_path}")
            print(f"{'─'*60}")
            return True

        if not all([self.smtp_host, self.smtp_user, self.smtp_pass]):
            logger.error(
                "SMTP credentials not fully configured. "
                "Set META_SMTP_HOST, META_SMTP_USER, META_SMTP_PASS in .env"
            )
            return False

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.smtp_user, to_email, msg.as_string())
            logger.info("Brand report sent to %s <%s>", to_name, to_email)
            return True
        except Exception as exc:
            logger.error("Failed to send report email: %s", exc)
            return False


# ── Interactive CLI review queue ───────────────────────────────────────────────

def run_review_queue(dry_run: bool = False):
    """
    Interactive prompt-based review queue.
    Shows each pending report and lets the admin decide what to do.
    """
    pending = get_pending_reports()

    if not pending:
        print("\n  No pending brand reports to review.")
        return

    print(f"\n{'='*65}")
    print(f"  BRAND REPORT REVIEW QUEUE — {len(pending)} pending")
    print(f"{'='*65}")

    sender = ReportEmailSender()

    for i, report in enumerate(pending, 1):
        company = report.get("company_name") or report.get("commenter_name", "Unknown")
        email = report.get("company_email", "")
        name = report.get("full_name") or report.get("commenter_name", "")
        html_path = report.get("html_path") or report.get("report_path", "")
        txt_path = report.get("txt_path", "")
        psid = report["psid"]

        print(f"\n[{i}/{len(pending)}] ─────────────────────────────────────────")
        print(f"  Company  : {company}")
        print(f"  Contact  : {name} <{email}>")
        print(f"  Website  : {report.get('website', 'N/A')}")
        print(f"  Platform : {report.get('platform', 'N/A')}")
        print(f"  Comment  : {report.get('comment_text', 'N/A')[:80]}")
        print(f"  Report   : {html_path}")

        # Show pitch summary
        if report.get("top_services"):
            try:
                services = json.loads(report["top_services"])
                print(f"  Top services to pitch: {', '.join(services)}")
            except Exception:
                pass
        if report.get("pitch_angle"):
            print(f"  Pitch angle: {report['pitch_angle']}")
        if report.get("opening_line"):
            print(f"  Opening line: {report['opening_line'][:100]}")

        print()
        print("  Actions:")
        print("    [p] Preview report text")
        print("    [a] Approve & send report now")
        print("    [q] Approve & queue for later (don't send yet)")
        print("    [r] Reject (discard this report)")
        print("    [s] Skip (review later)")
        print()

        while True:
            choice = input("  Your choice [p/a/q/r/s]: ").strip().lower()

            if choice == "p":
                if txt_path and Path(txt_path).exists():
                    print("\n" + "─" * 65)
                    print(Path(txt_path).read_text(encoding="utf-8"))
                    print("─" * 65 + "\n")
                else:
                    print("  Report file not found.")
                continue

            elif choice == "a":
                if not email:
                    print("  No email address on file — cannot send. Skipping.")
                    break
                note = input("  Optional personal note to add (press Enter to skip): ").strip()
                ok = sender.send_report(
                    to_email=email,
                    to_name=name,
                    company_name=company,
                    html_report_path=html_path,
                    custom_note=note,
                    dry_run=dry_run,
                )
                if ok:
                    _mark_approved(psid)
                    _mark_sent(psid)
                    print(f"  Report approved and sent to {name} <{email}>")
                else:
                    print("  Send failed — check SMTP config. Report marked approved but not sent.")
                    _mark_approved(psid)
                break

            elif choice == "q":
                _mark_approved(psid)
                print(f"  Report approved and queued. Send later with:")
                print(f"    python main.py meta-reply send --psid {psid}")
                break

            elif choice == "r":
                _mark_rejected(psid)
                print("  Report rejected and removed from queue.")
                break

            elif choice == "s":
                print("  Skipped — will appear again on next review.")
                break

            else:
                print("  Invalid choice. Enter p, a, q, r, or s.")

    print(f"\n{'='*65}")
    print("  Review queue complete.")
    print(f"{'='*65}\n")


def list_reports():
    """Print a table of all reports (pending, approved, sent)."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT full_name, company_name, company_email, platform,
                   report_generated, report_approved, report_sent, created_at
            FROM meta_leads
            ORDER BY created_at DESC
            LIMIT 50
        """).fetchall()

    if not rows:
        print("\n  No Meta leads in database yet.")
        return

    print(f"\n{'─'*90}")
    print(f"{'Name':<20} {'Company':<22} {'Email':<26} {'Platform':<10} {'Gen':>3} {'App':>3} {'Sent':>4}")
    print(f"{'─'*90}")
    for r in rows:
        print(
            f"{(r['full_name'] or r['company_name'] or '—'):<20} "
            f"{(r['company_name'] or '—'):<22} "
            f"{(r['company_email'] or '—'):<26} "
            f"{(r['platform'] or '—'):<10} "
            f"{'Y' if r['report_generated'] else 'N':>3} "
            f"{'Y' if r['report_approved'] else 'N':>3} "
            f"{'Y' if r['report_sent'] else 'N':>4}"
        )
    print(f"{'─'*90}\n")


def force_send_report(psid: str, dry_run: bool = False):
    """Force-send a specific approved report by PSID."""
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT ml.*, rp.html_path
               FROM meta_leads ml
               LEFT JOIN meta_report_pitches rp ON ml.psid = rp.psid
               WHERE ml.psid = ?""",
            (psid,)
        ).fetchone()

    if not row:
        print(f"No lead found with PSID: {psid}")
        return

    row = dict(row)
    sender = ReportEmailSender()
    ok = sender.send_report(
        to_email=row.get("company_email", ""),
        to_name=row.get("full_name", ""),
        company_name=row.get("company_name", ""),
        html_report_path=row.get("html_path") or row.get("report_path", ""),
        dry_run=dry_run,
    )
    if ok and not dry_run:
        _mark_sent(psid)
        print(f"Report sent to {row.get('company_email')}.")
