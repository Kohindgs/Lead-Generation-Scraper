"""
Campaign Orchestrator
======================
Ties together scraping → enrichment → outreach generation → export.
One entry point for running a complete lead generation campaign.
"""
import time
from datetime import datetime
from typing import List, Optional

from src.config import agency, scraper_cfg
from src.enrichment.enricher import LeadEnricher
from src.export.exporter import (
    export_to_excel, export_to_csv, export_to_json,
    export_outreach_messages, generate_html_report,
)
from src.models import Campaign, Lead, LeadSource, OutreachMessage, ScrapingResult
from src.outreach.message_generator import generate_outreach_batch
from src.scrapers.google_scraper import GoogleMapsScraper, GoogleSearchScraper
from src.scrapers.linkedin_scraper import LinkedInScraper, LinkedInSearchURLBuilder
from src.utils.database import init_db, upsert_lead, save_outreach
from src.utils.helpers import get_logger

logger = get_logger(__name__)


class CampaignOrchestrator:
    """
    Runs an end-to-end lead generation campaign:
      1. Scrape leads from LinkedIn / Google Maps / Google Search
      2. Enrich each lead (email, website audit, ICP score)
      3. Generate personalised outreach messages
      4. Export to Excel, CSV, JSON, and HTML report
    """

    def __init__(self):
        init_db()

    def run_linkedin_campaign(
        self,
        campaign_name: str = "LinkedIn Outreach",
        industries: Optional[List[str]] = None,
        titles: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        max_leads: int = 100,
        generate_outreach: bool = True,
    ) -> ScrapingResult:
        """Run a full LinkedIn prospecting campaign."""
        result = ScrapingResult(
            campaign_name=campaign_name,
            source=LeadSource.LINKEDIN,
        )
        start = time.time()

        logger.info("=" * 60)
        logger.info("Starting LinkedIn campaign: %s", campaign_name)
        logger.info("=" * 60)

        # 1. Scrape
        scraper = LinkedInScraper()
        leads = scraper.search_people(
            industries=industries,
            titles=titles,
            locations=locations,
            limit=min(max_leads, scraper_cfg.max_leads_per_run),
        )
        result.total_found = len(leads)
        result.total_scraped = len(leads)

        # 2. Enrich
        enricher = LeadEnricher()
        leads = enricher.enrich(leads, audit_websites=True)
        result.total_enriched = len(leads)

        # Save enriched leads to DB
        for lead in leads:
            upsert_lead(lead)

        # 3. Outreach messages
        messages: List[OutreachMessage] = []
        if generate_outreach:
            messages = generate_outreach_batch(leads, min_score=50)
            result.total_outreach_generated = len(messages)
            for msg in messages:
                save_outreach(msg)

        # 4. Export
        self._export_all(campaign_name, result, leads, messages)

        result.finished_at = datetime.utcnow()
        result.duration_seconds = time.time() - start
        result.leads = leads

        self._print_summary(result)
        return result

    def run_google_maps_campaign(
        self,
        campaign_name: str = "Google Maps Local Business",
        categories: Optional[List[str]] = None,
        location: str = "New York, USA",
        radius_km: int = 50,
        max_leads: int = 100,
        generate_outreach: bool = True,
    ) -> ScrapingResult:
        """Run a Google Maps local business prospecting campaign."""
        result = ScrapingResult(
            campaign_name=campaign_name,
            source=LeadSource.GOOGLE_MAPS,
        )
        start = time.time()

        logger.info("=" * 60)
        logger.info("Starting Google Maps campaign: %s", campaign_name)
        logger.info("Location: %s | Radius: %d km", location, radius_km)
        logger.info("=" * 60)

        # 1. Scrape
        scraper = GoogleMapsScraper()
        leads = scraper.scrape(
            categories=categories,
            location=location,
            radius_km=radius_km,
            limit=min(max_leads, scraper_cfg.max_leads_per_run),
        )
        result.total_found = len(leads)
        result.total_scraped = len(leads)

        # 2. Enrich
        enricher = LeadEnricher()
        leads = enricher.enrich(leads, audit_websites=True)
        result.total_enriched = len(leads)

        for lead in leads:
            upsert_lead(lead)

        # 3. Outreach
        messages: List[OutreachMessage] = []
        if generate_outreach:
            messages = generate_outreach_batch(leads, min_score=40)
            result.total_outreach_generated = len(messages)
            for msg in messages:
                save_outreach(msg)

        # 4. Export
        self._export_all(campaign_name, result, leads, messages)

        result.finished_at = datetime.utcnow()
        result.duration_seconds = time.time() - start
        result.leads = leads

        self._print_summary(result)
        return result

    def run_google_search_campaign(
        self,
        campaign_name: str = "Google Search Outreach",
        queries: Optional[List[str]] = None,
        max_leads: int = 50,
        generate_outreach: bool = True,
    ) -> ScrapingResult:
        """Run a Google Search prospecting campaign."""
        result = ScrapingResult(
            campaign_name=campaign_name,
            source=LeadSource.GOOGLE_SEARCH,
        )
        start = time.time()

        logger.info("=" * 60)
        logger.info("Starting Google Search campaign: %s", campaign_name)
        logger.info("=" * 60)

        scraper = GoogleSearchScraper()
        leads = scraper.scrape(queries=queries, limit=max_leads)
        result.total_found = len(leads)
        result.total_scraped = len(leads)

        enricher = LeadEnricher()
        leads = enricher.enrich(leads, audit_websites=True)
        result.total_enriched = len(leads)

        for lead in leads:
            upsert_lead(lead)

        messages: List[OutreachMessage] = []
        if generate_outreach:
            messages = generate_outreach_batch(leads, min_score=40)
            result.total_outreach_generated = len(messages)
            for msg in messages:
                save_outreach(msg)

        self._export_all(campaign_name, result, leads, messages)

        result.finished_at = datetime.utcnow()
        result.duration_seconds = time.time() - start
        result.leads = leads

        self._print_summary(result)
        return result

    def generate_linkedin_search_urls(self) -> List[dict]:
        """
        Generate ready-to-use LinkedIn search URLs for manual prospecting.
        No authentication required — just open the links in a browser.
        """
        urls = LinkedInSearchURLBuilder.generate_campaign_urls()
        logger.info("Generated %d LinkedIn search URLs.", len(urls))
        return urls

    # ── Private helpers ──────────────────────────────────────────────────────

    def _export_all(
        self,
        campaign_name: str,
        result: ScrapingResult,
        leads: List[Lead],
        messages: List[OutreachMessage],
    ):
        slug = campaign_name.lower().replace(" ", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        if not leads:
            logger.warning("No leads to export.")
            return

        try:
            export_to_excel(leads, f"{slug}_{ts}.xlsx")
        except Exception as exc:
            logger.warning("Excel export failed: %s — falling back to CSV.", exc)
            export_to_csv(leads, f"{slug}_{ts}.csv")

        export_to_json(leads, f"{slug}_{ts}.json")

        if messages:
            export_outreach_messages(leads, messages, f"{slug}_outreach_{ts}.csv")

        try:
            generate_html_report(result, leads, messages)
        except Exception as exc:
            logger.warning("HTML report failed: %s", exc)

    @staticmethod
    def _print_summary(result: ScrapingResult):
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"Campaign Summary: {result.campaign_name}", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green bold")

        table.add_row("Source", result.source.value)
        table.add_row("Leads Found", str(result.total_found))
        table.add_row("Leads Scraped", str(result.total_scraped))
        table.add_row("Leads Enriched", str(result.total_enriched))
        table.add_row("Outreach Messages", str(result.total_outreach_generated))
        icp = sum(1 for l in result.leads if l.icp_match)
        table.add_row("ICP Matches", str(icp))
        avg = (
            sum(l.lead_score for l in result.leads) / len(result.leads)
            if result.leads else 0
        )
        table.add_row("Avg Lead Score", f"{avg:.1f}/100")
        if result.duration_seconds:
            table.add_row("Duration", f"{result.duration_seconds:.0f}s")
        if result.errors:
            table.add_row("Errors", str(len(result.errors)))

        console.print(table)
