# SRI LEKH — STAGE 1.2.8 ANDROID RELEASE SIGNING & PHYSICAL DEVICE QA CERTIFICATION

**Assessment Date:** 2026-11-13  
**Target Package:** `com.srilekh.app`  
**CI Compilation Status:** Certified (`BUILD SUCCESSFUL in 2m 6s`, 534 tasks, JDK 21 + Android SDK 36)  
**Certification Verdict:** **OWNER APPROVAL REQUIRED / BLOCKED (OA-03 & OA-04)**  

---

## 1. Executive Summary

This report evaluates Android release readiness across three core dimensions:
1. **Compilation & Build Automation:** **VERIFIED PASS.** Cloud CI compiles Debug APK (`app-debug.apk`) and Release App Bundle (`app-release.aab`) with zero errors using modern Android SDK 36, Java 21, and Gradle 8.11.1.
2. **Release Digital Signing (OA-03):** **OWNER ACTION REQUIRED.** Google Play mandates that all published App Bundles must be digitally signed with the developer's upload key. The GitHub repository currently contains 0 secrets. Creating an arbitrary keystore without owner custody violates Google Play key management policies.
3. **Physical Hardware QA (OA-04):** **BLOCKED PENDING HARDWARE.** The local workstation has no physical Android handsets, emulator instances, or `adb` installed.
4. **Native Token Security (OA-11):** **DEFERRED TO v1.1.** The application uses `@capacitor/preferences` with `android:allowBackup="false"` and `android:usesCleartextTraffic="false"`, backed by local WebCrypto `AES-GCM-256` payload encryption, as accurately disclosed in the published privacy policy. Migrating to hardware Keystore without a physical testing device is an unverified regression hazard; it is accepted as residual risk for v1.0 and scheduled for v1.1.

---

## 2. Android Build & ProGuard / R8 Analysis

### 2.1 Build Configuration ([`frontend/android/app/build.gradle`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/build.gradle))
- `compileSdk`: 36
- `minSdkVersion`: 24 (Android 7.0+)
- `targetSdkVersion`: 35 / 36 (Complies with Google Play August 2024+ target API requirements)
- `versionCode`: 1
- `versionName`: `"1.0"`
- `compileOptions`: Java 21 compatibility (`JavaVersion.VERSION_21`)
- `buildTypes.release.minifyEnabled`: `false`

### 2.2 R8 / ProGuard Analysis & Recommendation
- **Why `minifyEnabled false` is Retained for Launch v1.0:**
  - SriLekh is a hybrid Capacitor application. The accounting algorithms, double-entry validation, and offline IndexedDB logic run inside the Android System WebView.
  - The native layer consists of Capacitor bridge plugins (`@capacitor/core`, `@capacitor/preferences`, `@capacitor/app`, `@capacitor/haptics`, `@capacitor/splash-screen`).
  - Enabling R8 minification on Capacitor without extensive physical device regression testing frequently strips Java reflection hooks and Cordova bridge methods, resulting in silent native crashes at runtime.
  - The compiled release AAB bundle size is ~4.8 MB, well below Google Play's 150 MB ceiling.
  - **Verdict:** Retaining `minifyEnabled false` for v1.0 is the proven, safe engineering decision.

---

## 3. Owner Keystore Generation & Automated Signing Workflow (OA-03)

To enable automated release signing without exposing credentials, the owner must complete this one-time setup:

### Step 1: Generate Upload Keystore
On a secure development machine with Java/Keytool installed:
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

### Step 2: Base64-Encode the Keystore File
```bash
# Windows PowerShell:
[Convert]::ToBase64String([IO.File]::ReadAllBytes("srilekh-release-key.jks")) | Out-File -Encoding ASCII srilekh_keystore_base64.txt

# macOS / Linux:
base64 -w 0 srilekh-release-key.jks > srilekh_keystore_base64.txt
```

### Step 3: Enter Secrets Directly into GitHub (Never in Chat)
In `https://github.com/prakhar2207/Vouch/settings/secrets/actions`, add:
1. `ANDROID_KEYSTORE_BASE64` = (content of `srilekh_keystore_base64.txt`)
2. `ANDROID_KEYSTORE_PASSWORD` = (your chosen keystore password)
3. `ANDROID_KEY_ALIAS` = `srilekh-key-alias`
4. `ANDROID_KEY_PASSWORD` = (your chosen key password)

Once added, GitHub Actions workflow `.github/workflows/mobile-release.yml` automatically produces a signed, Google Play-ready `.aab`.

---

## 4. The 14-Point Physical Android Device QA Matrix (OA-04)

Testing must be executed on real hardware using the `app-debug.apk` artifact from GitHub Actions or Google Play Internal Testing:

| ID | Test Scenario | Steps to Execute | Expected Passing Result | Hardware Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-01** | Cold Launch & Splash | Install APK/AAB; open app from home screen. | Splash displays cleanly; redirects to `/login` in < 2.5s. | Pending Owner Hardware |
| **TC-02** | Merchant Login & Session | Authenticate with demo account (`Apex Belting Store`). | Dashboard opens; token persisted in native preferences. | Pending Owner Hardware |
| **TC-03** | Force Close & Warm Restart | Swipe app away in Recents; re-open. | Session restored; user remains on Dashboard without re-login. | Pending Owner Hardware |
| **TC-04** | Airplane Mode Transition | Enable Airplane Mode; go to `/vouchers/sales`. | "Offline Mode" badge shows; local cached catalog loads. | Pending Owner Hardware |
| **TC-05** | Offline Voucher Creation | Create Sales Invoice while in Airplane Mode; Save. | Queued in local encrypted outbox; returns local ID. | Pending Owner Hardware |
| **TC-06** | Automatic Sync on Reconnect | Disable Airplane Mode (reconnect Wi-Fi/4G). | Background sync uploads voucher within 10s; status -> `SYNCED`. | Pending Owner Hardware |
| **TC-07** | Double-Entry Integrity | Open Reports -> Trial Balance. | Total Debits == Total Credits; variance ₹0.00. | Pending Owner Hardware |
| **TC-08** | Camera Barcode / QR Scan | Tap "Scan Item Barcode" on invoice screen. | Camera permission requested; viewfinder decodes code. | Pending Owner Hardware |
| **TC-09** | OS Memory Pressure | Open 3 heavy apps (Camera, Maps, YouTube), return. | App resumes state cleanly without losing draft inputs. | Pending Owner Hardware |
| **TC-10** | Multi-Device Logout | Log out on desktop web browser. | Mobile app detects revoked token on next request; routes to `/login`. | Pending Owner Hardware |
| **TC-11** | Account Deletion Flow | Navigate to Settings -> Delete Account. | Displays 8-year statutory accounting retention warning; confirms. | Pending Owner Hardware |
| **TC-12** | Edge-to-Edge & Cutouts | View on device with camera notch / hole-punch. | Content respects WindowInsets; no button clipping. | Pending Owner Hardware |
| **TC-13** | Screen Orientation | Rotate phone between Portrait and Landscape. | Tables scroll horizontally; layout adapts smoothly. | Pending Owner Hardware |
| **TC-14** | Hardware Back Navigation | Press Android hardware/gesture Back button. | Steps back one view; prompts exit on home screen. | Pending Owner Hardware |

---

## 5. Native Token Storage Security Assessment (OA-11)

- **Audited Files:** [`frontend/src/utils/auth.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/auth.ts#L101-L147), [`frontend/android/app/src/main/AndroidManifest.xml`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/android/app/src/main/AndroidManifest.xml#L4-L7).
- **Protections in Place:**
  - Android UID isolation: `SharedPreferences` isolated per-app.
  - `android:allowBackup="false"`: Blocks extraction via ADB backup or Google Drive auto-backup.
  - `android:usesCleartextTraffic="false"`: Blocks unencrypted HTTP traffic.
  - Accounting payloads in IndexedDB are encrypted with non-extractable WebCrypto `AES-GCM-256`.
- **Privacy Policy Transparency:** Explicitly disclosed in [`frontend/src/app/privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx#L271-L283).
- **Residual Risk & v1.1 Blueprint:** Migrating to Android hardware Keystore (`androidx.security.crypto.EncryptedSharedPreferences`) without physical devices to test biometric/PIN edge cases risks permanent app lockout. Preserving the disclosed, stable `@capacitor/preferences` for v1.0 is the responsible engineering path.
