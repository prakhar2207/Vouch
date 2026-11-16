# SRI LEKH — STAGE 1.1: PRIVACY & END-TO-END DATA FLOW AUDIT

**Audit Date:** 2026-11-12  
**Audited Page:** [`frontend/src/app/privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx)  
**Cross-Checked Codebase:** `config/settings.py`, `requirements.txt`, `render.yaml`, `apps/accounts/*`, `apps/companies/*`, `apps/audit/*`, `apps/common/*`, `apps/accounting/*`, `apps/analytics/*`, `apps/protocol/*`, `frontend/src/utils/auth.ts`, `frontend/src/lib/db/offlineDb.ts`, `frontend/src/lib/sync/sync-worker.ts`, `frontend/src/lib/crdt/*`, `frontend/src/context/CompanyContext.tsx`, `frontend/src/components/DashboardLayout.tsx`, `frontend/src/app/sw.ts`.

---

## 1. End-to-End Personal & Financial Data Inventory

| Data Category | Exact Fields / Entities Verified in Code | Storage Location(s) |
| :--- | :--- | :--- |
| **Account & Identity** (`User`, `EmailVerificationChallenge`) | `UUID`, `email`, optional `first_name`, `last_name`, `role`, salted password hash, `email_verified`, salted OTP hash (`otp_hash`), `ip_address` on email challenge, failed attempt counter (`max_attempts=5`). | PostgreSQL (prod/staging), Redis cache (OTP/rate limits), `localStorage` (`vouch_user`). |
| **Company Master** (`Company`) | Firm/legal name, `gstin`, `pan`, `state_code`, `address`, `city`, `pincode`, `email`, `phone`, `proprietor_name`, `proprietor_phone`, `bank_name`, `bank_account_number`, `bank_ifsc`, `bank_branch`, `upi_id`, uploaded `logo`/`logo_data`, `stamp`/`stamp_data`, `proprietor_signature`/`signature_data`, `is_active`, `deleted_at`. | PostgreSQL, uploaded file/media storage or DB text fields, `localStorage` (`vouch_active_company_id`, `vouch_cached_companies_list`). |
| **Accounting & Party Records** | Double-entry vouchers (`SALES`, `PURCHASE`, `RECEIPT`, `PAYMENT`, `CONTRA`, `JOURNAL`, `CREDIT_NOTE`, `DEBIT_NOTE`), ledger entries, proforma quotations, voucher attachments, party masters (name, GSTIN, state code, billing address, email, phone), B2B inbox requests. | PostgreSQL + Dexie `VouchOfflineDB` read caches & `outboxQueue`. |
| **Inventory & Documents** | Warehouses, categories, items, HSN codes, unit prices, price-list import jobs, OCR purchase bill images/PDFs (`<= 15 MB`), bank statements (`.csv`, `.xlsx`, `.xls`, `.pdf`, `.ofx`, `.qif`, `<= 15 MB`), extracted transactions. | PostgreSQL, Dexie `ocrCache`, transient transmission to Google Gemini API when OCR/AI parsing is triggered. |
| **GST & Audit Data** | GST tax calculations, GSTR summaries, uploaded GSTR-2B records, `CompanyGSTConfig` (supports Fernet encryption for credential fields), sandbox E-Way Bill / E-Invoice DB records, append-only `AuditLog` (`sequence`, `previous_hash`, `current_hash` SHA-256 chain, optional `ip_address` defaulting to `None` when omitted by callers). | PostgreSQL (encrypted backup dumps when `BACKUP_ENCRYPTION_KEY` configured). |
| **Device, Crypto & Session State** | JWT `access_token` (30m) & `refresh_token` (7d, rotated + blacklisted after rotation), `vouch_device_id`, `vouch_protocol_replica_id`, Ed25519 `AuthorizedDevice` public key (server) & non-extractable private `CryptoKey` (browser IndexedDB `VouchSecurityVault`), optional Web Push subscription endpoints. | Cookies (`access_token`, `refresh_token` — `SameSite=Lax`, non-`HttpOnly`, `Secure` on HTTPS), `localStorage` (`vouch_access_token`, `vouch_refresh_token`), Capacitor `Preferences`, IndexedDB `VouchSecurityVault`. |

---

## 2. Third-Party Processors, Cloud Infrastructure & Analytics Audit

| Service / Package | Verified Behavior in Code | Cross-Border Note | Disclosed in Updated `/privacy-policy`? |
| :--- | :--- | :--- | :--- |
| **Vercel** | Serves Next.js frontend / CDN assets. | Global/edge delivery possible. | Yes (Section 8) |
| **Render** (`render.yaml`) | Hosts Django REST API (`vouch-staging-api`), Celery worker (`vouch-staging-worker`), Celery beat (`vouch-staging-beat`). | Hosting region outside India unless explicitly provisioned in-country. | Yes (Section 8) |
| **Neon Cloud PostgreSQL** | Managed PostgreSQL; observed endpoint configuration points to AWS Singapore (`ap-southeast-1`). | Cross-border (`ap-southeast-1`). | Yes (Section 8) |
| **Redis** | `CELERY_BROKER_URL=REDIS_URL`, OTP/rate cache. | Follows managed Redis host region. | Yes (Section 8) |
| **Google Gemini API (`google.genai`)** | `GeminiClientProvider` transmits user-uploaded purchase bill OCR images/PDFs (`apps/accounting/services/ocr_service.py`), scanned bank statement PDFs/images (`bank_statement_service.py`), and AI price-list imports to Google Gemini models when API key configured (with PyPDF local fallback). | Transmitted to Google API endpoints outside India unless region-pinned. | **Yes — Added in Stage 1.1 (Section 8)** *(previously missing from Step 1 PDF)* |
| **SMTP / Gmail** (`config/settings.py`) | Default `EMAIL_HOST='smtp.gmail.com'`, `DEFAULT_FROM_EMAIL='SriLekh <admin@srilekh.com>'`, `EMAIL_REPLY_TO='support@srilekh.com'`. | External mail relay. | Yes (Section 8) |
| **Amazon S3 (`boto3`)** | Optional encrypted backup archive upload if `BACKUP_S3_BUCKET` is configured (`AWS_S3_REGION_NAME='ap-south-1'`). | `ap-south-1` (Mumbai) when default preserved. | Yes (Section 8) |
| **Cashfree GSP / Mock GST** | Defaults to `MockGSTProvider` & sandbox mode; `GSPProvider.search_taxpayer` uses Cashfree only if non-`MOCK` key configured (`eway_bill` / `einvoice` methods still delegate to `mock_fallback`). | External API when live key configured. | Yes (Section 8) |
| **Local ML (`analytics/services/ai_service.py`)** | Uses `pandas`, `numpy`, `scikit-learn` (`KMeans`, `LinearRegression`) locally on backend — does NOT send analytics data to Gemini. | Runs in-app on backend server. | Accurate (no overclaim) |
| **Third-Party Analytics / Trackers** | No Google Analytics, Mixpanel, PostHog, Meta Pixel, or Sentry SDK bundled in `frontend/package.json` or `requirements.txt`. | None. | Explicitly stated in Section 5 |

---

## 3. Browser Storage, Offline Isolation, Tenant Switch & Logout Data Flow

### Verified Trace (`auth.ts`, `offlineDb.ts`, `sync-worker.ts`, `CompanyContext.tsx`, `DashboardLayout.tsx`, `sw.ts`)

1. **Tenant Switch (`CompanyContext.switchCompany`):**
   - Awaits `safePurgeTenantData(prevId)` in `offlineDb.ts`, purging previous tenant's cached read tables (`syncedVouchers`, `syncedLedgers`, `syncedProducts`, `masters`, bank caches, etc.) while keeping its `outboxQueue`/`operationLog` isolated by `companyId`.
   - `sync-worker.ts` enforces strict company guard: skips any outbox/protocol item whose `companyId !== activeCompanyId`. *(Verified by test case 3 in `offline-sync.test.ts`.)*
2. **Logout (`DashboardLayout.handleLogout` & `auth.removeTokens`):**
   - Awaits `safePurgeTenantData()` (no `targetCompanyId`, `forceDestroyAll` false): deletes cached tenant read tables, synced rows, `ocrCache`, and `inboxQueue`, **while intentionally preserving unsynchronized `QUEUED` / `IN_FLIGHT` / `FAILED` rows in `outboxQueue` / `operationLog` tagged by `userId` and `companyId`** so offline work is not silently lost.
   - `sync-worker.ts` enforces user guard: blocks User B from pushing User A's queued outbox items (`Refusing to push transaction ... queued by user user-A`). *(Verified by test case 4 in `offline-sync.test.ts`.)*
   - Deletes `srilekh-pages-cache`, sends `{ type: "CLEAR_SESSION_CACHES" }` to Service Worker, removes JWT cookies/localStorage/Capacitor keys, and redirects to `/login`.
3. **Important Privacy Nuance Disclosed in Section 10 (Remediated in Stage 1.1):**
   - Because unsynchronized outbox payloads remain in `VouchOfflineDB` across logout (blocked from sync/view by another user, but present in browser IndexedDB), shared-computer users are explicitly warned not to create offline drafts on shared devices or to clear browser site data after logout.
   - Because `access_token` and `refresh_token` are accessible to client JS (non-`HttpOnly` cookies + `localStorage` + Capacitor `Preferences`), Section 7 & Section 9 accurately state this architecture rather than falsely claiming `HttpOnly`-only cookie isolation.

---

## 4. Retention, Deletion & Security Claims Accuracy

- **Company Archival vs Permanent User Deletion (`Section 13`):** Verified `CompanyViewSet.destroy` (`apps/companies/views.py`) requires password re-authentication and soft-deletes (`is_active=False`, `deleted_at=now()`). Only `superadmin` views perform permanent hard deletion. No self-serve user account delete button/endpoint exists in `apps/accounts/urls.py` or UI — accurately disclosed in updated `/privacy-policy` Section 13.
- **Backups (`Section 11` & `Section 13`):** `DatabaseBackupService.perform_backup` compresses PostgreSQL dumps, optionally encrypts with AES MultiFernet (`BACKUP_ENCRYPTION_KEY`), optionally uploads to S3, and prunes local archives older than `BACKUP_RETENTION_DAYS` (`7` days default). Deleted live DB records persist in historical encrypted backups until rotation expires — accurately disclosed.
- **Log Masking & Hash Chain (`Section 5` & `Section 7`):** `PIIMaskingFilter` scrubs GSTIN, PAN, bank account numbers, JWTs, and private keys in logs; `AuditLog` is append-only (`PermissionDenied` on update/delete) with SHA-256 `previous_hash` -> `current_hash` chaining. No unverified ISO 27001, SOC 2, or India-only residency claims appear.
