# SRI LEKH — STAGE 1.2.5 STAGING DEPLOYMENT & INTEGRATION CERTIFICATION

**Assessment Date:** 2026-11-12  
**Live Render Staging API:** `https://vouch-u3u7.onrender.com`  
**Tracked Staging Branch:** `fix/stage4-12-day6-remediation` (fast-forwarded from `f8578a88` -> `44fd0150` -> **`c160fca0`** matching `feat/google-play-launch-readiness`)  
**Overall Gate Verdict (Gate D — Staging & Cross-Origin Integration):** **PARTIALLY VERIFIED / FRONTEND STAGING BLOCKED** *(Live Render staging backend deployed, DB-isolated, and live E2E verified; deployed Vercel staging frontend remains behind SSO login wall & `staging.srilekh.com` DNS is NXDOMAIN)*

---

## 1. Live Render Staging Environment & Health Verification (`c160fca0`)

Probing `GET https://vouch-u3u7.onrender.com/api/v1/health/environment/` returned **`HTTP 200 OK`**:
- `service`: `"SriLekh Accounting Engine"` (`version: "1.0.2"`, `environment: "staging"`, **`commit: "c160fca0"`**)
- `database`: `{"engine": "postgresql", "sanitized_target": "neondb_staging", "identity_fingerprint": "6f4741bdaaf4", "is_isolated": true}`
- `migrations`: `{"status": "up_to_date", "unapplied_count": 0}`
- `redis`: `{"configured": true, "status": "unreachable"}`
- `celery`: `{"beat_schedule_configured": true, "beat_schedule_active": false, "outbox_sweeper_interval_seconds": 60, "workers_online": 0, "task_always_eager": false, "acks_late": true}`

Direct Neon isolation check (`python scripts/verify_staging_identity.py`) confirmed:
- `neondb_staging` (`PostgreSQL 18.6`, `77` public tables, `147` migrations, `7` staging companies, **`0`** rows for protected tenant `Maa Annapurna Belting Store`).

---

## 2. Live Deployed Render Staging Functional & Security Integration Probes

1. **Pre-Upgrade Blocker Fixed:** Prior to Stage 1.2.5, `https://vouch-u3u7.onrender.com` ran `f8578a88` where `/api/v1/auth/account/delete-request/` returned `404`. Fast-forwarding `fix/stage4-12-day6-remediation` rebuilt and migrated Render cleanly (`44fd0150`, subsequently updated to `c160fca0`).
2. **Full Live Ephemeral User Integration Flow on `https://vouch-u3u7.onrender.com` (commit `44fd0150`, `task-13896`):**
   - `POST /api/v1/auth/account/delete-request/` (unauthenticated) -> **`401 Unauthorized`**
   - `GET /api/v1/auth/account/delete-status/?reference=not-a-uuid` -> **`400 Bad Request`**
   - Provisioned ephemeral synthetic user (`stage125.cert.<uid>@staging.srilekh.invalid`) + solo company in `neondb_staging` -> Web cookie login (`X-Client-Type: web` -> `srilekh_access` HttpOnly cookie, zero `access`/`refresh` tokens in JSON body) -> `GET /api/v1/auth/me/` **`200 OK`** -> `POST /api/v1/accounting/import/preview/` with 52 MB ZIP-bomb `.xlsx` -> **`400 Bad Request`** (`{'error': 'Spreadsheet archive entry exceeds 50MB decompressed limit.'}`) -> Capacitor login Bearer captured -> `POST /api/v1/auth/account/delete-request/` (`Origin: https://staging.srilekh.com` + `X-CSRFToken`) -> **`200 OK` (`COMPLETED`, ref `a126a451-431b-4298-a01f-cde5d712275f`)** -> stale Bearer `GET /api/v1/auth/me/` -> **`401 Unauthorized`** -> `GET /api/v1/auth/account/delete-status/?reference=...` -> **`200 OK`** with `0` PII leaked.
3. **Post-`c160fca0` Live Re-Verification & CORS Allowlist Matrix (`task-14114` / latest probe):**
   - Unauthenticated `POST /api/v1/auth/account/delete-request/` -> **`401`**, malformed `/delete-status/` -> **`400`**.
   - `OPTIONS /api/v1/auth/me/`:
     - `Origin: https://vouch-pi-one.vercel.app` -> **`Access-Control-Allow-Origin: https://vouch-pi-one.vercel.app`**
     - `Origin: https://staging.srilekh.com` -> **`Access-Control-Allow-Origin: https://staging.srilekh.com`**
     - `Origin: https://www.srilekh.com` -> **`Access-Control-Allow-Origin: https://www.srilekh.com`**
     - `Origin: https://evil.example.com` -> **`None`** (rejected)

---

## 3. Vercel Deployed Staging Frontend Blocker (`OA-09`)

- Vercel built commit `c160fca0` cleanly (`Vercel: success` on GitHub commit statuses).
- However:
  - `staging.srilekh.com` DNS fails (`Non-existent domain`).
  - `https://vouch-git-feat-google-play-launch-readiness-trail-blazer.vercel.app/` returns **`HTTP 302`** -> `https://vercel.com/sso-api?...` (Vercel Preview SSO Authentication Wall).
- **Result:** Live Render staging backend API is deployed and certified on `c160fca0`, while browser-to-Vercel deployed cross-origin E2E remains **BLOCKED** pending Owner closing `OA-09`.
