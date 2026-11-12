# SRI LEKH — ANDROID BUILD AND SIGNING CERTIFICATION

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Package ID / App Name:** `com.srilekh.app` / `SriLekh`  
**Build & Runtime Classification:** **BLOCKED / NOT TESTED** *(Configuration Hardened in Source; Build Compiler & Physical Hardware Unavailable)*

---

## 1. Host Environment Tooling Verification

Direct command verification on the current Windows host confirmed all Android compilation and device-testing prerequisites are absent:
- `java`, `javac`, `keytool`, `adb`: **not found (`empty`)**
- Android SDK / JDK install directories: **not present**
- Upload keystore (`keystore.properties`, `.jks` / `.keystore`): **not present in repository (intentionally excluded from git)**

Accordingly, `./gradlew bundleRelease`, R8 bytecode shrinking execution, APK/AAB installation, and physical device QA were **not executed** and are explicitly reported as **BLOCKED / NOT TESTED**.

---

## 2. Configuration & Manifest Hardening Completed in Stage 1.2.3

| Component | Change & Audited Value | Status |
| :--- | :--- | :--- |
| **[`variables.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/variables.gradle)** | `minSdkVersion = 24`, `compileSdkVersion = 36`, `targetSdkVersion = 36` (Android 16) | Verified in source |
| **[`AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml)** | `android:allowBackup="false"`, `android:usesCleartextTraffic="false"`, `android:networkSecurityConfig="@xml/network_security_config"`; removed `READ_MEDIA_IMAGES` and external storage permissions | Verified in source |
| **[`network_security_config.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/res/xml/network_security_config.xml)** | Created XML forcing `cleartextTrafficPermitted="false"` and system-CA trust anchors (`<certificates src="system" />`) | Verified in source |
| **[`capacitor.config.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/capacitor.config.ts)** | Restricted `allowNavigation` strictly to `['srilekh.com', '*.srilekh.com', 'api.srilekh.com']` (`npx cap sync android` `exit 0` -> synced to `assets/capacitor.config.json`) | Verified via `cap sync` |
| **[`MainActivity.java`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/java/com/srilekh/app/MainActivity.java)** | `settings.setAllowFileAccess(false)`, `setAllowContentAccess(true)`, `OnBackPressedCallback` navigation handling | Verified in source |
| **[`build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle) & [`proguard-rules.pro`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/proguard-rules.pro)** | Kept `minifyEnabled false` untouched to avoid breaking Capacitor without a Gradle/R8 compiler; added safe keep rules for `com.srilekh.app.**`, `com.getcapacitor.**`, `@JavascriptInterface`, and `@PluginMethod` in `proguard-rules.pro` for when R8 is enabled on the build host | Verified in source |

---

## 3. Mandatory Owner / CI Build-Host Steps Required Before Play Release

On a runner/workstation with **JDK 21** + **Android SDK (API 36)**:
1. Provision owner-custodied upload keystore outside git and configure `frontend/android/keystore.properties` + `signingConfigs.release`.
2. Run `cd frontend && npx cap sync android && cd android && ./gradlew clean bundleRelease`.
3. Optionally enable `minifyEnabled true` + test R8 shrink against the keep rules in `proguard-rules.pro`.
4. Verify full physical Android device QA matrix (fresh install, cold/warm restart, session persistence, token refresh, password reset link handling, company switch, offline queue creation + reconnect sync, Secure Shared-Device Logout, camera/file upload picker, PDF DownloadManager output, Wi-Fi <-> cellular handoff, and hardware Back navigation).
