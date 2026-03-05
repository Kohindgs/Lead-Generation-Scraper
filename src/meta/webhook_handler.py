"""
Webhook Handler — Google Form Submission Receiver
==================================================
A lightweight Flask server that receives POST requests from Google Apps Script
when a new form response is submitted.

The Apps Script (docs/google_apps_script.js) watches the linked Google Sheet
for new rows and POSTs them to this endpoint.

On receiving a valid submission this handler:
  1. Validates the request (HMAC signature or shared secret)
  2. Upserts the lead data into SQLite
  3. Triggers brand report generation (Claude AI)
  4. Logs the lead to Google Sheets
  5. Returns 200 OK

Run the server:
  python main.py meta-reply webhook          # start on port 5055
  python main.py meta-reply webhook --port 8080

Exposing locally for testing (without a public server):
  ngrok http 5055
  Then set META_WEBHOOK_URL=https://xxxx.ngrok.io/meta-form in .env

Production:
  Deploy to any VPS / Cloud Run / Railway and point the Apps Script URL there.

Environment variables needed:
  META_WEBHOOK_SECRET   — shared secret to validate incoming POSTs
"""

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional

from src.config import meta_cfg, db_cfg
from src.utils.helpers import get_logger

logger = get_logger(__name__)

_FORM_FIELD_MAP = {
    # Maps Google Form question titles → our internal field names.
    # Adjust these to match EXACTLY the question text in your Google Form.
    "Full Name":         "full_name",
    "Phone Number":      "phone",
    "Company Email":     "company_email",
    "Company Email ID":  "company_email",
    "Company Name":      "company_name",
    "Website":           "website",
    "Website URL":       "website",
    # PSID is injected by the Apps Script as a hidden pre-filled field
    "PSID":              "psid",
}


# ── SQLite helper ──────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_cfg.path)
    conn.row_factory = sqlite3.Row
    return conn


def _upsert_form_data(psid: str, data: dict):
    with _get_conn() as conn:
        conn.execute("""
            UPDATE meta_leads
            SET
                full_name     = COALESCE(?, full_name),
                phone         = COALESCE(?, phone),
                company_email = COALESCE(?, company_email),
                company_name  = COALESCE(?, company_name),
                website       = COALESCE(?, website),
                updated_at    = datetime('now')
            WHERE psid = ?
        """, (
            data.get("full_name"),
            data.get("phone"),
            data.get("company_email"),
            data.get("company_name"),
            data.get("website"),
            psid,
        ))
        conn.commit()


# ── Signature validation ───────────────────────────────────────────────────────

def _valid_signature(request_body: bytes, signature_header: str) -> bool:
    """Validate HMAC-SHA256 signature from the Apps Script."""
    secret = meta_cfg.webhook_secret
    if not secret:
        # If no secret configured, allow all (dev mode)
        logger.warning("META_WEBHOOK_SECRET not set — accepting all webhooks (dev mode).")
        return True

    expected = hmac.new(
        secret.encode(), request_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


# ── Background report generator ────────────────────────────────────────────────

def _generate_report_async(psid: str, form_data: dict):
    """Run report generation in a background thread so the webhook returns fast."""
    from src.meta.brand_report_generator import BrandReportGenerator, LeadFormData
    from src.meta.sheets_logger import SheetsLogger

    lead = LeadFormData(
        psid=psid,
        full_name=form_data.get("full_name", ""),
        phone=form_data.get("phone", ""),
        company_email=form_data.get("company_email", ""),
        company_name=form_data.get("company_name", ""),
        website=form_data.get("website", ""),
    )

    try:
        generator = BrandReportGenerator()
        result = generator.generate(lead)

        if result:
            logger.info(
                "Brand report generated for %s — awaiting approval.",
                lead.company_name
            )
        else:
            logger.error("Brand report generation failed for PSID %s.", psid)
    except Exception as exc:
        logger.error("Error generating brand report for PSID %s: %s", psid, exc)

    # Log to Google Sheets regardless of report success
    try:
        sheets = SheetsLogger()
        sheets.log_lead(psid)
        if result:
            sheets.log_report(psid)
    except Exception as exc:
        logger.error("Sheets logging failed for PSID %s: %s", psid, exc)


# ── Flask app ──────────────────────────────────────────────────────────────────

def create_app():
    """
    Create and configure the Flask webhook application.
    Import is inside the function so Flask is only required when the
    webhook server is actually used.
    """
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        raise ImportError(
            "Flask not installed. Run: pip install flask"
        )

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "DGenius Meta Webhook"})

    @app.route("/meta-form", methods=["POST"])
    def receive_form():
        """
        Receive a Google Form submission from the Apps Script.

        Expected JSON body:
        {
          "psid": "...",
          "full_name": "...",
          "phone": "...",
          "company_email": "...",
          "company_name": "...",
          "website": "..."
        }
        """
        body = request.get_data()

        # Validate signature
        sig = request.headers.get("X-DGenius-Signature", "")
        if not _valid_signature(body, sig):
            logger.warning("Invalid webhook signature — rejected request.")
            return jsonify({"error": "Invalid signature"}), 403

        try:
            payload = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400

        if not payload:
            return jsonify({"error": "Empty payload"}), 400

        # Normalise field names (handle both raw form keys and mapped names)
        normalised = {}
        for key, val in payload.items():
            mapped = _FORM_FIELD_MAP.get(key, key.lower().replace(" ", "_"))
            normalised[mapped] = str(val).strip() if val else ""

        psid = normalised.get("psid", "")
        if not psid:
            logger.warning("Webhook received without PSID — cannot match to commenter.")
            # Still store as a partial lead with a generated ID
            psid = f"form_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            # Insert as new lead
            with _get_conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO meta_leads
                        (psid, commenter_name, platform, full_name, phone,
                         company_email, company_name, website)
                    VALUES (?, ?, 'form_direct', ?, ?, ?, ?, ?)
                """, (
                    psid,
                    normalised.get("full_name", ""),
                    normalised.get("full_name", ""),
                    normalised.get("phone", ""),
                    normalised.get("company_email", ""),
                    normalised.get("company_name", ""),
                    normalised.get("website", ""),
                ))
                conn.commit()
        else:
            _upsert_form_data(psid, normalised)

        logger.info(
            "Form submission received — %s (%s) PSID=%s",
            normalised.get("full_name", "?"),
            normalised.get("company_name", "?"),
            psid,
        )

        # Generate report in background (don't block the response)
        t = threading.Thread(
            target=_generate_report_async,
            args=(psid, normalised),
            daemon=True,
        )
        t.start()

        return jsonify({"status": "received", "psid": psid}), 200

    @app.route("/meta-form/webhook-verify", methods=["GET"])
    def webhook_verify():
        """Meta webhook verification endpoint (for Facebook Webhook setup)."""
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == meta_cfg.webhook_verify_token:
            logger.info("Meta webhook verified successfully.")
            return challenge, 200
        return "Forbidden", 403

    return app


def run_server(port: int = 5055, debug: bool = False):
    """Start the webhook server."""
    app = create_app()
    logger.info("Starting DGenius Meta webhook server on port %d ...", port)
    print(f"\n  Webhook server running at: http://0.0.0.0:{port}")
    print(f"  Google Form endpoint    : http://0.0.0.0:{port}/meta-form")
    print(f"  Health check            : http://0.0.0.0:{port}/health")
    print(f"  For local testing use ngrok: ngrok http {port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
