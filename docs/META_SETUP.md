# Meta App Setup Guide
**DGenius Solutions — AI Content Reply System**

---

## What You Need

| Credential | Where to get it |
|------------|----------------|
| `META_PAGE_ACCESS_TOKEN` | Meta for Developers → your App → Generate token |
| `META_PAGE_ID` | Your Facebook Page → About → Page ID |
| `META_IG_ACCOUNT_ID` | Meta Business Suite → Instagram → Account ID |
| `META_WEBHOOK_VERIFY_TOKEN` | Any random string you choose |
| `META_WEBHOOK_SECRET` | Any strong random string (used to sign webhook POSTs) |

---

## Step 1 — Create a Meta App

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Click **My Apps → Create App**
3. Choose: **Business** type
4. Fill in app name (e.g., "DGenius Reply Bot") → Create
5. Note your **App ID** and **App Secret**

---

## Step 2 — Add Products

In your App Dashboard, add these products:

- **Messenger** (for Facebook DMs)
- **Instagram Graph API** (for Instagram DMs)
- **Webhooks** (to receive real-time comment notifications — optional, polling works too)

---

## Step 3 — Generate a Page Access Token

1. App Dashboard → **Messenger → Settings**
2. Under **Access Tokens** → select your Facebook Page
3. Click **Generate Token** → copy it
4. This is your `META_PAGE_ACCESS_TOKEN`

For long-lived tokens (recommended for production):
```bash
# Exchange short-lived token for long-lived (60-day) token
curl -X GET "https://graph.facebook.com/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=YOUR_APP_ID
  &client_secret=YOUR_APP_SECRET
  &fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

---

## Step 4 — Required Permissions

Your App needs these permissions (request via App Review for production):

| Permission | Purpose |
|-----------|---------|
| `pages_read_engagement` | Read comments on your page |
| `pages_manage_metadata` | Access page metadata |
| `pages_messaging` | Send Messenger DMs |
| `instagram_basic` | Read Instagram account data |
| `instagram_manage_comments` | Read Instagram comments |
| `instagram_manage_messages` | Send Instagram DMs |

For testing, these work without App Review on your own page.
For running ads at scale, submit for App Review.

---

## Step 5 — Find Your Page ID

```
Facebook Page → About (scroll down) → Page ID
```
Or use Graph Explorer:
```
GET /me?fields=id,name&access_token=YOUR_PAGE_ACCESS_TOKEN
```

---

## Step 6 — Find Your Instagram Account ID

```
Meta Business Suite → Settings → Instagram accounts → Account ID
```
Or via Graph API:
```
GET /me/instagram_accounts?access_token=YOUR_PAGE_TOKEN
```

---

## Step 7 — Configure `.env`

```bash
# Meta Graph API
META_PAGE_ACCESS_TOKEN="EAAxxxxxxxxxxxxxxxx"
META_PAGE_ID="123456789012345"
META_IG_ACCOUNT_ID="17841400000000000"

# Webhook (for form submissions from Google Apps Script)
META_WEBHOOK_SECRET="choose-a-strong-random-secret"
META_WEBHOOK_VERIFY_TOKEN="choose-another-random-token"

# Google Form URL (with PSID placeholder for pre-fill)
META_GOOGLE_FORM_URL="https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform?usp=pp_url&entry.XXXXXXX=PSID_PLACEHOLDER"

# Gmail / Google Business for sending reports
META_SMTP_HOST="smtp.gmail.com"
META_SMTP_PORT=587
META_SMTP_USER="your@dgeniussolutions.com"
META_SMTP_PASS="your-google-app-password"

# Google Sheets
GOOGLE_SHEET_ID="your-google-sheet-id-from-url"
GOOGLE_SERVICE_ACCOUNT_JSON="config/google-service-account.json"
```

---

## Step 8 — Gmail App Password

To send emails via Gmail (Google Workspace):

1. Google Account → Security → 2-Step Verification → App passwords
2. Select app: **Mail** | Select device: **Other** → enter "DGenius Bot"
3. Copy the 16-character password → set as `META_SMTP_PASS`

---

## Step 9 — Run the Campaign

```bash
# One-time scan + DM
python main.py meta-reply scan

# Continuous polling every 15 minutes
python main.py meta-reply scan --watch

# Start the webhook server (receives Google Form submissions)
python main.py meta-reply webhook

# Review and approve reports
python main.py meta-reply review

# List all leads
python main.py meta-reply list

# View campaign stats
python main.py meta-reply stats
```

---

## Meta Ad Campaign Tips

1. **Ad creative**: Use copy that naturally encourages commenting "AI Content"
   Example CTA: *"Comment AI CONTENT below to get your free brand audit"*

2. **Ad objective**: Engagement → Comment objective works best

3. **Audience**: Target B2B decision-makers, CEOs, Marketing Directors,
   Business Owners in your target industries

4. **Budget**: Start with $10-20/day per ad set to test

5. **Retargeting**: Pixel people who comment → show a second ad with
   stronger social proof to the same audience

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Invalid OAuth token" | Regenerate your Page Access Token |
| "Permissions error" | Check your App has the required permissions |
| DMs not sending | Ensure user has messaged your page before (24-hour rule) |
| Instagram DMs failing | Confirm IG account is connected to your App |
| No comments found | Check `META_PAGE_ID` is correct; verify the page has posts |
