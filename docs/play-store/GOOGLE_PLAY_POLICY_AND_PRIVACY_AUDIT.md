# SRI LEKH — GOOGLE PLAY POLICY & PRIVACY AUDIT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Audited Routes:** `/privacy-policy`, `/terms`, `/refund-policy`, `/contact`, `/pricing`, `/delete-account`, `/`, `/robots.txt`, `/sitemap.xml`

---

## 1. Privacy Policy vs. Actual Codebase Verification Matrix

| Disclosure Area | Prior Status | Codebase Reality Today | Updated Policy Status |
| :--- | :--- | :--- | :--- |
| **Browser Authentication Tokens** | **Verified FAIL** (described old JS cookies & `localStorage`) | Server-set `HttpOnly; Secure` cookies (`srilekh_access`, `srilekh_refresh`), origin-aware `SameSite`, CSRF (`csrftoken`/`X-CSRFToken`), `User.token_version` revocation, zero JS JWTs in `localStorage`/`document.cookie`. | **Verified PASS** — Updated [`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx) Sections 7 & 9. |
| **Capacitor Mobile Token Storage** | **PARTIALLY VERIFIED** | `@capacitor/preferences` (OS app-sandboxed SharedPreferences/UserDefaults), `android:allowBackup="false"`, wiped on logout & revoked via server `token_version`. Hardware Keystore not yet implemented. | **Verified PASS** — Accurately disclosed in Section 7 (`"planned native enhancement rather than an active control"`). |
| **IndexedDB Offline Data & Encryption** | **PARTIALLY VERIFIED** | `VouchOfflineDB` financial tables stored **plaintext at rest** in browser IndexedDB (`userId`/`companyId` scoped); `VouchSecurityVault` stores non-extractable Ed25519 keys. | **Verified PASS** — Plaintext-at-rest explicitly stated in Section 7 & Section 10. |
| **Standard vs. Shared-Device Logout** | Outdated | Ordinary logout preserves isolated `QUEUED`/`IN_FLIGHT`/`FAILED` outbox rows while clearing read caches & SW caches; Secure Shared-Device Logout (`forceDestroyAll`) deletes `VouchOfflineDB`, `VouchSecurityVault`, `vouch_*` keys, and caches. | **Verified PASS** — Explicitly documented in Section 10. |
| **Self-Service Account Deletion** | **Verified FAIL** (stated unavailable) | In-app (`Settings → Account Profile`) & web (`/delete-account`) password-reauthenticated permanent personal anonymization + revocation implemented; multi-user sole-owner transfer enforced (`409`). | **Verified PASS** — Documented in Section 13; statutory retention duration marked pending owner/counsel confirmation. |
| **Third-Party AI & Cloud Processors** | Accurate in Stage 1.1 | Google Gemini API (`google.genai`) for OCR, Vercel, Render, Neon PostgreSQL (`ap-southeast-1`), Redis, SMTP/Gmail default, optional S3 (`ap-south-1`), optional Cashfree GSP, international transfer notice. | **Verified PASS** — Preserved accurately in Section 8. |
| **Legal Entity / Grievance Officer / Retention SLAs** | Placeholder | Business legal entity name, physical address, Grievance Officer particulars, processor DPAs, and exact retention years remain unconfirmed placeholders. | **OWNER ACTION REQUIRED** |

---

## 2. Google Play Policy Compliance Audit

| Policy Requirement | Region / Scope Assessment | Codebase / Build Finding | Status |
| :--- | :--- | :--- | :--- |
| **Play Account Deletion Requirement** (In-App + Web URL) | Confirmed global Play policy for apps supporting account creation | Implemented `/delete-account` (`AllowAny` info + authenticated request + non-PII status receipt), linked in `PublicFooter`, `Contact`, `Privacy Policy`, `robots.ts`, `sitemap.ts`, and `Settings → Account Profile`. **Blocker:** Must be deployed live to `https://srilekh.com/delete-account` before Play Console submission. | **Verified PASS** *(Code & Local E2E)* / **BLOCKED** *(Live `srilekh.com` deploy pending approval)* |
| **Commercial & Payments Compliance (Initial Release)** | Global / India Play Payments Policy vs Pure Companion Model | [`NativeCommercialGuard`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/NativeCommercialGuard.tsx) blocks `/pricing` and `/refund-policy` (including Razorpay checkout mentions) inside Capacitor Android; [`NativeCommercialHide`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/NativeCommercialHide.tsx) removes `/pricing` and `/refund-policy` links from header/footer/contact; homepage `"Free tier available"` banner removed. Website `/pricing` & `/refund-policy` remain intact for browsers. | **Verified PASS** *(Local E2E & Simulation)* |
| **Target API Level Policy** | Confirmed Play Console requirement (`API 36` Android 16 for Aug 31, 2026+) | [`variables.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/variables.gradle) already sets `compileSdkVersion = 36` and `targetSdkVersion = 36`. | **Verified PASS** |
| **Photo & Video Permissions Policy (`READ_MEDIA_IMAGES`)** | Confirmed strict Play Store media-access restriction | `READ_MEDIA_IMAGES`, `READ_EXTERNAL_STORAGE`, and `WRITE_EXTERNAL_STORAGE` removed from [`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml) because `<input type="file">` uploads in WebView use Android's system file/photo picker cleanly without broad library read permission. *(Needs physical Android device verification.)* | **Verified PASS** *(Manifest)* / **NOT TESTED** *(Physical Android Device)* |
| **Data Safety Section Accuracy** | Mandatory Play Console submission form | Data collected: Email, optional Name, Financial/Business/Tax records, device/replica pseudonymous IDs, push tokens (if subscribed), uploaded OCR images/PDFs/bank statements; transit encrypted via HTTPS/TLS; no ads/third-party analytics SDKs (`GA`, `Mixpanel`, `Sentry` absent). | **OWNER ACTION REQUIRED** *(Play Console form entry)* |
| **Financial Features Declaration** | Mandatory Play Console declaration (`App content`) | Policy-dependent categorization: SriLekh provides B2B bookkeeping/invoicing (does NOT lend money, transmit funds, hold balances, issue credit, or provide investment advice). Owner/counsel must confirm exact Play Financial Features answers and ensure Setu/AA/Razorpay remain excluded in Android. | **OWNER ACTION REQUIRED** |

---

## 3. Public Route & Mobile Responsiveness Check

Playwright Chromium (`msedge`) viewport `390x844` verified HTTP `200` on `/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, `/delete-account`, `/robots.txt`, and `/sitemap.xml` with zero runtime page errors against the built Next.js production bundle (`57/57` routes). Live staging/production public URL deployment checks remain blocked until approved for staging/main deployment.
