# SRI LEKH — STAGE 4.15 NOTIFICATION AUTHORIZATION & SECURITY REPORT

**Environment:** Live Render Staging (`https://vouch-u3u7.onrender.com`) & PostgreSQL `test_neondb_staging`  
**Commit SHA:** `c15a64fb2793a8d1abc762997a1202d73b4b92ae` (`fix/stage4-12-day6-remediation`)  
**Database Fingerprint:** `6f4741bdaaf4` (`neondb_staging`)  
**Execution Timestamp:** `2026-11-12 14:19–15:09 IST`

---

## Verdict: **PASS (Remediated, Tested on PostgreSQL & Verified Live on `c15a64fb`)**

---

## 1. Original Defect & Root Cause

- **Affected Component:** `_get_target_company()` in [apps/notifications/views.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/views.py), called by `EmailDeliveryLogListView`, `EmailDeliveryLogRetryAPIView`, and `NotificationPreferencesAPIView`.
- **Root Cause:** When an explicit `company_id` query parameter or `X-Company-ID` header identified a tenant the authenticated user did **not** belong to, `_get_target_company()` failed the `UserCompany.objects.filter(...)` check and silently fell through to `UserCompany.objects.filter(user=request.user).first()`, returning the caller's own company logs (`HTTP 200`) instead of rejecting the unauthorized request (`HTTP 403` / `404`). Additionally, passing a non-UUID `company_id` risked unhandled `ValidationError` on UUID queries.

---

## 2. Code Remediation Implemented ([apps/notifications/views.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/notifications/views.py))

Implemented `_resolve_authorized_company(request)` and updated `NotificationPreferencesAPIView` (`GET`, `PATCH`), `EmailDeliveryLogListView` (`GET`), and `EmailDeliveryLogRetryAPIView` (`POST`):
- Rejects conflicting `X-Company-ID` header vs `?company_id=` query param with `400 Bad Request`.
- Validates UUID format safely, returning `400 Bad Request` on invalid UUIDs.
- When explicit `company_id` is supplied:
  - Active membership exists -> returns `(company, None)`.
  - Company exists without active membership -> returns **`403 Forbidden`** (`"Permission denied: You do not belong to the requested company."`) with zero silent fallback and zero tenant log exposure.
  - Company UUID does not exist -> returns **`404 Not Found`** (`"Company not found."`).
- When omitted: preserves safe default membership selection (`order_by('id').first()`), returning `400` if the user has no active company membership.

---

## 3. PostgreSQL & Live Render Verification Results

### PostgreSQL Test Suite (`test_neondb_staging`, `task-50430`)
- `apps.notifications.tests_stage4_15_auth`: **`6 / 6 OK`**
- `apps.notifications.tests`: **`16 / 16 OK`**

| Request Scenario | Expected HTTP | Observed PG Test | Observed Live Render (`c15a64fb`) | Pass/Fail |
|---|---|---|---|---|
| Unauthenticated `GET /api/v1/notifications/logs/` | `401` | `401` | `401` (prior audit) | **PASS** |
| Authenticated `OWNER` / `ADMIN` same-tenant `logs/` | `200` | `200` | `200` (`count: 50`) | **PASS** |
| Authenticated `EMPLOYEE` / `VIEWER` / `CA` same-tenant `logs/` | `403` | `403` (`403` for all 3) | `403` (`viewer_s414`) | **PASS** |
| Explicit unauthorized `?company_id=<Garodia>` (`Precision Agro` owner) | `403` (zero fallback) | `403` | **`403 Forbidden`** (`"Permission denied: You do not belong to the requested company."`) | **PASS** |
| Explicit unauthorized `X-Company-ID` header / `preferences/` | `403` | `403` | Covered by PG suite | **PASS** |
| Unknown company UUID `?company_id=<random>` | `404` | `404` | **`404 Not Found`** (`"Company not found."`) | **PASS** |
| Malformed `?company_id=not-a-uuid` | `400` | `400` | **`400 Bad Request`** (`"Invalid company ID format."`) | **PASS** |
| Conflicting `X-Company-ID` vs `?company_id=` | `400` | `400` | Covered by PG suite | **PASS** |
| No `company_id` (single & multi-tenant user / orphan user) | `200` / `400` | `200` / `200` / `400` | Covered by PG suite | **PASS** |
| Cross-tenant retry `POST /logs/<other_id>/retry/` (explicit & implicit) & RBAC | `403` / `404` / `403` | `403` / `404` / `403` | Covered by PG suite & Stage 4.14 `404` | **PASS** |
