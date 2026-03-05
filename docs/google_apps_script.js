/**
 * DGenius Solutions — Google Apps Script
 * =========================================
 * Paste this script into your Google Form's linked Spreadsheet:
 *   Extensions → Apps Script → paste → Save → set trigger
 *
 * What it does:
 *   When a new form response arrives, it reads the row, builds a JSON
 *   payload (including the PSID pre-filled via the form URL), and POSTs
 *   it to the DGenius webhook server so the brand report pipeline runs.
 *
 * Setup steps:
 *   1. Open your Google Form → Responses tab → click the Sheets icon
 *      (this links the Form to a Spreadsheet).
 *   2. In the Spreadsheet: Extensions → Apps Script
 *   3. Paste this entire file → Save
 *   4. Set WEBHOOK_URL below to your server URL
 *   5. Set WEBHOOK_SECRET to match META_WEBHOOK_SECRET in your .env
 *   6. Add a trigger:
 *        Triggers (clock icon) → + Add Trigger
 *        Function: onFormSubmit
 *        Event source: From spreadsheet
 *        Event type: On form submit
 *   7. Authorise when prompted
 *
 * PSID pre-fill:
 *   When you send the DM from the Python system, the form URL is plain.
 *   To auto-capture the PSID, use a pre-filled link per user. See the
 *   META_SETUP.md guide for how to generate per-user pre-filled links.
 *   Alternatively, the webhook can match by email if PSID is missing.
 */

// ── CONFIGURE THESE ──────────────────────────────────────────────────────────

var WEBHOOK_URL = "https://YOUR_SERVER_URL/meta-form";
// e.g. "https://abc123.ngrok.io/meta-form"  (local dev with ngrok)
//      "https://yourserver.com/meta-form"   (production VPS)

var WEBHOOK_SECRET = "YOUR_WEBHOOK_SECRET_HERE";
// Must match META_WEBHOOK_SECRET in your Python .env file

// Column names in your Google Form Spreadsheet (EXACTLY as they appear)
// Edit these to match your Form questions if they differ.
var FIELD_MAP = {
  "Full Name":         "full_name",
  "Phone Number":      "phone",
  "Company Email":     "company_email",
  "Company Email ID":  "company_email",
  "Company Name":      "company_name",
  "Website":           "website",
  "Website URL":       "website",
  "PSID":              "psid",        // hidden pre-filled field
  "Reference ID":      "psid",        // renamed label for the pre-filled PSID
  "Timestamp":         "timestamp",
};

// ── TRIGGER FUNCTION ─────────────────────────────────────────────────────────

/**
 * Triggered automatically on every new form submission.
 * Reads the latest row and sends it to the DGenius webhook.
 */
function onFormSubmit(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];

    // Get values from the submitted row
    var row = e.range.getValues()[0];

    // Build payload
    var payload = {};
    for (var i = 0; i < headers.length; i++) {
      var header = headers[i].toString().trim();
      var fieldName = FIELD_MAP[header] || header.toLowerCase().replace(/\s+/g, "_");
      var value = row[i] ? row[i].toString().trim() : "";
      if (value) {
        payload[fieldName] = value;
      }
    }

    Logger.log("Form submission payload: " + JSON.stringify(payload));

    if (!WEBHOOK_URL || WEBHOOK_URL === "https://YOUR_SERVER_URL/meta-form") {
      Logger.log("ERROR: WEBHOOK_URL not configured. Update the script.");
      return;
    }

    // Build HMAC-SHA256 signature
    var body = JSON.stringify(payload);
    var signature = _hmacSha256(WEBHOOK_SECRET, body);

    // POST to webhook
    var options = {
      method: "post",
      contentType: "application/json",
      payload: body,
      headers: {
        "X-DGenius-Signature": signature,
        "User-Agent": "DGenius-AppsScript/1.0",
      },
      muteHttpExceptions: true,
    };

    var response = UrlFetchApp.fetch(WEBHOOK_URL, options);
    var status = response.getResponseCode();
    var responseBody = response.getContentText();

    Logger.log("Webhook response " + status + ": " + responseBody);

    if (status === 200) {
      Logger.log("SUCCESS: Lead sent to DGenius system for " + (payload.full_name || "unknown"));
    } else {
      Logger.log("WARNING: Webhook returned status " + status);
      // Retry once after 5 seconds
      Utilities.sleep(5000);
      UrlFetchApp.fetch(WEBHOOK_URL, options);
    }

  } catch (err) {
    Logger.log("ERROR in onFormSubmit: " + err.toString());
  }
}


// ── MANUAL TEST ───────────────────────────────────────────────────────────────

/**
 * Run this function manually from the Apps Script editor to test
 * your webhook connection before the form goes live.
 */
function testWebhook() {
  var testPayload = {
    full_name: "Test User",
    phone: "+1-555-000-0000",
    company_email: "test@example.com",
    company_name: "Test Company Ltd",
    website: "https://www.example.com",
    psid: "TEST_PSID_12345",
  };

  var body = JSON.stringify(testPayload);
  var signature = _hmacSha256(WEBHOOK_SECRET, body);

  var options = {
    method: "post",
    contentType: "application/json",
    payload: body,
    headers: {
      "X-DGenius-Signature": signature,
      "User-Agent": "DGenius-AppsScript-Test/1.0",
    },
    muteHttpExceptions: true,
  };

  var response = UrlFetchApp.fetch(WEBHOOK_URL, options);
  Logger.log("Test webhook status: " + response.getResponseCode());
  Logger.log("Test webhook body: " + response.getContentText());
}


// ── UTILITIES ─────────────────────────────────────────────────────────────────

/**
 * Compute HMAC-SHA256 hex signature.
 * Google Apps Script has built-in Utilities.computeHmacSha256Signature.
 */
function _hmacSha256(secret, message) {
  if (!secret || secret === "YOUR_WEBHOOK_SECRET_HERE") {
    return "no-signature";
  }
  var signature = Utilities.computeHmacSha256Signature(message, secret);
  return signature.map(function(byte) {
    return ("0" + (byte & 0xff).toString(16)).slice(-2);
  }).join("");
}
