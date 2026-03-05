"""
AI Content Campaign Manager
============================
The top-level orchestrator for the Meta "AI Content" lead-generation campaign.

Full flow:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Meta Ad / Post Comment  →  "AI Content" detected              │
  │           ↓                                                     │
  │  Auto DM sent with Google Form link                            │
  │           ↓                                                     │
  │  Prospect fills form (Name, Phone, Email, Company, Website)    │
  │           ↓                                                     │
  │  Google Apps Script webhooks form data → our server            │
  │           ↓                                                     │
  │  Claude AI generates Brand Audit Report                        │
  │           ↓                                                     │
  │  Admin reviews & approves report (CLI)                         │
  │           ↓                                                     │
  │  Report sent via Gmail (Google Business) to lead's email       │
  │           ↓                                                     │
  │  Lead + status logged to Google Sheets                         │
  └─────────────────────────────────────────────────────────────────┘

CLI commands (see main.py):
  python main.py meta-reply scan          # one-time scan + DM
  python main.py meta-reply scan --watch  # continuous polling loop
  python main.py meta-reply review        # interactive report approval
  python main.py meta-reply list          # list all leads/reports
  python main.py meta-reply webhook       # start form webhook server
  python main.py meta-reply webhook --port 8080
  python main.py meta-reply send --psid X # force-send a report
  python main.py meta-reply sync-sheets   # sync all leads to Google Sheets
  python main.py meta-reply stats         # show campaign statistics
"""

import time
from datetime import datetime
from typing import Optional

from src.meta.comment_monitor import CommentMonitor
from src.meta.dm_sender import DMSender
from src.utils.helpers import get_logger

logger = get_logger(__name__)


class MetaCampaignManager:
    """
    Orchestrates the comment scan → DM send pipeline.
    Report generation is handled asynchronously by the webhook handler.
    """

    def __init__(self):
        self.monitor = CommentMonitor()
        self.sender = DMSender()

    def run_scan(
        self,
        max_posts: int = 25,
        send_dms: bool = True,
        dry_run: bool = False,
    ) -> dict:
        """
        Single scan pass: find new 'AI Content' comments and DM the authors.
        Returns stats dict.
        """
        stats = {
            "scan_time": datetime.now().isoformat(),
            "new_comments": 0,
            "dms_sent": 0,
            "dms_failed": 0,
        }

        logger.info("Starting Meta 'AI Content' scan...")
        comments = self.monitor.scan_all(max_posts=max_posts)
        stats["new_comments"] = len(comments)

        if not comments:
            logger.info("No new 'AI Content' comments found.")
            return stats

        logger.info("Found %d new comment(s). Sending DMs...", len(comments))

        if send_dms:
            dm_stats = self.sender.send_batch(comments, dry_run=dry_run)
            stats["dms_sent"] = dm_stats["sent"]
            stats["dms_failed"] = dm_stats["failed"]
        else:
            logger.info("DMs disabled (send_dms=False). Comments logged only.")

        return stats

    def run_watch(
        self,
        interval_minutes: int = 15,
        max_posts: int = 25,
        send_dms: bool = True,
        dry_run: bool = False,
    ):
        """
        Continuous polling loop — scans every interval_minutes.
        Press Ctrl+C to stop.
        """
        print(f"\n  Watching for 'AI Content' comments every {interval_minutes} min.")
        print(f"  Press Ctrl+C to stop.\n")

        try:
            while True:
                stats = self.run_scan(
                    max_posts=max_posts,
                    send_dms=send_dms,
                    dry_run=dry_run,
                )
                _print_scan_summary(stats)
                logger.info(
                    "Next scan in %d minutes...", interval_minutes
                )
                time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            print("\n  Watch loop stopped.")

    def show_stats(self):
        """Print campaign statistics from the database."""
        import sqlite3
        from src.config import db_cfg

        conn = sqlite3.connect(db_cfg.path)
        conn.row_factory = sqlite3.Row

        try:
            # Total processed comments
            total_comments = conn.execute(
                "SELECT COUNT(*) as c FROM meta_processed_comments"
            ).fetchone()["c"]

            dms_sent = conn.execute(
                "SELECT COUNT(*) as c FROM meta_processed_comments WHERE dm_sent = 1"
            ).fetchone()["c"]

            total_leads = conn.execute(
                "SELECT COUNT(*) as c FROM meta_leads"
            ).fetchone()["c"]

            form_filled = conn.execute(
                "SELECT COUNT(*) as c FROM meta_leads WHERE company_email IS NOT NULL AND company_email != ''"
            ).fetchone()["c"]

            reports_generated = conn.execute(
                "SELECT COUNT(*) as c FROM meta_leads WHERE report_generated = 1"
            ).fetchone()["c"]

            reports_approved = conn.execute(
                "SELECT COUNT(*) as c FROM meta_leads WHERE report_approved = 1"
            ).fetchone()["c"]

            reports_sent = conn.execute(
                "SELECT COUNT(*) as c FROM meta_leads WHERE report_sent = 1"
            ).fetchone()["c"]

            # Platform breakdown
            by_platform = conn.execute("""
                SELECT platform, COUNT(*) as c
                FROM meta_leads GROUP BY platform
            """).fetchall()

        except sqlite3.OperationalError:
            print("\n  No Meta campaign data found. Run a scan first.")
            conn.close()
            return
        finally:
            conn.close()

        print(f"\n{'='*55}")
        print(f"  AI Content Campaign — Statistics")
        print(f"{'='*55}")
        print(f"  Comments processed : {total_comments}")
        print(f"  DMs sent           : {dms_sent}")
        print(f"  Leads created      : {total_leads}")
        print(f"  Form completions   : {form_filled}")
        print(f"  Reports generated  : {reports_generated}")
        print(f"  Reports approved   : {reports_approved}")
        print(f"  Reports sent       : {reports_sent}")
        if total_leads:
            conversion = round(form_filled / total_leads * 100, 1)
            print(f"\n  DM → Form rate     : {conversion}%")
        print(f"\n  By platform:")
        for row in by_platform:
            print(f"    {row['platform']:<12}: {row['c']}")
        print(f"{'='*55}\n")


def _print_scan_summary(stats: dict):
    now = stats.get("scan_time", "")[:19].replace("T", " ")
    print(f"\n  [{now}] Scan complete")
    print(f"    New comments found : {stats['new_comments']}")
    print(f"    DMs sent           : {stats['dms_sent']}")
    if stats["dms_failed"]:
        print(f"    DMs failed         : {stats['dms_failed']}")
