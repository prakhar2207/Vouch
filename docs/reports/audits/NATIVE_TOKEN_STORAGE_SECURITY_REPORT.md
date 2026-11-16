# SRI LEKH — NATIVE TOKEN STORAGE & ANDROID SECURITY REPORT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Scope:** Native Android Capacitor token storage ([`auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts)), WebView surface ([`MainActivity.java`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/java/com/srilekh/app/MainActivity.java)), manifest/network transport ([`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml), [`network_security_config.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/res/xml/network_security_config.xml)), and [`capacitor.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/capacitor.config.ts).

---

## 1. Current Architecture & Controls Verified

1. **Browser vs. Capacitor Separation ([`auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts)):**
   - **Web Browser Mode:** Zero JWT strings are persisted in `localStorage`, `sessionStorage`, or JS cookies (`document.cookie`); sessions rely exclusively on server-set `HttpOnly; Secure` cookies + `X-CSRFToken`.
   - **Capacitor Native Mode (`isCapacitorNative()`):** Access/refresh Bearer tokens are kept in process memory (`inMemoryNativeAccessToken`, `inMemoryNativeRefreshToken`) and mirrored via `@capacitor/preferences` (`syncCapacitorPreference`, `hydrateNativeTokens`). Both keys are explicitly cleared on `removeTokens()`.
2. **Android App Sandbox & Transport Controls Implemented:**
   - [`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml):
     - `android:allowBackup="false"` prevents `adb backup` or Google cloud auto-backup extraction of app-private `Preferences` XML files and WebView storage.
     - Added `android:usesCleartextTraffic="false"` and `android:networkSecurityConfig="@xml/network_security_config"`.
   - [`network_security_config.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/res/xml/network_security_config.xml):
     - Enforces `cleartextTrafficPermitted="false"` globally and restricts trusted roots to system CAs (`<certificates src="system" />`), blocking user-installed CAs in release builds.
   - [`capacitor.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/capacitor.config.ts):
     - Restricted `server.allowNavigation` strictly to first-party hosts (`srilekh.com`, `*.srilekh.com`, `api.srilekh.com`), removing third-party WhatsApp web domains (`api.whatsapp.com`, `wa.me`, `web.whatsapp.com`) so third-party origins cannot open inside the privileged Capacitor Bridge WebView and instead hand off externally via OS intents. Re-synced via `npx cap sync android` (`exit 0`).
   - [`MainActivity.java`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/java/com/srilekh/app/MainActivity.java):
     - Enforces `settings.setAllowFileAccess(false)` while keeping `setAllowContentAccess(true)` for system file-picker content URIs, and attaches an `OnBackPressedCallback` handler.
3. **Server-Side Revocation Safety Net:**
   - Even if native device storage were compromised prior to logout, server-side logout, shared-device logout, password reset, and account deletion increment `User.token_version` and blacklist outstanding refresh tokens (`revoke_user_tokens`), immediately rejecting stale Bearer tokens with `401 Unauthorized`.

---

## 2. Explicit Limitation: Hardware-Backed Android Keystore Encryption

- **Truthful Status:** Native Bearer tokens on Capacitor Android still rest in `@capacitor/preferences` (Android OS app-private `SharedPreferences`), **not** encrypted via Android Keystore / `EncryptedSharedPreferences`.
- **Why Not Installed Blindly in Stage 1.2.3:** The current Windows build host lacks JDK (`java`, `javac`, `keytool`) and the Android SDK (`adb`), so any third-party native Capacitor Keystore/SecureStorage plugin could **not** be Java/Kotlin-compiled, R8-verified, or device-tested on this machine. Per release safety rules, uncompilable native Gradle plugins must not be claimed as hardware-backed security.
- **Public Disclosure Accuracy:** [`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx) explicitly states that Capacitor stores Bearer tokens in OS app-sandboxed storage (`@capacitor/preferences`) with OS backup disabled, and describes hardware Keystore encryption accurately as a planned enhancement rather than an active control.
- **Recommended Follow-Up Before Play Production Scale:** On an Android SDK/JDK build host, evaluate migrating native token custody to Android Keystore-backed `EncryptedSharedPreferences` and test token migration across app updates on physical Android 8–15 devices.
