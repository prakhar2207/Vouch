# SRI LEKH — STAGE 1.2.6 PHYSICAL ANDROID DEVICE QA MATRIX & EXECUTION RUNBOOK

**Assessment Date:** 2026-11-12  
**Target Package:** `com.srilekh.app`  
**Execution Environment:** Workstation host has no physical handsets, emulators, or `adb` (`shutil.which('adb') == False`)  
**Certification Verdict:** **BLOCKED PENDING HARDWARE TESTING (OA-04)**  

---

## 1. Executive Summary

While cloud CI verifies compilation of the Android APK and AAB bundles, Google Play Store compliance, stability, and MSME accounting reliability require manual and automated verification on actual physical Android devices.

Mobile devices introduce real-world conditions that cannot be simulated on cloud runners:
- Dynamic WebView engine variations across Android versions (Chromium 80 through Chromium 130+).
- System-level memory pressure and low-memory killer (LMK) eviction.
- Hardware-accelerated WebCrypto (`AES-GCM-256`) performance on entry-level ARM chipsets.
- Cellular-to-offline transitions (creating invoices in physical dead zones and reconnecting).
- Camera hardware initialization for barcode and QR code invoice scanning.

This report establishes the complete 14-point physical device verification matrix, device testing cohorts, and step-by-step owner execution instructions.

---

## 2. Target Device Verification Cohort

Testing must be executed across at least two real physical devices spanning entry-level and modern Android versions:

| Tier | Target Specs | Example Devices | Android Version | Primary Verification Focus |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1 (Legacy / Entry MSME)** | 2 GB – 3 GB RAM, MediaTek Helio / Unisoc, 720p Display | Redmi 9A, Realme C11, Galaxy A03 | Android 9.0 – 11.0 (WebView < 95) | Memory pressure, indexedDB storage limits, offline voucher creation speed |
| **Tier 2 (Mainstream MSME)** | 4 GB – 8 GB RAM, Snapdragon 600/700 series, 1080p | Redmi Note 11/12, Galaxy M33, Vivo T1 | Android 12.0 – 13.0 | Typical merchant usage, multi-tab resume, camera barcode scanning |
| **Tier 3 (Modern / Flagship)** | 8 GB+ RAM, High Refresh Rate, Edge-to-Edge Display | Pixel 7/8, Galaxy S23/S24, OnePlus 11 | Android 14.0 – 15.0 | Edge-to-edge UI rendering, gesture navigation, strict Android 14/15 background limits |
| **Tier 4 (Tablet Companion)** | 10" Screen, Landscape Orientation | Lenovo Tab M10, Galaxy Tab A8 | Android 11.0 – 13.0 | Responsive tablet dashboard, split-view ledger statements |

---

## 3. The 14-Point Physical QA Test Matrix

Each test case must be executed on a physical device using either the Debug APK or the Google Play Internal Testing Track build.

| ID | Test Scenario | Execution Steps | Expected Passing Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-01** | **Clean Installation & Cold Launch** | Download and install APK/AAB; open app from launcher. | App splash screen displays smoothly; redirects to `/login` within `< 2.5` seconds. No crash or white screen. | Pending Owner Execution |
| **TC-02** | **Merchant Login & Biometric/Token Persistence** | Authenticate using sandbox credentials (`Apex Belting Store`). | Dashboard loads immediately; token securely saved in native preferences; no JavaScript console errors. | Pending Owner Execution |
| **TC-03** | **App Kill & Warm Restart** | Force close app from Android Recents; reopen app. | Session is automatically restored; user remains logged into dashboard without re-entering credentials. | Pending Owner Execution |
| **TC-04** | **Offline Mode Transition (Dead Zone Simulation)** | Place device in **Airplane Mode**; navigate to `/vouchers/sales`. | UI shows "Offline Mode" indicator; product catalog and party list load instantly from local encrypted IndexedDB. | Pending Owner Execution |
| **TC-05** | **Offline Invoice Creation** | Create a Sales Invoice (1 customer, 2 items, GST 18%) while in Airplane Mode; click Save. | Voucher saves to local outbox; returns local transaction ID; debit/credit equilibrium maintained in local ledger. | Pending Owner Execution |
| **TC-06** | **Automatic Cloud Sync on Reconnect** | Disable Airplane Mode (re-enable Wi-Fi / 4G). | Within 10 seconds, background sync activates; voucher uploads to backend; local outbox status updates to `SYNCED`. | Pending Owner Execution |
| **TC-07** | **Double-Entry Balance Verification** | Navigate to Reports -> Trial Balance after reconnect. | Total Debits == Total Credits; difference is `0.00 INR`; invoice matches backend database records. | Pending Owner Execution |
| **TC-08** | **Camera Barcode / QR Scanning** | Open invoice item scanner; grant camera runtime permission. | Camera view opens smoothly; correctly decodes QR/barcode; populates SKU/item name in invoice row. | Pending Owner Execution |
| **TC-09** | **Backgrounding & OS Memory Pressure** | Open SriLekh, open 3 heavy apps (Camera, YouTube, Maps), return to SriLekh. | App state resumes cleanly; does not reload from scratch or lose unsaved draft invoice inputs. | Pending Owner Execution |
| **TC-10** | **Multi-Tab / Multi-Device Logout** | Log in on mobile; log in on desktop browser; click Logout on desktop. | Mobile app detects invalid refresh token on next API request, clears secure storage, and returns to `/login`. | Pending Owner Execution |
| **TC-11** | **In-App Account Deletion Flow** | Navigate to Settings -> Privacy -> Delete Account (or visit `/delete-account`). | Warning dialog displays statutory 8-year accounting retention notice; deletion request processes per policy. | Pending Owner Execution |
| **TC-12** | **Edge-to-Edge & Display Cutouts** | Verify layout on device with camera notch / hole punch / curved edges. | Content respects Android WindowInsets; status bar and navigation bar do not overlap buttons or navigation links. | Pending Owner Execution |
| **TC-13** | **Orientation Changes (Portrait / Landscape)** | Rotate device while viewing Balance Sheet and Invoice table. | Layout adapts smoothly; table scrolls horizontally without layout clipping or text truncation. | Pending Owner Execution |
| **TC-14** | **Native Back Button & Navigation** | Press Android hardware/gesture Back button across all nested menus. | Navigates back one step in view history; pressing Back on home dashboard prompts to minimize or exit cleanly. | Pending Owner Execution |

---

## 4. Step-by-Step Owner Execution Instructions

### Option 1: Direct USB Installation (Debug APK)
1. Download `android-debug-apk` artifact from the latest GitHub Actions CI run.
2. Enable **Developer Options** and **USB Debugging** on your Android handset.
3. Connect handset to your computer and install:
   ```bash
   adb install -r app-debug.apk
   ```
4. Execute the 14 test cases in Section 3.

### Option 2: Google Play Internal Testing Track (Recommended)
1. Upload the signed `app-release.aab` to Google Play Console -> **Internal Testing**.
2. Add tester email addresses (e.g., your own Gmail account).
3. Open the Play Store opt-in link on your physical phone and install directly from the Play Store.
4. Execute the 14 test cases in Section 3.

---

## 5. Evidence Recording Template for Closure

To certify closure of **OA-04**, the owner must record test execution results:

```markdown
### Physical Device QA Execution Log
- **Tester Name:** [Owner / QA Engineer]
- **Date:** [YYYY-MM-DD]
- **Device Model:** [e.g., Samsung Galaxy M33 / Xiaomi Redmi Note 12]
- **Android OS Version:** [e.g., Android 13 (API 33)]
- **WebView Version:** [e.g., Chrome 124.0.6367.82]
- **Build Tested:** [Debug APK / Play Internal Track AAB]
- **TC-01 through TC-14 Result:** ALL PASS (14/14)
- **Defects Identified:** [None / Detail any layout or sync bugs]
```
