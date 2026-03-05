# Google Form Setup Guide
**DGenius Solutions — AI Content Lead Capture Form**

This guide walks you through creating the Google Form that captures lead
details after someone DMs you in response to commenting "AI Content" on
your Meta ad.

---

## Step 1 — Create the Google Form

1. Go to [forms.google.com](https://forms.google.com) and click **Blank form**
2. Title: **Free Brand Audit — Tell Us About Your Business**
3. Description:
   > We're excited to put together your personalised Brand Audit Report!
   > Just fill in the details below and we'll get back to you within 24 hours
   > with your free report and tailored recommendations.

---

## Step 2 — Add These Questions (exact names matter)

Add these questions in order. The field names must match EXACTLY for the
Apps Script to map them correctly.

| Question Title | Type | Required |
|----------------|------|----------|
| Full Name | Short answer | Yes |
| Phone Number | Short answer | Yes |
| Company Email | Short answer | Yes |
| Company Name | Short answer | Yes |
| Website | Short answer | Yes |
| PSID | Short answer | No (hidden) |

### Notes:
- **PSID** is a hidden field populated automatically via the pre-filled URL
  (see Step 5). You can hide it by making it the last question and not
  mentioning it in the form description.
- For **Company Email**, you can add response validation:
  Settings → Responses → Validate email format.

---

## Step 3 — Customise the Form

1. **Theme**: Click the palette icon → Set colours to match DGenius brand
   - Primary: `#0f3460` (dark navy)
   - Background: White
   - Upload your brand logo (top of page)

2. **Confirmation message** (Settings → Presentation → Confirmation message):
   > Thank you! We're already working on your Brand Audit Report.
   > Expect it in your inbox within 24 hours. Meanwhile, feel free to
   > explore our work at dgeniussolutions.com

3. **Collect email addresses**: Settings → Responses → Collect email addresses
   → Set to "Verified" (respondents must sign in) OR leave off for frictionless entry

---

## Step 4 — Link to Google Sheets

1. In the Form, click the **Responses** tab
2. Click the green **Sheets** icon → Create a new spreadsheet
3. Name it: **AI Content Leads — DGenius**
4. This spreadsheet will auto-populate with form responses

---

## Step 5 — Set Up the Apps Script (Webhook)

1. Open the linked Spreadsheet created in Step 4
2. Click **Extensions → Apps Script**
3. Delete the default `myFunction` code
4. Paste the entire contents of `docs/google_apps_script.js`
5. Update the two config values at the top:
   ```javascript
   var WEBHOOK_URL = "https://YOUR_SERVER_URL/meta-form";
   var WEBHOOK_SECRET = "YOUR_WEBHOOK_SECRET_HERE";
   ```
6. Click **Save** (floppy disk icon)
7. Add a trigger:
   - Click the **clock icon** (Triggers) in the left sidebar
   - Click **+ Add Trigger** (bottom right)
   - Function: `onFormSubmit`
   - Deployment: `Head`
   - Event source: `From spreadsheet`
   - Event type: `On form submit`
   - Click **Save** → authorise when prompted

---

## Step 6 — Generate Per-User Pre-Filled Form Links

To auto-populate the PSID (so we know which commenter filled the form):

1. Click the **three-dot menu** in your form → **Get pre-filled link**
2. Fill in the PSID field with a placeholder (e.g., `PSID_PLACEHOLDER`)
3. Click **Get Link** → copy the URL
4. In your Python code (`src/config.py`), the DM sender will replace
   `PSID_PLACEHOLDER` with the actual PSID for each user

The DM template in `src/meta/dm_sender.py` uses `meta_cfg.google_form_url`.
Set this to the pre-filled URL template in your `.env`:

```
META_GOOGLE_FORM_URL=https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform?usp=pp_url&entry.XXXX=PSID_PLACEHOLDER
```

The system automatically replaces `PSID_PLACEHOLDER` with the real PSID
when building each DM. *(This behaviour is in `DMSender.build_dm_text()` —
update the replacement logic if your placeholder differs.)*

---

## Step 7 — Test the Pipeline

1. **Start the webhook server**:
   ```bash
   python main.py meta-reply webhook
   ```
   In a second terminal, expose it publicly:
   ```bash
   ngrok http 5055
   ```
   Copy the ngrok URL and update `WEBHOOK_URL` in the Apps Script.

2. **Test the Apps Script** directly:
   - In the Apps Script editor, select the `testWebhook` function
   - Click **Run** → check Logs for a `200` response

3. **Submit a test form response** — check:
   - Your webhook server logs show the received data
   - A brand report is generated in `reports/brand_audits/`
   - The lead appears in the review queue: `python main.py meta-reply list`

---

## Step 8 — Brand Logo

Yes — please send us your brand logo! Add it to the form:
1. Click the image icon at the top of the form
2. Upload your logo (recommended: PNG, transparent background, min 400px wide)

Also add it to the HTML report template by placing your logo file at:
`reports/brand_audits/assets/logo.png`
Then reference it in `src/meta/brand_report_generator.py` inside `_to_html()`.

---

## Checklist

- [ ] Form created with all 6 fields
- [ ] Linked to Google Sheets
- [ ] Apps Script pasted, configured, and triggered
- [ ] Webhook server running and publicly accessible
- [ ] `META_GOOGLE_FORM_URL` set in `.env`
- [ ] Test submission received and report generated
- [ ] Brand logo added to form and report template

---

## Related Files

| File | Purpose |
|------|---------|
| `docs/google_apps_script.js` | Apps Script — sends form data to webhook |
| `src/meta/webhook_handler.py` | Flask server — receives form data |
| `src/meta/brand_report_generator.py` | Claude AI — generates brand report |
| `src/meta/report_approver.py` | CLI — review and approve reports |
| `src/meta/dm_sender.py` | Meta API — sends DMs with form link |
| `src/meta/sheets_logger.py` | Google Sheets — logs all leads |
| `docs/META_SETUP.md` | Meta App setup guide |
