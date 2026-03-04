#!/usr/bin/env python3
"""
DGenius Solutions — Lead Generation Scraper
============================================
CLI entry point. Run campaigns from the command line.

Usage examples:
  python main.py linkedin --max-leads 50
  python main.py google-maps --location "Los Angeles, CA" --max-leads 100
  python main.py google-search --max-leads 30
  python main.py all --max-leads 50
  python main.py urls          # Generate LinkedIn search URLs (no login needed)
  python main.py stats         # Show database statistics

  # LeadsGorilla integration:
  python main.py leadsgorilla --file my_leads.csv
  python main.py leadsgorilla --file my_leads.xlsx --send-emails
  python main.py leadsgorilla --file my_leads.csv --dry-run
  python main.py send-emails --dry-run
"""
import argparse
import sys
from pathlib import Path

# Ensure src is importable when running as script
sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(
        description="DGenius Solutions Lead Generation Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Campaign type")

    # ── linkedin ──────────────────────────────────────────────────────────────
    li = subparsers.add_parser("linkedin", help="Scrape LinkedIn for leads")
    li.add_argument("--name", default="LinkedIn Outreach", help="Campaign name")
    li.add_argument("--industries", nargs="*", help="Target industries")
    li.add_argument("--titles", nargs="*", help="Target job titles")
    li.add_argument("--locations", nargs="*", help="Target locations")
    li.add_argument("--max-leads", type=int, default=50, help="Max leads to collect")
    li.add_argument("--no-outreach", action="store_true", help="Skip outreach generation")

    # ── google-maps ───────────────────────────────────────────────────────────
    gm = subparsers.add_parser("google-maps", help="Scrape Google Maps for local businesses")
    gm.add_argument("--name", default="Google Maps Local Business", help="Campaign name")
    gm.add_argument("--location", default="New York, USA", help="Search location")
    gm.add_argument("--radius", type=int, default=50, help="Search radius in km")
    gm.add_argument("--categories", nargs="*", help="Business categories to search")
    gm.add_argument("--max-leads", type=int, default=100, help="Max leads to collect")
    gm.add_argument("--no-outreach", action="store_true")

    # ── google-search ─────────────────────────────────────────────────────────
    gs = subparsers.add_parser("google-search", help="Scrape Google Search results")
    gs.add_argument("--name", default="Google Search Outreach", help="Campaign name")
    gs.add_argument("--queries", nargs="*", help="Custom search queries")
    gs.add_argument("--max-leads", type=int, default=30, help="Max leads")
    gs.add_argument("--no-outreach", action="store_true")

    # ── post-scraper ──────────────────────────────────────────────────────────
    ps = subparsers.add_parser(
        "post-scraper",
        help="Search LinkedIn posts for service requirements (hot inbound leads)"
    )
    ps.add_argument("--max-posts", type=int, default=60,
                    help="Max posts to collect per run (default: 60)")
    ps.add_argument("--send-dms", action="store_true",
                    help="Auto-send DMs to qualified posters")
    ps.add_argument("--dry-run", action="store_true",
                    help="Preview results without saving or sending")
    ps.add_argument("--min-score", type=int, default=45,
                    help="Min opportunity score 0-100 (default: 45)")
    ps.add_argument("--max-age-hours", type=float, default=48.0,
                    help="Max post age in hours (default: 48)")
    ps.add_argument("--services", nargs="*",
                    help="Limit to specific services e.g. SEO 'Web Design & Development'")

    # ── scheduler ─────────────────────────────────────────────────────────────
    sch = subparsers.add_parser(
        "scheduler",
        help="Run post-scraper automatically on a schedule"
    )
    sch.add_argument("action", choices=["start", "status"],
                     help="'start' to run the scheduler, 'status' to view config")
    sch.add_argument("--once", action="store_true",
                     help="Run one scrape pass then stop (no loop)")

    # ── all ───────────────────────────────────────────────────────────────────
    all_p = subparsers.add_parser("all", help="Run all scrapers in sequence")
    all_p.add_argument("--max-leads", type=int, default=50)
    all_p.add_argument("--location", default="New York, USA")
    all_p.add_argument("--no-outreach", action="store_true")

    # ── urls ──────────────────────────────────────────────────────────────────
    subparsers.add_parser("urls", help="Generate LinkedIn search URLs (no login needed)")

    # ── stats ─────────────────────────────────────────────────────────────────
    subparsers.add_parser("stats", help="Show database statistics")

    # ── export ────────────────────────────────────────────────────────────────
    exp = subparsers.add_parser("export", help="Export existing leads from database")
    exp.add_argument("--format", choices=["excel", "csv", "json"], default="excel")
    exp.add_argument("--min-score", type=int, default=0)
    exp.add_argument("--status", help="Filter by status")
    exp.add_argument("--source", help="Filter by source")

    # ── leadsgorilla ──────────────────────────────────────────────────────────
    lg = subparsers.add_parser(
        "leadsgorilla",
        help="Import leads from a LeadsGorilla CSV/Excel export"
    )
    lg.add_argument(
        "--file", required=True,
        help="Path to LeadsGorilla export file (.csv or .xlsx)"
    )
    lg.add_argument(
        "--send-emails", action="store_true",
        help="Send AI-generated outreach emails after importing"
    )
    lg.add_argument(
        "--dry-run", action="store_true",
        help="Preview emails without actually sending"
    )
    lg.add_argument(
        "--export-for-lg", action="store_true",
        help="Export AI messages back to CSV for LeadsGorilla's emailer"
    )
    lg.add_argument("--min-score", type=int, default=40,
                    help="Min lead score for outreach (default: 40)")
    lg.add_argument("--no-outreach", action="store_true",
                    help="Skip AI outreach message generation")

    # ── send-emails ───────────────────────────────────────────────────────────
    se = subparsers.add_parser(
        "send-emails",
        help="Send pending outreach emails from database"
    )
    se.add_argument(
        "--dry-run", action="store_true",
        help="Preview emails without sending"
    )
    se.add_argument("--min-score", type=int, default=50)
    se.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # ── Execute ───────────────────────────────────────────────────────────────

    if args.command == "stats":
        _show_stats()

    elif args.command == "urls":
        _show_linkedin_urls()

    elif args.command == "export":
        _export_db_leads(
            fmt=args.format,
            min_score=args.min_score,
            status=args.status,
            source=args.source,
        )

    elif args.command == "linkedin":
        from src.orchestrator import CampaignOrchestrator
        orch = CampaignOrchestrator()
        orch.run_linkedin_campaign(
            campaign_name=args.name,
            industries=args.industries,
            titles=args.titles,
            locations=args.locations,
            max_leads=args.max_leads,
            generate_outreach=not args.no_outreach,
        )

    elif args.command == "google-maps":
        from src.orchestrator import CampaignOrchestrator
        orch = CampaignOrchestrator()
        orch.run_google_maps_campaign(
            campaign_name=args.name,
            categories=args.categories,
            location=args.location,
            radius_km=args.radius,
            max_leads=args.max_leads,
            generate_outreach=not args.no_outreach,
        )

    elif args.command == "google-search":
        from src.orchestrator import CampaignOrchestrator
        orch = CampaignOrchestrator()
        orch.run_google_search_campaign(
            campaign_name=args.name,
            queries=args.queries,
            max_leads=args.max_leads,
            generate_outreach=not args.no_outreach,
        )

    elif args.command == "post-scraper":
        _run_post_scraper(args)

    elif args.command == "scheduler":
        _run_scheduler(args)

    elif args.command == "leadsgorilla":
        _run_leadsgorilla(args)

    elif args.command == "send-emails":
        _send_pending_emails(args)

    elif args.command == "all":
        from src.orchestrator import CampaignOrchestrator
        orch = CampaignOrchestrator()
        print("\n── Running Google Maps Campaign ──")
        orch.run_google_maps_campaign(
            campaign_name="All Sources — Google Maps",
            location=args.location,
            max_leads=args.max_leads,
            generate_outreach=not args.no_outreach,
        )
        print("\n── Running LinkedIn Campaign ──")
        orch.run_linkedin_campaign(
            campaign_name="All Sources — LinkedIn",
            max_leads=args.max_leads,
            generate_outreach=not args.no_outreach,
        )
        print("\n── Running Google Search Campaign ──")
        orch.run_google_search_campaign(
            campaign_name="All Sources — Google Search",
            max_leads=args.max_leads // 2,
            generate_outreach=not args.no_outreach,
        )


def _run_post_scraper(args):
    """Run the LinkedIn service-requirement post scraper once."""
    from src.utils.database import init_db
    from src.scrapers.linkedin_post_scraper import LinkedInPostScraper
    from src.export.exporter import export_service_posts

    init_db()

    scraper = LinkedInPostScraper()
    posts = scraper.run(
        max_posts=args.max_posts,
        send_dms=args.send_dms,
        dry_run=args.dry_run,
        min_score=args.min_score,
        max_post_age_hours=args.max_age_hours,
        services_filter=args.services or None,
    )

    if posts and not args.dry_run:
        export_service_posts(posts, "service_requests_latest.xlsx")
        print(f"\nResults exported to: exports/service_requests_latest.xlsx")

    print(f"\n{'='*55}")
    print(f"  Post Scraper Complete")
    print(f"  Qualified posts  : {len(posts)}")
    hot = sum(1 for p in posts if p.opportunity_score >= 70)
    warm = sum(1 for p in posts if 45 <= p.opportunity_score < 70)
    print(f"  Hot (score≥70)   : {hot}")
    print(f"  Warm (score≥45)  : {warm}")
    dms_sent = sum(1 for p in posts if p.dm_sent)
    if dms_sent:
        print(f"  DMs sent         : {dms_sent}")
    print(f"{'='*55}")


def _run_scheduler(args):
    """Start the automated scheduler."""
    from src.scheduler import Scheduler
    scheduler = Scheduler()
    if args.action == "status":
        scheduler.show_status()
    elif args.action == "start":
        if args.once:
            scheduler.run_once()
        else:
            scheduler.start(run_immediately=True)


def _run_leadsgorilla(args):
    """Import LeadsGorilla export, enrich, generate outreach, optionally send."""
    from src.scrapers.leadsgorilla_importer import import_leads
    from src.enrichment.enricher import LeadEnricher
    from src.outreach.message_generator import generate_outreach_batch
    from src.outreach.email_sender import EmailSender, export_for_leadsgorilla_emailer
    from src.export.exporter import export_to_excel, export_outreach_messages
    from src.utils.database import init_db, upsert_lead

    init_db()

    # 1. Import from LeadsGorilla file
    print(f"\nImporting leads from: {args.file}")
    leads = import_leads(args.file)
    if not leads:
        print("No leads imported. Check the file path and format.")
        return

    print(f"Imported {len(leads)} leads.")

    # 2. Enrich + score
    print("Enriching leads (website audit + ICP scoring)…")
    enricher = LeadEnricher()
    leads = enricher.enrich(leads, audit_websites=True)
    for lead in leads:
        upsert_lead(lead)

    icp_count = sum(1 for l in leads if l.icp_match)
    print(f"Enrichment done. ICP matches: {icp_count}/{len(leads)}")

    # 3. Export enriched leads
    export_to_excel(leads, f"leadsgorilla_enriched.xlsx")
    print("Enriched leads exported to: exports/leadsgorilla_enriched.xlsx")

    # 4. Generate outreach messages
    messages = []
    if not args.no_outreach:
        print(f"Generating AI outreach messages (score ≥ {args.min_score})…")
        messages = generate_outreach_batch(leads, min_score=args.min_score)
        print(f"Generated {len(messages)} outreach messages.")

        if messages:
            export_outreach_messages(leads, messages, "leadsgorilla_outreach.csv")
            print("Outreach messages saved to: exports/leadsgorilla_outreach.csv")

    # 5. Export for LeadsGorilla emailer (if requested)
    if args.export_for_lg and messages:
        path = export_for_leadsgorilla_emailer(leads, messages)
        print(f"\nLeadsGorilla-ready email CSV exported to: {path}")
        print("Import this file into LeadsGorilla's Email Campaign feature.")

    # 6. Send emails via SMTP (if requested)
    if args.send_emails or args.dry_run:
        if not messages:
            print("No outreach messages generated — cannot send emails.")
            return
        sender = EmailSender()
        if args.send_emails and not args.dry_run:
            print("\nTesting SMTP connection…")
            if not sender.test_connection():
                print("SMTP connection failed. Check SMTP_USER and SMTP_PASS in .env")
                return
        stats = sender.send_campaign(leads, messages, dry_run=args.dry_run)
        print(
            f"\nEmail results — "
            f"Sent: {stats['sent']} | Skipped: {stats['skipped']} | Failed: {stats['failed']}"
        )

    # Summary
    print(f"\n{'='*55}")
    print(f"  LeadsGorilla Campaign Complete")
    print(f"  Leads imported   : {len(leads)}")
    print(f"  ICP matches      : {icp_count}")
    print(f"  Messages created : {len(messages)}")
    print(f"  Exports in       : exports/")
    print(f"{'='*55}")


def _send_pending_emails(args):
    """Send emails for leads already in the database."""
    import json
    from src.utils.database import init_db, get_leads, get_connection
    from src.models import Lead, OutreachMessage, OutreachChannel
    from src.outreach.email_sender import EmailSender
    from src.outreach.message_generator import generate_outreach_batch

    init_db()

    # Load leads from DB
    rows = get_leads(status="new", min_score=args.min_score, limit=args.limit)
    if not rows:
        print("No new leads found in database matching filters.")
        return

    leads = []
    for row in rows:
        lead = Lead(
            id=row["id"],
            full_name=row.get("full_name", ""),
            first_name=row.get("first_name", ""),
            last_name=row.get("last_name", ""),
            title=row.get("title", ""),
            company_name=row.get("company_name", ""),
            company_website=row.get("company_website"),
            industry=row.get("industry", ""),
            email=row.get("email"),
            phone=row.get("phone"),
            lead_score=row.get("lead_score", 0),
            icp_match=bool(row.get("icp_match", 0)),
            pain_points=json.loads(row.get("pain_points") or "[]"),
            services_needed=json.loads(row.get("services_needed") or "[]"),
        )
        leads.append(lead)

    # Only leads with emails
    leads_with_email = [l for l in leads if l.email]
    print(f"Found {len(leads_with_email)} leads with emails (score ≥ {args.min_score}).")

    if not leads_with_email:
        print("No leads with emails found. Run enrichment first.")
        return

    # Generate messages
    messages = generate_outreach_batch(leads_with_email, min_score=args.min_score)
    print(f"Generated {len(messages)} email messages.")

    sender = EmailSender()
    stats = sender.send_campaign(leads_with_email, messages, dry_run=args.dry_run)
    print(
        f"\nDone — Sent: {stats['sent']} | Skipped: {stats['skipped']} | Failed: {stats['failed']}"
    )


def _show_stats():
    from src.utils.database import init_db, get_stats
    from rich.console import Console
    from rich.table import Table
    init_db()
    stats = get_stats()
    console = Console()

    console.print("\n[bold cyan]DGenius Lead Database Stats[/bold cyan]\n")
    console.print(f"  Total Leads : [bold green]{stats['total_leads']}[/bold green]")
    console.print(f"  Avg Score   : [bold yellow]{stats['avg_score']}[/bold yellow]\n")

    t = Table(title="By Status")
    t.add_column("Status"); t.add_column("Count", style="green")
    for status, cnt in stats["by_status"].items():
        t.add_row(status, str(cnt))
    console.print(t)

    t2 = Table(title="By Source")
    t2.add_column("Source"); t2.add_column("Count", style="green")
    for src, cnt in stats["by_source"].items():
        t2.add_row(src, str(cnt))
    console.print(t2)

    t3 = Table(title="Top Industries")
    t3.add_column("Industry"); t3.add_column("Leads", style="green")
    for ind, cnt in stats["top_industries"]:
        t3.add_row(ind or "Unknown", str(cnt))
    console.print(t3)


def _show_linkedin_urls():
    from src.orchestrator import CampaignOrchestrator
    from src.utils.database import init_db
    init_db()
    orch = CampaignOrchestrator()
    urls = orch.generate_linkedin_search_urls()

    print(f"\n{'='*70}")
    print(f"  DGenius Solutions — LinkedIn Search URLs")
    print(f"  Open these in your browser to find leads (no API needed)")
    print(f"{'='*70}\n")
    for i, u in enumerate(urls, 1):
        print(f"[{i}] {u['name']}")
        print(f"    Titles    : {', '.join(u['target_titles'])}")
        print(f"    Industry  : {u['target_industry']}")
        print(f"    URL       : {u['url']}")
        print()

    # Save to file
    from pathlib import Path
    out = Path("exports/linkedin_search_urls.txt")
    out.parent.mkdir(exist_ok=True)
    with open(out, "w") as f:
        for i, u in enumerate(urls, 1):
            f.write(f"[{i}] {u['name']}\n")
            f.write(f"    {u['description']}\n")
            f.write(f"    {u['url']}\n\n")
    print(f"Saved to: {out}")


def _export_db_leads(fmt: str, min_score: int, status: str, source: str):
    from src.utils.database import init_db, get_leads
    from src.models import Lead
    init_db()
    rows = get_leads(status=status, source=source, min_score=min_score, limit=5000)

    leads = []
    for row in rows:
        import json
        lead = Lead(
            id=row["id"],
            full_name=row.get("full_name", ""),
            first_name=row.get("first_name", ""),
            last_name=row.get("last_name", ""),
            title=row.get("title", ""),
            company_name=row.get("company_name", ""),
            company_website=row.get("company_website"),
            industry=row.get("industry", ""),
            email=row.get("email"),
            phone=row.get("phone"),
            linkedin_url=row.get("linkedin_url"),
            city=row.get("city", ""),
            country=row.get("country", ""),
            lead_score=row.get("lead_score", 0),
            icp_match=bool(row.get("icp_match", 0)),
            pain_points=json.loads(row.get("pain_points") or "[]"),
            services_needed=json.loads(row.get("services_needed") or "[]"),
        )
        leads.append(lead)

    if not leads:
        print("No leads found with those filters.")
        return

    from src.export.exporter import export_to_excel, export_to_csv, export_to_json
    if fmt == "excel":
        path = export_to_excel(leads)
    elif fmt == "csv":
        path = export_to_csv(leads)
    else:
        path = export_to_json(leads)

    print(f"Exported {len(leads)} leads → {path}")


if __name__ == "__main__":
    main()
