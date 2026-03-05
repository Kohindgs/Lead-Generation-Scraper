"""
Google Sheets Lead Logger
==========================
Logs every Meta lead (comment + form submission + report status) to a
Google Sheet for easy tracking by the DGenius team.

The Sheet has two tabs:
  • "Leads"   — one row per lead, all details + status
  • "Reports" — tracks report generation, approval, and send timestamps

Authentication:
  Uses a Google Service Account JSON key.
  Share the Sheet with the service account email (Editor access).

Setup:
  1. Create a Google Cloud project
  2. Enable the Google Sheets API
  3. Create a Service Account → download JSON key
  4. Set GOOGLE_SERVICE_ACCOUNT_JSON in .env (path to key file)
  5. Set GOOGLE_SHEET_ID in .env (from the Sheet URL)
  6. Share the Sheet with the service account email
  7. Run: pip install gspread google-auth

Required install:
  pip install gspread google-auth
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

from src.config import meta_cfg, db_cfg
from src.utils.helpers import get_logger

logger = get_logger(__name__)


def _get_gspread_client():
    """Authenticate and return a gspread client using a Service Account."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error(
            "gspread / google-auth not installed. "
            "Run: pip install gspread google-auth"
        )
        return None

    key_path = meta_cfg.google_service_account_json
    if not key_path or not os.path.exists(key_path):
        logger.error(
            "GOOGLE_SERVICE_ACCOUNT_JSON not set or file not found. "
            "Cannot write to Google Sheets."
        )
        return None

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(key_path, scopes=scopes)
    return gspread.authorize(creds)


def _ensure_leads_headers(ws) -> None:
    """Write headers to the Leads sheet if not already present."""
    headers = [
        "PSID", "Commenter Name", "Platform", "Comment Text",
        "Full Name", "Phone", "Company Email", "Company Name", "Website",
        "Report Generated", "Report Approved", "Report Sent",
        "Created At", "Updated At",
    ]
    first_row = ws.row_values(1)
    if not first_row or first_row[0] != "PSID":
        ws.insert_row(headers, index=1)


def _ensure_reports_headers(ws) -> None:
    """Write headers to the Reports sheet if not already present."""
    headers = [
        "PSID", "Company Name", "Company Email",
        "Top Services", "Pitch Angle", "Budget Tier",
        "Opening Line", "Report Path",
        "Generated At",
    ]
    first_row = ws.row_values(1)
    if not first_row or first_row[0] != "PSID":
        ws.insert_row(headers, index=1)


class SheetsLogger:
    """
    Appends/updates lead data in Google Sheets.
    Gracefully no-ops if credentials are not configured.
    """

    def __init__(self):
        self.sheet_id = meta_cfg.google_sheet_id
        self.client = None
        self._leads_ws = None
        self._reports_ws = None

        if not self.sheet_id:
            logger.info("GOOGLE_SHEET_ID not set — Sheets logging disabled.")
            return

        self.client = _get_gspread_client()

    def _get_sheets(self):
        if not self.client:
            return None, None
        try:
            sh = self.client.open_by_key(self.sheet_id)

            # Leads tab
            try:
                leads_ws = sh.worksheet("Leads")
            except Exception:
                leads_ws = sh.add_worksheet(title="Leads", rows=1000, cols=20)
            _ensure_leads_headers(leads_ws)

            # Reports tab
            try:
                reports_ws = sh.worksheet("Reports")
            except Exception:
                reports_ws = sh.add_worksheet(title="Reports", rows=1000, cols=20)
            _ensure_reports_headers(reports_ws)

            return leads_ws, reports_ws
        except Exception as exc:
            logger.error("Failed to open Google Sheet: %s", exc)
            return None, None

    def log_lead(self, psid: str) -> bool:
        """
        Read lead data from SQLite and append/update the Google Sheet.
        Call this after a form submission is received.
        """
        if not self.client:
            return False

        lead = _get_lead_from_db(psid)
        if not lead:
            logger.warning("No lead found for PSID %s — cannot log to Sheets.", psid)
            return False

        leads_ws, _ = self._get_sheets()
        if not leads_ws:
            return False

        row = [
            lead.get("psid", ""),
            lead.get("commenter_name", ""),
            lead.get("platform", ""),
            lead.get("comment_text", ""),
            lead.get("full_name", ""),
            lead.get("phone", ""),
            lead.get("company_email", ""),
            lead.get("company_name", ""),
            lead.get("website", ""),
            "Yes" if lead.get("report_generated") else "No",
            "Yes" if lead.get("report_approved") else "No",
            "Yes" if lead.get("report_sent") else "No",
            lead.get("created_at", ""),
            lead.get("updated_at", ""),
        ]

        try:
            # Check if PSID already exists in sheet
            psid_col = leads_ws.col_values(1)
            if psid in psid_col:
                row_idx = psid_col.index(psid) + 1
                leads_ws.update(f"A{row_idx}", [row])
                logger.info("Updated Sheets row for PSID %s", psid)
            else:
                leads_ws.append_row(row, value_input_option="USER_ENTERED")
                logger.info("Appended new Sheets row for PSID %s", psid)
            return True
        except Exception as exc:
            logger.error("Failed to write lead to Sheets: %s", exc)
            return False

    def log_report(self, psid: str) -> bool:
        """Log report pitch data to the Reports tab."""
        if not self.client:
            return False

        pitch = _get_pitch_from_db(psid)
        if not pitch:
            return False

        _, reports_ws = self._get_sheets()
        if not reports_ws:
            return False

        row = [
            pitch.get("psid", ""),
            pitch.get("company_name", ""),
            _get_lead_email(psid),
            pitch.get("top_services", ""),
            pitch.get("pitch_angle", ""),
            pitch.get("budget_tier", ""),
            pitch.get("opening_line", ""),
            pitch.get("html_path", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ]

        try:
            psid_col = reports_ws.col_values(1)
            if psid in psid_col:
                row_idx = psid_col.index(psid) + 1
                reports_ws.update(f"A{row_idx}", [row])
            else:
                reports_ws.append_row(row, value_input_option="USER_ENTERED")
            logger.info("Report data logged to Sheets for PSID %s", psid)
            return True
        except Exception as exc:
            logger.error("Failed to write report to Sheets: %s", exc)
            return False

    def sync_all(self) -> int:
        """Sync ALL leads from SQLite to Google Sheets. Returns count synced."""
        if not self.client:
            logger.info("Sheets not configured — skipping full sync.")
            return 0

        psids = _get_all_psids()
        count = 0
        for psid in psids:
            if self.log_lead(psid):
                count += 1
        logger.info("Synced %d leads to Google Sheets.", count)
        return count


# ── SQLite read helpers ────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_cfg.path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_lead_from_db(psid: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM meta_leads WHERE psid = ?", (psid,)
        ).fetchone()
    return dict(row) if row else None


def _get_pitch_from_db(psid: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM meta_report_pitches WHERE psid = ?", (psid,)
        ).fetchone()
    return dict(row) if row else None


def _get_lead_email(psid: str) -> str:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT company_email FROM meta_leads WHERE psid = ?", (psid,)
        ).fetchone()
    return row["company_email"] if row else ""


def _get_all_psids() -> list:
    with _get_conn() as conn:
        rows = conn.execute("SELECT psid FROM meta_leads").fetchall()
    return [r["psid"] for r in rows]
