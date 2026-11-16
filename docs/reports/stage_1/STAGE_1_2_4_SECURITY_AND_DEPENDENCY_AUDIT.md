# SRI LEKH — STAGE 1.2.4 SECURITY AND DEPENDENCY AUDIT

**Assessment Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Overall Security Audit Status:** **CONDITIONAL PASS** *(Browser/Backend App Controls & Runtime NPM Dependencies Hardened and Verified; Native Android Keystore & Live Hosting/SMTP Pending)*

---

## 1. Dependency Supply-Chain Audit

### Frontend (`frontend/`)
- **`npm audit --omit=dev --json` (Production Runtime):**
  - `critical: 0`, `high: 0`, `moderate: 0`, `low: 0`, `total: 0` (`vulnerabilities: []`).
  - `xlsx` (`0.18.5`) confirmed absent from runtime tree; Excel parsing uses `read-excel-file@^9.3.15` wrapped in [`spreadsheet-parser.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/import/spreadsheet-parser.ts).
- **`npm audit --json` (Full Tree Including `devDependencies`):**
  - `critical: 0`, `high: 0`, `moderate: 10`, `low: 0`, `total: 10` across build/lint/CLI tools (`@capacitor/cli`, `@typescript-eslint/*`, `minimatch`, `typescript-eslint`, `uuid`, `xcode`). Not shipped in Next.js server/client runtime or Android WebView assets.

### Backend Python Packages (Host Environment Snapshot)
Audited installed versions directly via `importlib.metadata`:
- `Django 5.2.17`, `djangorestframework 3.15.2`, `djangorestframework-simplejwt 5.5.1`
- `cryptography 50.0.0`, `PyJWT 2.13.0`
- `openpyxl 3.1.5`, `pandas 3.0.5`, `Pillow 12.3.0`, `reportlab 5.0.1`
- `requests 2.34.2`, `urllib3 2.7.0`, `psycopg 3.3.4`, `celery 5.6.3`, `redis 6.4.0`
- *Disclosure:* `pip-audit` / `safety` CLI was not installed on this host, so automated CVE database matching against PyPI advisories was not run locally; should be executed in CI before production deploy.

---

## 2. File Upload, Spreadsheet, Archive & XML Parser Hardening (Stage 1.2.4)

### Frontend Browser Parser & Importer
- Hardened [`spreadsheet-parser.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/import/spreadsheet-parser.ts):
  - `validateSpreadsheetFilename`: blocks empty names, length > 255, `\0`, `/`, `\`, `..`, and ASCII control characters.
  - `validateSpreadsheetMetadata`: blocks 0-byte files, >15 MB files (`MAX_SPREADSHEET_SIZE_BYTES`), `.xls` legacy BIFF, mismatched `.csv` `.xlsx` MIME types, and unexpected dangerous MIMEs (`text/html`, `image/*`, `application/x-msdownload`, etc.).
  - `validateXlsxArchiveBytes`: parses ZIP End-of-Central-Directory & Central Directory **before** calling `readSheet(file, 1)` to block non-ZIP signatures (`PK\x03\x04` check), corrupt archives, ZIP64 sentinels, ZIP-slip entry paths (`..`, leading `/`/`\`, `\0`), >250 ZIP members, >50 MB uncompressed payload, and >100x compression ratio bombs (for >1 MB uncompressed payloads).
  - `parseCsvToRows`: blocks embedded null bytes/binary headers (`%PDF-`, `PK`, `MZ`), unclosed trailing quotes (`Malformed CSV: unclosed quoted field`), and >50,000 rows (`MAX_SPREADSHEET_ROWS`).
  - Added `parseNonNegativeSpreadsheetNumber` used by [`PriceListImportModal.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/modals/PriceListImportModal.tsx) so negative values (`-500`, `(500)`) and malformed numbers (`12.34.56`, `NaN`) never silently flip signs or corrupt prices, and duplicate item names surface explicit warnings.

### Backend Ingestion Views & Services
- Created centralized validator [`apps/accounting/services/upload_security.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/upload_security.py) and wired across:
  - [`import_views.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/import_views.py) (`UniversalImportPreviewAPIView`, `UniversalImportExecuteAPIView`)
  - [`universal_import_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/universal_import_service.py)
  - [`tally_migration_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/services/tally_migration_service.py) (`validate_xml_no_xxe` blocks `<!DOCTYPE` & `<!ENTITY` before `ElementTree.fromstring`)
  - [`itc_views.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/gst/itc_views.py) (`GSTR2BUploadView`)
  - [`itc_reconciliation_service.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/gst/services/itc_reconciliation_service.py) (`ingest_gstr2b_excel` converted to streaming `read_only=True` with ZIP-bomb pre-check, 50,000-row ceiling, and pre-validation before `GSTR2BImport` creation)
- Verified exception responses across import and GSTR-2B APIs no longer return raw `str(e)` exception strings to HTTP clients.

---

## 3. Authentication, CSRF, CORS, Headers & Token Custody Matrix

| Security Domain | Verification Method | Result |
| :--- | :--- | :--- |
| **HttpOnly Cookie Auth & Zero Browser JWTs** | Playwright Edge E2E (`:3000` + `:8000`) + [`tests_stage1_2_auth_cookies.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounts/tests_stage1_2_auth_cookies.py) | **PASS** — `srilekh_access` verified `httpOnly=True`; `0` `eyJ` strings in `localStorage`, `sessionStorage`, `document.cookie`, or rendered DOM |
| **CSRF Origin & Token Enforcement** | Playwright Edge accidental cross-port probe (`:3124` blocked `403 CSRF Failed: Origin checking failed`), valid `:3000` (`200`), DRF `enforce_csrf_checks=True` | **PASS** |
| **Live Staging Headers & CORS Isolation** | Live HTTPS probes to `https://vouch-u3u7.onrender.com` & `https://www.srilekh.com` | **PASS** — `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`, CSP (`frame-ancestors 'none'`, `object-src 'none'`); CORS `OPTIONS` echoes allowed Vercel/staging origins and omits `Access-Control-Allow-Origin` for `https://evil.example.com` |
| **Capacitor Native Token Storage** | Source audit of [`auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts) + Test 2 in [`stage1_2_offline_auth_privacy.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/sync/stage1_2_offline_auth_privacy.test.ts) | **CONDITIONAL PASS** — `@capacitor/preferences` (`allowBackup="false"`), not Android Keystore (accurately disclosed; blocked on host Android SDK/JDK) |
| **Upload & Parser Hardening** | [`spreadsheet-parser.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/import/spreadsheet-parser.test.ts) (**9/9**) + [`tests_upload_security.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/accounting/tests_upload_security.py) (**5/5** SQLite & Neon PG) | **PASS** |
