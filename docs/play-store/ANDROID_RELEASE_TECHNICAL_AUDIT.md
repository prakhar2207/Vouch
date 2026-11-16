# SRI LEKH — ANDROID RELEASE TECHNICAL AUDIT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Android Package / Application ID:** `com.srilekh.app`  
**App Name:** `SriLekh` (`strings.xml` & `capacitor.config.ts`)

---

## 1. Capacitor Architecture & Build Configuration Audit

| Configuration Area | Audited Value (`frontend/android/` & `capacitor.config.ts`) | Finding & Status |
| :--- | :--- | :--- |
| **Application ID & Version** | `applicationId "com.srilekh.app"`, `versionCode 1`, `versionName "1.0"` ([`build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle)) | **Verified PASS** (Must increment `versionCode` for any subsequent Play Console upload). |
| **SDK Targets (`variables.gradle`)** | `minSdkVersion = 24` (Android 7.0), `compileSdkVersion = 36`, `targetSdkVersion = 36` (Android 16) | **Verified PASS** — Meets Google Play 2026 API 36 requirement cleanly. |
| **Hosting Model (`capacitor.config.ts`)** | Remote WebView `server.url: 'https://srilekh.com/dashboard'`, `cleartext: false`, `androidScheme: 'https'`, `errorPath: 'index.html'` (`mobile-shell`). | **PARTIALLY VERIFIED** — Relies on live `https://srilekh.com/dashboard`; staging URLs are **not** embedded. `mobile-shell/index.html` provides branded offline fallback when unreachable. |
| **WebView `allowNavigation` Scope** | Removed `localhost`, `127.0.0.1`, `vouch-pi-one.vercel.app`, and `*.vercel.app`; restricted to `srilekh.com`, `*.srilekh.com`, `api.srilekh.com`, and WhatsApp share domains; re-synced via `npx cap sync android` (`exit 0`). | **Verified PASS** |
| **Backup Extraction Hardening** | Changed `android:allowBackup="true"` -> `android:allowBackup="false"` in [`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml). | **Verified PASS** |
| **Permissions Audit (`READ_MEDIA_IMAGES`)** | Removed unnecessary `READ_MEDIA_IMAGES`, `READ_EXTERNAL_STORAGE`, and `WRITE_EXTERNAL_STORAGE` from [`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml); retained `INTERNET`, `ACCESS_NETWORK_STATE`, `CAMERA` (`required="false"`). | **Verified PASS** *(Manifest)* / **NOT TESTED** *(Physical Android camera & file picker QA)* |
| **WebView Hardening & Back Button (`MainActivity.java`)** | Updated [`MainActivity.java`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/java/com/srilekh/app/MainActivity.java): changed `settings.setAllowFileAccess(true)` -> `false` (retaining `setAllowContentAccess(true)` for content URI uploads) and added `OnBackPressedCallback` so hardware Back navigates WebView history before closing. | **Verified PASS** *(Source inspection)* / **NOT TESTED** *(No JDK/Gradle compiler on host)* |
| **R8 / ProGuard & Release Signing** | `buildTypes.release.minifyEnabled false` in [`build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle); no `signingConfigs.release` or keystore file in repository (correctly excluded from git). | **OWNER ACTION REQUIRED / BLOCKED** *(Requires keystore + Gradle verification on JDK/Android SDK build host)* |
| **Secrets & Ad/Analytics SDKs** | Zero hardcoded API secrets, zero ad SDKs (`ADMOB`), zero `google-services.json`, zero third-party analytics SDKs in `android/` and `package.json`. | **Verified PASS** |

---

## 2. Android Build, Signing & Physical Device Verification Status

| Requirement | Environment Reality | Status |
| :--- | :--- | :--- |
| **Gradle `.aab` Build (`./gradlew bundleRelease`)** | `java`, `keytool`, `adb`, Android SDK (`%LOCALAPPDATA%\Android\Sdk`), and JDK are **absent** on this Windows host (`Test-Path` -> `False`). | **BLOCKED (No JDK / Android SDK Build Host)** |
| **Release Upload Keystore & Signing** | No release `.jks`/`.keystore` or `keystore.properties` exists on host (never generate/commit dummy production release keystores without owner custody). | **OWNER ACTION REQUIRED** |
| **Physical Android Device Testing** (Fresh install, Login/Logout, Restart, Token Refresh, Password Reset, Company Switch, Offline/Reconnect Sync, Shared-Device Logout, PDF Downloads, Back Button, Wi-Fi/Cellular switch) | Physical Android hardware and `adb` unavailable. Web-rendered mobile viewport checks (`390x844`) & simulated `Capacitor.isNativePlatform()` UI guard checks do **not** substitute for real Android WebView/device testing. | **NOT TESTED (No Physical Android Device)** |

---

## 3. Exact Owner / Release Engineer Instructions to Build Signed `.aab`

On a developer workstation or CI runner with **JDK 21** + **Android SDK (API 36 Build Tools & Platform)**:

1. Generate upload keystore securely outside the repository (`keytool -genkey -v -keystore srilekh-upload.jks -keyalg RSA -keysize 2048 -validity 10000 -alias srilekh-upload`) and configure local `frontend/android/keystore.properties` (git-ignored) + `signingConfigs.release` in `frontend/android/app/build.gradle`.
2. Ensure `https://srilekh.com` has been updated with the approved production release containing `/delete-account`, updated `/privacy-policy`, and `NativeCommercialGuard` / `NativeCommercialHide`.
3. Run:
   ```bash
   cd frontend
   npx cap sync android
   cd android
   ./gradlew clean bundleRelease
   ```
4. Install release build cleanly onto a physical Android device (Android 8–15), verify camera/file picker `<input type="file">`, PDF DownloadManager (`Environment.DIRECTORY_DOWNLOADS`), hardware back button, offline fallback (`mobile-shell/index.html`), logout revocation, and verify ZERO pricing/checkout links are reachable before uploading `app-release.aab` to Google Play Console Internal Testing first.
