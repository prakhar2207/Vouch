# SRI LEKH — STAGE 1.2.4 ANDROID RELEASE REPORT

**Assessment Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Application Identity:** `com.srilekh.app` / `SriLekh` (`versionCode 1`, `versionName "1.0"`)  
**Overall Gate Status (Gate B):** **BLOCKED / NOT TESTED** *(Manifest, Transport & Offline Bootstrap Hardened & Synced; JDK 21, Android SDK, Release Signing, R8 Execution & Device QA Blocked on Host)*

---

## 1. Host Environment & Build Capability Inspection

Verified via PowerShell `Get-Command`:
- `java`, `javac`, `keytool`, `adb`, `gradle`: **`MISSING`**
- `%LOCALAPPDATA%\Android\Sdk` / `Program Files\Java`: **absent**
- Keystore secrets / `keystore.properties`: **intentionally absent from git**
- Docker Desktop CLI (`docker.exe`) installed, daemon/WSL `docker-desktop` `Stopped`; not used for Android SDK compilation.

**Verified Execution Command:** `cd frontend && npx cap sync android` -> **`exit 0`** (`0.124s`), syncing `mobile-shell` web assets and 5 Capacitor plugins (`@capacitor/app@8.1.2`, `@capacitor/network@8.0.1`, `@capacitor/preferences@8.0.1`, `@capacitor/splash-screen@8.0.2`, `@capacitor/status-bar@8.0.4`).

**Commands NOT Executed (`NOT TESTED / BLOCKED`):** `./gradlew assembleDebug`, `./gradlew bundleRelease`, signed `.aab` output verification, R8 shrinking compilation, `adb` install/logcat, and all physical Android device matrix cases.

---

## 2. Stage 1.2.4 Code Findings & Remediation

1. **Fixed Offline Cold-Start Shell Auth Detection ([`mobile-shell/index.html`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/mobile-shell/index.html#L161-L180)):**
   - **Defect Found in Stage 1.2.4:** `navigateToApp()` still checked `localStorage.getItem("vouch_access_token") || localStorage.getItem("access_token")`, which Stage 1.2 removed in favor of `vouch_session_meta` + `@capacitor/preferences`, causing offline cold-starts via `mobile-shell/index.html` to misreport signed-in users as unauthenticated.
   - **Fix Applied:** Converted `navigateToApp()` to `async` checking `localStorage.getItem("vouch_session_meta")` (`mode === "token"` or `userId`) and `window.Capacitor.Plugins.Preferences.get({ key: "vouch_access_token" })`, then re-synced cleanly via `npx cap sync android`.
2. **Release Minification & Signing Config Gap Confirmed ([`build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle#L23-L28), [`mobile-release.yml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/.github/workflows/mobile-release.yml#L50-L56)):**
   - [`build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle#L23-L28) currently sets `minifyEnabled false` and has no `signingConfigs.release` block; CI workflow `.github/workflows/mobile-release.yml` runs `./gradlew bundleRelease || ./gradlew bundle` without passing keystore secrets.
   - Because JDK/Android SDK are unavailable here, `minifyEnabled` was **not** flipped blindly without compiler verification; [`proguard-rules.pro`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/proguard-rules.pro) already holds Capacitor/Bridge keep rules ready for verification on a JDK 21 + Android SDK host.

---

## 3. Hardened Android Configuration Summary

| Control | Audited File | Verified Value |
| :--- | :--- | :--- |
| **SDK Levels** | [`variables.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/variables.gradle) | `minSdkVersion 24`, `compileSdkVersion 36`, `targetSdkVersion 36` |
| **Backup & Cleartext Block** | [`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml) | `android:allowBackup="false"`, `android:usesCleartextTraffic="false"`, `@xml/network_security_config`, storage/media permissions removed |
| **Trust Anchors** | [`network_security_config.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/res/xml/network_security_config.xml) | `cleartextTrafficPermitted="false"`, system CAs only |
| **Origin Allowlist** | [`capacitor.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/capacitor.config.ts) | `url: 'https://srilekh.com/dashboard'`, `cleartext: false`, `allowNavigation: ['srilekh.com', '*.srilekh.com', 'api.srilekh.com']` |
| **WebView Hardening** | [`MainActivity.java`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/java/com/srilekh/app/MainActivity.java) | `setAllowFileAccess(false)`, `setAllowContentAccess(true)`, `OnBackPressedCallback`, DownloadManager cookie pass-through |
| **Native Token Custody** | [`auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts) | `@capacitor/preferences` (app-private sandbox, not hardware Android Keystore; disclosed in `/privacy-policy`) |
