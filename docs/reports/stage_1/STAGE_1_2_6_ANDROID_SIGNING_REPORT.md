# SRI LEKH — STAGE 1.2.6 ANDROID RELEASE SIGNING & R8/PROGUARD VERIFICATION REPORT

**Assessment Date:** 2026-11-12  
**Target Package:** `com.srilekh.app`  
**CI Compilation Status:** Certified (`BUILD SUCCESSFUL in 2m 6s`, 534 tasks, JDK 21 + Android SDK 36)  
**Certification Verdict:** **OWNER APPROVAL REQUIRED / PARTIALLY VERIFIED (OA-03)**  

---

## 1. Executive Summary

In Stage 1.2.5 and Stage 1.2.6, the Android build pipeline was migrated to modern tooling (Java 21, Android SDK 36, Gradle 8.11.1, AGP 8.7.2). Cloud CI verified the clean compilation of both the Debug APK (`app-debug.apk`) and the Release App Bundle (`app-release.aab`).

However, the compiled release `.aab` is currently **unsigned** because:
1. Google Play policies mandate that every published App Bundle must be digitally signed with the developer's dedicated Upload Key.
2. The workstation lacks Java/Keytool binaries, and the GitHub repository has 0 repository secrets configured.
3. Creating an arbitrary, untracked keystore without owner custody violates Google Play key management policies and risks permanently locking the developer out of future Play Store updates.

This report establishes the complete signing specification, ProGuard/R8 analysis, and the automated GitHub Actions workflow to enable zero-leak owner signing.

---

## 2. Cloud CI Compilation Proof

In `.github/workflows/stage-verification-ci.yml`, the Android build task executed cleanly under Ubuntu LTS:
```bash
- uses: actions/setup-java@v5
  with:
    distribution: 'temurin'
    java-version: '21'

- name: Sync Capacitor & Compile Android Debug APK + Release AAB
  working-directory: frontend
  run: |
    npx cap sync android
    cd android
    chmod +x gradlew
    ./gradlew assembleDebug bundleRelease --no-daemon
```

### Build Telemetry:
- **Gradle Tasks:** `534 actionable tasks: 534 executed`
- **Build Duration:** `2m 6s`
- **Output Artifacts:**
  - `frontend/android/app/build/outputs/apk/debug/app-debug.apk` (~5.6 MB)
  - `frontend/android/app/build/outputs/bundle/release/app-release.aab` (~4.8 MB)
- **Status:** Android compilation and asset bundle generation are **100% VERIFIED**.

---

## 3. ProGuard / R8 Configuration & Shrinking Analysis

Inspection of [`frontend/android/app/build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle#L23-L28):
```groovy
buildTypes {
    release {
        minifyEnabled false
        proguardFiles getDefaultProguardFile('proguard-android.txt'), 'proguard-rules.pro'
    }
}
```

### Architectural Analysis:
1. **Why `minifyEnabled false` is the Correct Choice for Release v1.0:**
   - SriLekh is a hybrid application powered by Capacitor. The core business logic, UI, and accounting computations reside in compiled JavaScript running within the Android System WebView.
   - The native layer consists solely of Capacitor runtime plugins (`@capacitor/core`, `@capacitor/preferences`, `@capacitor/app`, `@capacitor/haptics`, `@capacitor/splash-screen`).
   - Enabling aggressive R8 code shrinking (`minifyEnabled true`) on Capacitor projects strips Java reflection classes, callback interfaces, and bridge methods required by the JavaScript-to-Native bridge, frequently causing catastrophic silent crashes when invoking native plugins on physical devices.
   - The total AAB bundle size is already extremely lean (~4.8 MB), well below Google Play's 150 MB download limit.
2. **Recommendation:**
   - Maintain `minifyEnabled false` for initial Google Play launch.
   - Any future activation of R8 must include comprehensive keep rules for `com.getcapacitor.**`, `androidx.security.**`, and Cordova plugin bindings, followed by physical device regression testing.

---

## 4. Keystore Generation Specification for Account Owner

The account owner must generate the official upload key on a secure workstation.

### Step 1: Execute `keytool` Command
Open Terminal or PowerShell (with JDK installed) and run:
```bash
keytool -genkeypair \
  -v \
  -keystore srilekh-release-key.jks \
  -alias srilekh-key-alias \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -storetype JKS
```

*When prompted:*
- **What is your first and last name?** Enter company/developer name (e.g., `SriLekh Release Admin`).
- **What is the name of your organizational unit?** `Engineering`.
- **What is the name of your organization?** `SriLekh`.
- **City / State / Country:** Enter your registered business location (`IN`).
- **Passphrase:** Choose a strong password (record securely in your password vault).

### Step 2: Convert Keystore to Base64 (For CI Secrets)
```bash
# On macOS / Linux:
base64 -w 0 srilekh-release-key.jks > srilekh_keystore_base64.txt

# On Windows PowerShell:
[Convert]::ToBase64String([IO.File]::ReadAllBytes("srilekh-release-key.jks")) | Out-File -Encoding ASCII srilekh_keystore_base64.txt
```

> [!CAUTION]
> **CRITICAL BACKUP REQUIREMENT**: Store `srilekh-release-key.jks` and its passphrase in a secure offline vault (e.g., 1Password, Bitwarden, or encrypted USB). If this key is lost, Google Play will reject all future app updates unless Google Play App Signing key reset is requested with identity verification.

---

## 5. Automated CI Signing Workflow Integration

Once the owner configures the 4 GitHub Secrets in repository `prakhar2207/Vouch`:
- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

The GitHub Actions release workflow `.github/workflows/mobile-release.yml` uses the following signing step to emit an officially signed release bundle:

```yaml
      - name: Sign Android Release App Bundle
        uses: r0adkll/sign-android-release@v1
        id: sign_app
        with:
          releaseDirectory: frontend/android/app/build/outputs/bundle/release
          signingKeyBase64: ${{ secrets.ANDROID_KEYSTORE_BASE64 }}
          alias: ${{ secrets.ANDROID_KEY_ALIAS }}
          keyStorePassword: ${{ secrets.ANDROID_KEYSTORE_PASSWORD }}
          keyPassword: ${{ secrets.ANDROID_KEY_PASSWORD }}

      - name: Upload Signed Google Play AAB Artifact
        uses: actions/upload-artifact@v4
        with:
          name: google-play-signed-app-bundle
          path: ${{ steps.sign_app.outputs.signedReleaseFile }}
```

---

## 6. Verification Criteria for Closure of OA-03

To mark **OA-03** formally closed:
1. GitHub Actions workflow compiles and signs the release `.aab` using the owner secrets.
2. Binary verification confirms valid signature:
   ```bash
   jarsigner -verify -verbose -certs app-release.aab
   ```
   **Expected output:** `jar verified.` with the owner's certificate DN.
3. Bundletool validates manifest and packaging:
   ```bash
   bundletool validate --bundle=app-release.aab
   ```
