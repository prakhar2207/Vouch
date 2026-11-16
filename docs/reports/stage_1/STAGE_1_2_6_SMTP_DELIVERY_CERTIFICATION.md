# SRI LEKH — STAGE 1.2.6 SMTP RELAY, DNS AUTHENTICATION & INBOX DELIVERY CERTIFICATION

**Assessment Date:** 2026-11-12  
**Target Domain:** `srilekh.com`  
**Protected Baseline:** Zero hardcoded credentials; strict SPF `-all` policy in place  
**Certification Verdict:** **BLOCKED PENDING OWNER CREDENTIALS & DNS ACTION (OA-06)**  

---

## 1. Executive Summary

Transactional email delivery (for password resets, company invites, billing receipts, and account deletion confirmations) is a critical operational component for production release.

An audit of the domain's live DNS records and the application's configuration revealed an active email deliverability conflict that would cause 100% of outbound emails to be rejected or quarantined by recipient mail servers (Gmail, Yahoo, Outlook) if deployed as currently configured.

This certification report details:
1. The live DNS authentication audit (`SPF`, `DKIM`, `DMARC`, `MX`).
2. The architectural conflict between Django default settings and live DNS records.
3. Comparative evaluation of Option A (GoDaddy Secureserver) vs Option B (AWS SES / Resend).
4. Step-by-step configuration runbooks for both paths.
5. End-to-end verification probe script and deliverability metrics.

---

## 2. Live DNS Authentication Audit (`srilekh.com`)

Live DNS query executed against public root resolver (`8.8.8.8`):

### 2.1 SPF Record (`srilekh.com`)
```
srilekh.com  text = "v=spf1 include:secureserver.net -all"
```
- **Analysis:** The Sender Policy Framework explicitly authorizes ONLY `secureserver.net` (GoDaddy's email infrastructure).
- **Enforcement:** The `-all` mechanism specifies a **HARD FAIL**. Any mail sent with `@srilekh.com` from an IP address outside GoDaddy's authorized network will fail SPF evaluation.

### 2.2 MX Records (`srilekh.com`)
```
srilekh.com  MX preference = 0, mail exchanger = smtp.secureserver.net
srilekh.com  MX preference = 10, mail exchanger = mailstore1.secureserver.net
```
- **Analysis:** Inbound mail is routed through GoDaddy's Secureserver mail exchangers.

### 2.3 DMARC Policy (`_dmarc.srilekh.com`)
```
_dmarc.srilekh.com  text = "v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;"
```
- **Analysis:** DMARC enforcement policy is set to `p=quarantine`. If an email fails both SPF alignment and DKIM alignment, recipient mail servers are instructed to flag the message as spam/quarantine.

### 2.4 DKIM Record (`default._domainkey.srilekh.com`)
```
*** dns.google can't find default._domainkey.srilekh.com: Non-existent domain
```
- **Analysis:** No DKIM public key is currently published under standard domainkey selectors.

---

## 3. The Deliverability Conflict in Application Configuration

Inspection of [`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py#L466-L476):
```python
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='SriLekh <admin@srilekh.com>')
EMAIL_REPLY_TO = env('EMAIL_REPLY_TO', default='support@srilekh.com')
```

### The Conflict:
1. `DEFAULT_FROM_EMAIL` uses sender domain `@srilekh.com`.
2. Default `EMAIL_HOST` points to `smtp.gmail.com`.
3. If an owner attempts to send mail using a personal Gmail account or Google SMTP while maintaining `DEFAULT_FROM_EMAIL = admin@srilekh.com`, the receiving mail server will inspect SPF on `srilekh.com`.
4. Because Google's SMTP IPs are **NOT** in `include:secureserver.net`, SPF results in **FAIL (Hardfail)**.
5. With no DKIM signature to rescue alignment, DMARC evaluates to **FAIL**.
6. Recipient MTAs (Gmail, Microsoft, etc.) will reject or send to Junk.

---

## 4. Evaluation of Remediation Paths

### Option A: Use Existing GoDaddy Workspace / Microsoft 365 Relay (Fastest, 0 DNS Changes)
- **Host:** `smtpout.secureserver.net`
- **Port:** `465` (SSL) or `587` (TLS)
- **Sender:** `admin@srilekh.com`
- **Pros:**
  - Matches the existing `include:secureserver.net` SPF record with 100% SPF alignment immediately.
  - Zero DNS changes required on GoDaddy nameservers.
- **Cons:**
  - Shared relay throughput limits (typically 250–500 emails/day on basic mailboxes).
  - DKIM is managed by GoDaddy mailbox settings.

### Option B: Dedicated Transactional Provider (AWS SES / Resend / Postmark) (Recommended for Scale)
- **Host:** `email-smtp.us-east-1.amazonaws.com` or `smtp.resend.com`
- **Port:** `587` (TLS)
- **Pros:**
  - High deliverability, dedicated IP reputation, detailed bounce/complaint webhooks, high sending limits.
- **Cons:**
  - Requires updating GoDaddy DNS: adding SPF include (e.g. `include:amazonses.com` or `include:resend.com`) and publishing 3 DKIM CNAME/TXT records.

---

## 5. Step-by-Step Owner Configuration Runbooks

### Runbook A: Configuring GoDaddy Secureserver SMTP (Zero DNS Changes)

1. Open Render Dashboard -> Select `vouch-u3u7` (and `vouch-staging-worker` when provisioned).
2. Go to **Environment** tab and add/update:
   ```env
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtpout.secureserver.net
   EMAIL_PORT=465
   EMAIL_USE_SSL=True
   EMAIL_USE_TLS=False
   EMAIL_HOST_USER=admin@srilekh.com
   EMAIL_HOST_PASSWORD=<Owner_GoDaddy_Email_Password>
   DEFAULT_FROM_EMAIL=SriLekh <admin@srilekh.com>
   EMAIL_REPLY_TO=support@srilekh.com
   ```
3. Save changes.

---

### Runbook B: Configuring AWS SES / Resend (With DNS Updates)

1. **In GoDaddy DNS Management (`srilekh.com`):**
   - Update SPF TXT record:
     ```
     v=spf1 include:secureserver.net include:amazonses.com -all
     ```
   - Add the 3 CNAME DKIM verification records provided by AWS SES (or the Resend DKIM TXT record).
2. **In Render Dashboard (`vouch-u3u7` / `vouch-staging-worker`):**
   ```env
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=<SES_SMTP_USERNAME>
   EMAIL_HOST_PASSWORD=<SES_SMTP_PASSWORD>
   DEFAULT_FROM_EMAIL=SriLekh <admin@srilekh.com>
   EMAIL_REPLY_TO=support@srilekh.com
   ```
3. Save changes.

---

## 6. Verification Probe Script & Pass/Fail Metrics

Once credentials are configured in staging, execute the verification script via manage.py shell or staging endpoint:

```python
import os, django
from django.core.mail import send_mail

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

recipient = "prakharssa@gmail.com"
sent = send_mail(
    subject="[SriLekh Verification] Staging SMTP Delivery Test",
    message="This is an automated delivery test verifying SPF, DKIM, and DMARC alignment for SriLekh release certification.",
    from_email="SriLekh <admin@srilekh.com>",
    recipient_list=[recipient],
    fail_silently=False,
)
print("EMAILS_SENT:", sent)
assert sent == 1, "Failed to send verification email"
```

### Passing Acceptance Thresholds for Closure of OA-06:
1. `send_mail` returns `1` within `< 10` seconds without socket timeout or authentication exception.
2. Email arrives in recipient inbox (NOT Spam/Junk folder).
3. Raw email headers show:
   - `spf=pass`
   - `dmarc=pass`
   - `dkim=pass` (if Option B configured)
