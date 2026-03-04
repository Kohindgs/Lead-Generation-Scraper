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
