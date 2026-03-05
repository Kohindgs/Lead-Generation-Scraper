"""
Meta Setup Helper
=================
Interactive CLI wizard that validates a Page Access Token and
auto-discovers the Page ID (if not known) and Instagram Business
Account ID, then prints a ready-to-paste .env snippet.

Usage:
  python main.py meta-reply setup
  python main.py meta-reply setup --token EAAxxxxxxxxx
  python main.py meta-reply setup --token EAAxxxxxxxxx --page-id 123456789
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import requests

META_GRAPH_BASE = "https://graph.facebook.com/v19.0"


class MetaAPIError(Exception):
    pass


def _graph_get(path: str, token: str, params: dict | None = None) -> dict:
    url = f"{META_GRAPH_BASE}/{path.lstrip('/')}"
    params = params or {}
    params["access_token"] = token
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response else str(exc)
        raise MetaAPIError(f"Graph API error: {body}") from exc
    except requests.RequestException as exc:
        raise MetaAPIError(f"Network error: {exc}") from exc


def _verify_token(token: str) -> dict:
    """
    Call /me to verify the token and return basic page info.
    Returns dict with 'id' and 'name'.
    """
    return _graph_get("me", token, {"fields": "id,name"})


def _get_managed_pages(token: str) -> list[dict]:
    """Return pages the token has access to (for user tokens)."""
    try:
        data = _graph_get("me/accounts", token, {"fields": "id,name,access_token"})
        return data.get("data", [])
    except MetaAPIError:
        return []


def _get_instagram_account(page_id: str, token: str) -> Optional[dict]:
    """
    Return the Instagram Business Account connected to a Facebook Page.
    Returns dict with 'id' and 'name', or None.
    """
    try:
        data = _graph_get(
            f"{page_id}",
            token,
            {"fields": "instagram_business_account{id,name,username}"},
        )
        ig = data.get("instagram_business_account")
        return ig  # may be None if no IG account linked
    except MetaAPIError:
        return None


def _print_separator(char: str = "─", width: int = 65):
    print(char * width)


def run_setup(token: str = "", page_id: str = ""):
    """
    Interactive setup wizard.
    """
    print()
    _print_separator("═")
    print("  DGenius Solutions — Meta AI Content Reply System")
    print("  Credential Setup Wizard")
    _print_separator("═")
    print()

    # ── Step 1: Get token ──────────────────────────────────────────────────────
    if not token:
        token = os.getenv("META_PAGE_ACCESS_TOKEN", "").strip()
    if not token:
        token = input(
            "  Paste your Page Access Token (from Meta for Developers):\n  > "
        ).strip()

    if not token:
        print("\n  [ERROR] No token provided. Aborting.")
        sys.exit(1)

    print("\n  Verifying token with Meta Graph API...")

    # ── Step 2: Verify token ───────────────────────────────────────────────────
    try:
        me = _verify_token(token)
    except MetaAPIError as exc:
        print(f"\n  [ERROR] Token verification failed: {exc}")
        print("  Check that your token is valid and hasn't expired.")
        sys.exit(1)

    token_page_id = me.get("id", "")
    token_page_name = me.get("name", "")

    print(f"  Token valid! Identity: {token_page_name} (ID: {token_page_id})")

    # ── Step 3: Resolve page ID ────────────────────────────────────────────────
    if not page_id:
        page_id = os.getenv("META_PAGE_ID", "").strip()

    if not page_id:
        # If the token is a Page token, the /me response IS the page.
        # If it's a User token, list available pages.
        pages = _get_managed_pages(token)
        if pages:
            print(f"\n  Found {len(pages)} page(s) accessible with this token:")
            for i, p in enumerate(pages, 1):
                print(f"    [{i}] {p['name']} — ID: {p['id']}")
            if len(pages) == 1:
                page_id = pages[0]["id"]
                print(f"\n  Using page: {pages[0]['name']} (ID: {page_id})")
            else:
                choice = input(
                    f"\n  Enter the number of the page to use [1-{len(pages)}]: "
                ).strip()
                try:
                    page_id = pages[int(choice) - 1]["id"]
                    token = pages[int(choice) - 1].get("access_token", token)
                except (ValueError, IndexError):
                    print("  Invalid choice. Using token identity as page ID.")
                    page_id = token_page_id
        else:
            # Page token — /me is the page itself
            page_id = token_page_id
            print(f"  Using page ID from token: {page_id}")

    if not page_id:
        page_id = input(
            "\n  Enter your Facebook Page ID (found in Page → About):\n  > "
        ).strip()

    print(f"\n  Page ID: {page_id}")

    # ── Step 4: Find Instagram Account ID ─────────────────────────────────────
    print("\n  Looking up connected Instagram Business Account...")
    ig = _get_instagram_account(page_id, token)
    ig_account_id = ""

    if ig:
        ig_account_id = ig.get("id", "")
        ig_name = ig.get("name") or ig.get("username", "")
        print(f"  Instagram account found: @{ig_name} (ID: {ig_account_id})")
    else:
        print(
            "  No Instagram Business Account found connected to this page.\n"
            "  You can still run the Facebook-only campaign.\n"
            "  To link Instagram: Meta Business Suite → Settings → Accounts → Instagram."
        )
        ig_account_id = input(
            "\n  Enter Instagram Account ID manually (or press Enter to skip):\n  > "
        ).strip()

    # ── Step 5: Print .env snippet ─────────────────────────────────────────────
    print()
    _print_separator("═")
    print("  Your .env configuration:")
    _print_separator("═")
    print()
    print("  Copy and paste the following into your .env file:\n")
    print(f"META_PAGE_ACCESS_TOKEN=\"{token}\"")
    print(f"META_PAGE_ID=\"{page_id}\"")
    if ig_account_id:
        print(f"META_IG_ACCOUNT_ID=\"{ig_account_id}\"")
    else:
        print('META_IG_ACCOUNT_ID=""   # Not configured')

    print()
    _print_separator("─")
    print()
    print("  Next steps:")
    print("  1. Add the above to your .env file")
    print("  2. Set META_GOOGLE_FORM_URL (see docs/GOOGLE_FORM_SETUP.md)")
    print("  3. Set META_SMTP_USER and META_SMTP_PASS for sending reports")
    print("  4. Run: python main.py meta-reply scan --dry-run")
    print("         (tests comment detection without sending DMs)")
    print()
    _print_separator("═")
    print()

    return {
        "token": token,
        "page_id": page_id,
        "ig_account_id": ig_account_id,
        "page_name": token_page_name,
    }
