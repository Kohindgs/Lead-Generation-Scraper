"""
Automation Scheduler
=====================
Runs the LinkedIn post scraper + DM sender automatically on a schedule.

Uses APScheduler (lightweight, no Redis/Celery needed).

Schedule (configurable via .env):
  - Every N hours: search for new service-request posts
  - Send DMs immediately for hot leads (score ≥ 70)
  - Send DMs in next batch for warm leads (score ≥ 45)
  - Daily digest: export new leads to Excel

Run:
  python main.py scheduler start            # run forever
  python main.py scheduler start --once     # run once now, then stop
  python main.py scheduler status           # show schedule
"""
from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from src.utils.helpers import get_logger
from src.utils.database import init_db

logger = get_logger(__name__)

# ── Schedule config (all overridable via .env) ────────────────────────────────
POST_SCRAPE_INTERVAL_HOURS = float(os.getenv("POST_SCRAPE_INTERVAL_HOURS", "4"))
MAX_POSTS_PER_RUN          = int(os.getenv("MAX_POSTS_PER_RUN", "60"))
MIN_SCORE_TO_DM            = int(os.getenv("MIN_SCORE_TO_DM", "55"))
AUTO_SEND_DMS              = os.getenv("AUTO_SEND_DMS", "false").lower() == "true"
MAX_POST_AGE_HOURS         = float(os.getenv("MAX_POST_AGE_HOURS", "48"))
DAILY_EXPORT_HOUR          = int(os.getenv("DAILY_EXPORT_HOUR", "8"))  # 8 AM


def _run_post_scrape_job(send_dms: bool = False):
    """The main scheduled job — scrapes posts and optionally sends DMs."""
    logger.info("═" * 55)
    logger.info("SCHEDULED RUN — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("═" * 55)

    from src.scrapers.linkedin_post_scraper import LinkedInPostScraper
    from src.export.exporter import export_service_posts

    scraper = LinkedInPostScraper()
    posts = scraper.run(
        max_posts=MAX_POSTS_PER_RUN,
        send_dms=send_dms and AUTO_SEND_DMS,
        dry_run=False,
        min_score=MIN_SCORE_TO_DM,
        max_post_age_hours=MAX_POST_AGE_HOURS,
    )

    if posts:
        # Export to Excel after each run
        try:
            export_service_posts(posts, "service_requests_latest.xlsx")
            logger.info("Exported %d posts to exports/service_requests_latest.xlsx", len(posts))
        except Exception as exc:
            logger.warning("Export failed: %s", exc)

    logger.info(
        "Run complete. Found %d qualified posts (DMs sent: %s).",
        len(posts), "yes" if (send_dms and AUTO_SEND_DMS) else "no"
    )
    return posts


def _run_daily_export_job():
    """Export all leads + service posts accumulated today."""
    logger.info("Daily export job running …")
    from src.utils.database import get_leads_today, get_service_posts_today
    from src.export.exporter import export_to_excel, export_service_posts

    leads_today = get_leads_today()
    posts_today = get_service_posts_today()

    date_str = datetime.now().strftime("%Y-%m-%d")
    if leads_today:
        export_to_excel(leads_today, f"daily_leads_{date_str}.xlsx")
        logger.info("Daily export: %d leads → exports/daily_leads_%s.xlsx",
                    len(leads_today), date_str)
    if posts_today:
        export_service_posts(posts_today, f"daily_posts_{date_str}.xlsx")
        logger.info("Daily export: %d posts → exports/daily_posts_%s.xlsx",
                    len(posts_today), date_str)


class Scheduler:
    """APScheduler wrapper for the automation loop."""

    def __init__(self):
        self._scheduler = None

    def _build_scheduler(self):
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.triggers.interval import IntervalTrigger
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logger.error(
                "APScheduler not installed. Run: pip install apscheduler"
            )
            sys.exit(1)

        scheduler = BlockingScheduler(timezone="UTC")

        # Job 1: Post scraper — every N hours
        scheduler.add_job(
            func=_run_post_scrape_job,
            trigger=IntervalTrigger(hours=POST_SCRAPE_INTERVAL_HOURS),
            id="post_scraper",
            name=f"LinkedIn Post Scraper (every {POST_SCRAPE_INTERVAL_HOURS}h)",
            kwargs={"send_dms": AUTO_SEND_DMS},
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=600,
        )

        # Job 2: Daily export — fixed time each day
        scheduler.add_job(
            func=_run_daily_export_job,
            trigger=CronTrigger(hour=DAILY_EXPORT_HOUR, minute=0),
            id="daily_export",
            name=f"Daily Lead Export ({DAILY_EXPORT_HOUR:02d}:00 UTC)",
            replace_existing=True,
            max_instances=1,
        )

        self._scheduler = scheduler
        return scheduler

    def start(self, run_immediately: bool = True):
        """
        Start the scheduler. Blocks indefinitely.

        Args:
            run_immediately: Run the scrape job once right now before
                             entering the schedule loop.
        """
        init_db()

        logger.info("Starting LinkedIn Post Scraper Scheduler")
        logger.info("  Scrape interval : every %.0f hours", POST_SCRAPE_INTERVAL_HOURS)
        logger.info("  Max posts/run   : %d", MAX_POSTS_PER_RUN)
        logger.info("  Min DM score    : %d", MIN_SCORE_TO_DM)
        logger.info("  Auto-send DMs   : %s", AUTO_SEND_DMS)
        logger.info("  Daily export    : %02d:00 UTC", DAILY_EXPORT_HOUR)
        logger.info("  Press Ctrl+C to stop.")
        logger.info("─" * 55)

        scheduler = self._build_scheduler()

        # Graceful shutdown on SIGINT / SIGTERM
        def _shutdown(signum, frame):
            logger.info("Shutting down scheduler …")
            if self._scheduler:
                self._scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        # Run immediately before entering loop
        if run_immediately:
            logger.info("Running immediate scrape …")
            try:
                _run_post_scrape_job(send_dms=AUTO_SEND_DMS)
            except Exception as exc:
                logger.error("Immediate run failed: %s", exc)

        logger.info("Scheduler active. Next scrape in %.0f hours.", POST_SCRAPE_INTERVAL_HOURS)
        scheduler.start()

    def run_once(self):
        """Run the scrape job exactly once (no loop)."""
        init_db()
        logger.info("Running single post-scrape pass …")
        posts = _run_post_scrape_job(send_dms=AUTO_SEND_DMS)
        logger.info("Done. %d qualified posts found.", len(posts))
        return posts

    def show_status(self):
        """Print current schedule configuration."""
        print(f"\n{'─'*55}")
        print("  LinkedIn Post Scraper — Schedule Config")
        print(f"{'─'*55}")
        print(f"  Scrape interval  : every {POST_SCRAPE_INTERVAL_HOURS:.0f} hours")
        print(f"  Max posts/run    : {MAX_POSTS_PER_RUN}")
        print(f"  Min score to DM  : {MIN_SCORE_TO_DM}")
        print(f"  Auto-send DMs    : {'YES ✓' if AUTO_SEND_DMS else 'NO (set AUTO_SEND_DMS=true in .env)'}")
        print(f"  Max post age     : {MAX_POST_AGE_HOURS:.0f} hours")
        print(f"  Daily export at  : {DAILY_EXPORT_HOUR:02d}:00 UTC")
        print(f"{'─'*55}")
        print(f"\n  To start:  python main.py scheduler start")
        print(f"  Once only: python main.py scheduler start --once")
        print(f"{'─'*55}\n")
