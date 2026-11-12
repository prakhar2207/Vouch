# SRI LEKH — STAGE 1.2.5 ANDROID BUILD & PHYSICAL DEVICE QA REPORT

**Assessment Date:** 2026-11-12  
**Branch / Commit:** `feat/google-play-launch-readiness` @ `c160fca0`  
**Overall Gate Verdict (Gate B — Android Technical Readiness):** **PARTIALLY VERIFIED / BLOCKED** *(Unsigned Release `.aab` & Debug `.apk` compiled & uploaded cleanly in Cloud CI via JDK 21 + Android SDK 36; owner keystore signing & physical Android device QA remain blocked on owner hardware/secrets)*

---

## 1. Local Workstation vs. Cloud CI Build Capability

- **Local Windows Host:** Zero JDK (`java`, `javac`, `keytool`), zero Android SDK (`adb`), and zero release upload keystore exist locally.
- **Stage 1.2.5 Resolution (Cloud CI — [`.github/workflows/stage-verification-ci.yml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/.github/workflows/stage-verification-ci.yml)):**
  - Job `131328027030` (`Frontend Audit/Tests & Unsigned Android AAB/APK Compile (JDK 21 + SDK 36)`) ran on `ubuntu-latest` for commit `c160fca0` (`Run #43259891989`):
    - Node `22.23.4`, Temurin JDK `21`, Android SDK `compileSdkVersion = 36` / `targetSdkVersion = 36` / `minSdkVersion = 24` ([`variables.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/variables.gradle#L1-L4)).
    - `npx tsc --noEmit`: **PASS**
    - `npm test`: **45 / 45 PASS**
    - `npm audit --omit=dev`: **0 vulnerabilities**
    - `NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com npm run build`: **PASS**
    - `npx cap sync android`: Found `5` Capacitor plugins for Android (`@capacitor/app`, `@capacitor/network`, `@capacitor/preferences`, `@capacitor/splash-screen`, `@capacitor/status-bar`).
    - `./gradlew assembleDebug bundleRelease --no-daemon`: **`BUILD SUCCESSFUL in 2m 6s`** (`534 actionable tasks: 534 executed`).
    - Artifact Uploaded: **`stage-ci-android-artifacts`** (Artifact ID `13963902215`, `6,974,483` bytes, SHA-256 `4ad70761672b5e74de67858e83fbb1b3c2e8d0fb2bfc0546abb006e223ec7e7c`, containing debug `.apk` + unsigned release `.aab`).

---

## 2. Build Configuration Audit (`frontend/android/app/build.gradle`)

Observed directly in [`frontend/android/app/build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle#L1-L28):
- `applicationId "com.srilekh.app"`, `versionCode 1`, `versionName "1.0"`
- `JavaVersion.VERSION_21` (`sourceCompatibility` & `targetCompatibility`)
- `buildTypes.release`:
  - `minifyEnabled false` (no R8 obfuscation/shrinking enabled yet)
  - No `signingConfigs.release` block committed (CI builds unsigned `.aab` until owner supplies keystore secrets in GitHub Actions / local `keystore.properties`).
- [`mobile-release.yml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/.github/workflows/mobile-release.yml) already exists for release-tagged `main` workflows (`workflow_dispatch` / `v*` / `main`).

---

## 3. Physical Device Matrix & Remaining Owner Actions (`OA-03`, `OA-04`)

| Verification Item | Status | Notes |
| :--- | :--- | :--- |
| Cloud CI Debug APK + Unsigned Release AAB compile | **PASS** | Run `43259891989`, Job `131328027030`, `534` Gradle tasks |
| Release Upload Keystore Creation & `.aab` Signing | **BLOCKED (Owner)** | Owner must generate/manage Play upload keystore (`keytool`) and configure `signingConfigs.release` via env/secrets (never committed to git) |
| R8 Shrinking / ProGuard Verification (`minifyEnabled true`) | **NOT TESTED** | Pending owner test once release signing is configured |
| Physical Android Device QA (Android 8–15 handsets) | **NOT TESTED (Blocked)** | Cold start offline bootstrap, airplane-mode queue + reconnect sync, token refresh, deep-link password reset, PDF voucher share/download, camera picker, Secure Shared-Device Logout, hardware back button |
