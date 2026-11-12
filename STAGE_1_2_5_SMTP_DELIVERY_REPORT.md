# SRI LEKH — STAGE 1.2.5 SMTP, DNS & EMAIL DELIVERY CERTIFICATION

**Assessment Date:** 2026-11-12  
**Branch / Commit:** `feat/google-play-launch-readiness` @ `c160fca0`  
**Overall Gate Verdict (Gate D/E — Live Email Delivery):** **BLOCKED** *(Codebase idempotent email delivery & timeout resilience verified; live SMTP credentials absent, live inbox delivery untested, and `srilekh.com` DNS configuration shows critical SPF/DKIM alignment gap)*

---

## 1. Repository Email Architecture Verified ([`config/settings.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/config/settings.py#L465-L476), [`email_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/email_service.py#L16-L90))

- **Backend Configuration:**
  - `EMAIL_BACKEND`: `'django.core.mail.backends.console.EmailBackend'` if `DEBUG` else `'django.core.mail.backends.smtp.EmailBackend'`
  - `EMAIL_HOST`: `env('EMAIL_HOST', default='smtp.gmail.com')` (`EMAIL_PORT=587`, `EMAIL_USE_TLS=True`, `EMAIL_TIMEOUT=10`)
  - `DEFAULT_FROM_EMAIL`: `'SriLekh <admin@srilekh.com>'`, `EMAIL_REPLY_TO`: `'support@srilekh.com'`
  - **Environment Reality:** Neither local `.env` nor [`render.yaml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/render.yaml) configures `EMAIL_HOST_USER` or `EMAIL_HOST_PASSWORD`. Mocked SMTP timeout resilience (`test_password_reset_smtp_timeout_returns_generic_200_without_crash`) passes cleanly on Neon PostgreSQL 18.6 without crashing OTP/reset endpoints.

---

## 2. Live DNS & SMTP Relay Probes (`2026-11-12`)

| Check Target | Observed Output | Operational Impact |
| :--- | :--- | :--- |
| **`srilekh.com` Nameservers** | GoDaddy (`ns21.domaincontrol.com`, `ns22.domaincontrol.com`) | Domain DNS controlled via GoDaddy |
| **`srilekh.com` MX Records** | `smtp.secureserver.net` (pref 0), `mailstore1.secureserver.net` (pref 10) | Domain mail hosted on GoDaddy / Secureserver |
| **`srilekh.com` SPF (`TXT`)** | `"v=spf1 include:secureserver.net -all"` | **CRITICAL CONFIG MATCH WARNING:** Strict `-all` rejects unauthorized senders! Because `config/settings.py` defaults `EMAIL_HOST` to `smtp.gmail.com` instead of `smtpout.secureserver.net` (or a dedicated transactional relay like Resend/SES), sending `admin@srilekh.com` via `smtp.gmail.com` without updating SPF/DKIM will fail SPF `-all` checks |
| **`_dmarc.srilekh.com` (`TXT`)** | `"v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;"` | Active `p=quarantine` DMARC policy enforces SPF/DKIM alignment |
| **DKIM Selector Probes (`TXT`)** | `default._domainkey.srilekh.com` -> DNS request timed out; `google._domainkey.srilekh.com` -> empty/no record | **NO DKIM RECORD FOUND** on inspected standard selectors |
| **TCP Banner Reachability (`port 587/465`)** | `smtp.gmail.com:587` OPEN (`220 ... gsmtp`); `smtpout.secureserver.net:587` OPEN (`220 sxplsmtpa04-11.prod.sxb1.secureserver.net :SMTPAUTH:`); `smtpout.secureserver.net:465` OPEN (`TLS_PORT`); `smtp.secureserver.net:587` `TimeoutError` (expected: inbound MX only) | Authenticated submission endpoint `smtpout.secureserver.net` (`587`/`465`) is network-reachable |

---

## 3. Required Owner Actions (`OA-06`)

1. Provision a transactional SMTP relay (`EMAIL_HOST=smtpout.secureserver.net` matching GoDaddy SPF `include:secureserver.net`, or dedicated transactional provider such as AWS SES/Resend/Postmark with matching SPF `include:` + DKIM TXT records on `srilekh.com` DNS).
2. Configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` in Render staging/production secrets.
3. Verify real inbox delivery (<10s) for signup OTP, password reset OTP, and invoice PDF emails and inspect email authentication headers (`SPF=PASS`, `DKIM=PASS`, `DMARC=PASS`).
