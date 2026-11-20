# SRI LEKH — GST ROUND 1.2.1 AUDIT REPORT: FRONTEND UX & PORTAL DISTINCTION
**Audited Target:** `frontend/src/components/settings/GSTRegistrationsView.tsx` & `frontend/src/lib/api/gst.ts`  
**Git Commit:** `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`  
**Branch:** `fix/stage4-12-day6-remediation`  
**Auditor:** Principal Frontend Engineer & UX/Accessibility Auditor  
**Date:** 2026-11-16  

---

## 1. Executive Summary

This independent forensic audit evaluates the Next.js / TypeScript frontend implementation for SriLekh's GST Multi-Registration and verification workflow (`frontend/src/components/settings/GSTRegistrationsView.tsx`).

The interface provides:
1. Multi-GSTIN dashboard displaying all configured registrations, their primary state, and verification status.
2. In-modal pre-save verification preview against Sandbox by Quicko.
3. Registration lifecycle management (edit, activate, deactivate, on-demand re-verification).
4. Auto-population of legal name, trade name, address, and state from GSTIN digits.

This audit identifies **one P2 flaw where the UI misrepresents unconfigured/cached results as "Portal Verified"**, **one P2 flaw allowing silent unverified saves**, and **two P3 UX/responsive layout defects**.

---

## 2. Detailed Findings

### FINDING FE-01 (Severity: P2 — Medium)
**False "Portal Verified" Distinction on Cache or Unconfigured Gateway Fallback**

- **File & Function:** `frontend/src/components/settings/GSTRegistrationsView.tsx`: lines 408–421.
- **Exact Problem:**
  In `handleVerifyInModal()`:
  ```typescript
  const res = await gstApi.verifyRegistrationPreview(companyId, clean);
  if (res.success) {
      setVerifiedDetails(res);
      ...
  }
  ```
  And in the JSX rendering:
  ```tsx
  {verifiedDetails && (
      <div className="p-3.5 rounded-xl bg-emerald-500/5 border border-emerald-500/20 space-y-1.5">
          <div className="flex items-center justify-between text-[11px]">
              <span className="font-bold text-emerald-500 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Portal Verified
              </span>
              <span className="font-bold uppercase text-foreground">{verifiedDetails.status || 'Active'}</span>
          </div>
          ...
      </div>
  )}
  ```
  However, in the backend (`apps/gst/services/gstin_service.py`), when the Sandbox Gateway is not configured with live credentials, or when an error occurs, the API can return:
  ```json
  {
      "success": true,
      "source": "cache_unconfigured_gateway",
      "is_cached": true
  }
  ```
  Because `res.success` is `true`, the frontend unconditionally displays a prominent green badge declaring **"Portal Verified"**!
  
  The user is given the false impression that a live query was executed against the Indian Government GST Portal via Quicko Sandbox, when in reality no live network verification took place.

- **Reproduction Scenario:**
  1. Set up an environment without `GST_SANDBOX_API_KEY`.
  2. Populate `GSTTaxpayerCache` with a mock entry.
  3. In the UI, click "Add GST Registration" and click "Verify".
  4. The card turns bright green with "Portal Verified", despite the gateway being completely unconfigured.

- **Business / Security Impact:**
  Medium. Misleads business owners and auditors into believing records were verified in real-time with the sovereign portal.

- **Recommended Correction:**
  Inspect `res.source` and render distinct badges:
  ```tsx
  {verifiedDetails.source === 'provider_live' ? (
      <span className="text-emerald-500"><CheckCircle2 className="..." /> Portal Verified (Live)</span>
  ) : verifiedDetails.is_cached ? (
      <span className="text-blue-500"><Info className="..." /> Verified via Local Cache ({new Date(verifiedDetails.updated_at).toLocaleDateString()})</span>
  ) : (
      <span className="text-amber-500"><AlertTriangle className="..." /> Format Validated (Gateway Offline)</span>
  )}
  ```

- **Detected by Existing Tests?**
  **NO.**

---

### FINDING FE-02 (Severity: P2 — Medium)
**Silent Save of Unverified GSTIN Without Confirmation**

- **File & Function:** `frontend/src/components/settings/GSTRegistrationsView.tsx`: lines 149–160.
- **Exact Problem:**
  When creating a registration:
  ```typescript
  await gstApi.createRegistration(companyId, {
      gstin: clean,
      ...
      auto_verify: false // Already verified via preview
  });
  ```
  The code assumes the user clicked the "Verify" button prior to clicking "Confirm & Save Registration".
  However, the "Confirm & Save Registration" button is enabled as long as `inputGstin.length === 15`. If the user types a 15-character GSTIN and immediately clicks "Confirm & Save Registration" without clicking "Verify":
  1. The registration is saved with `auto_verify: false`.
  2. It is saved with `verification_status: 'NOT_VERIFIED'`.
  3. The modal closes without informing the user that the registration was never verified against the portal.

- **Recommended Correction:**
  If `!verifiedDetails`, either require verification before enabling the submit button, or display a clear confirmation dialog: *"This GSTIN has not been verified against the GST portal. Save as Unverified?"*

- **Detected by Existing Tests?**
  **NO.**

---

### FINDING FE-03 (Severity: P3 — Low)
**Missing Deactivation Confirmation Modal**

- **File & Function:** `frontend/src/components/settings/GSTRegistrationsView.tsx`: `handleToggleActive` (lines 188–201).
- **Exact Problem:**
  Clicking the power toggle button immediately fires `deactivateRegistration()` or `reactivateRegistration()`. There is no confirmation prompt. If an operator accidentally clicks the power icon on their primary GSTIN, the registration is instantly marked `INACTIVE`, which could block active e-invoicing pipelines.

- **Recommended Correction:**
  Add a confirmation modal (`window.confirm` or custom dialog) before sending the deactivation request.

- **Detected by Existing Tests?**
  **NO.**

---

### FINDING FE-04 (Severity: P3 — Low)
**Modal Viewport Overflow on Small Screens (Mobile Viewports)**

- **File & Function:** `frontend/src/components/settings/GSTRegistrationsView.tsx`: line 348.
- **Exact Problem:**
  The modal container is declared as:
  ```tsx
  <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-2xl relative space-y-4">
  ```
  On mobile devices (e.g. iPhone SE, screen height < 700px), when the verified card, legal name, trade name, state, pincode, address textarea, and primary toggle are all expanded, the modal content extends beyond the screen boundary and the submit buttons become inaccessible.

- **Recommended Correction:**
  Add scroll constraints to the modal container:
  ```tsx
  <div className="bg-card border border-border rounded-2xl max-w-lg w-full p-6 shadow-2xl relative space-y-4 max-h-[90vh] overflow-y-auto">
  ```

---

## 3. UI/UX Verification Summary

| UX Dimension | Implementation | Assessment |
|---|---|---|
| **Loading Indicators** | Spinners on `loading`, `verifying`, `verifyingId`, and `saving`. | **EXCELLENT.** User always receives visual feedback during async operations. |
| **Error Feedback** | `useToast()` error notifications for network failures, 400 Bad Requests, and validation errors. | **EXCELLENT.** |
| **Status Badges** | Distinct color palettes for `ACTIVE` (emerald), `INACTIVE` (gray), `CANCELLED` (red), `SUSPENDED` (amber). | **EXCELLENT.** High visual clarity. |
| **Primary Indication** | `★ PRIMARY` badge on primary registration. | **EXCELLENT.** |
| **Portal Distinction** | Unconditional "Portal Verified" badge regardless of source. | **DEFECTIVE (Finding FE-01).** |

---

## 4. Verdict & Release Readiness

**Dimension Verdict:** **CONDITIONAL PASS**  
The user interface is modern, reactive, and provides clear visual states. Resolving the portal distinction ambiguity (Finding FE-01) and adding a confirmation dialog for unverified saves (Finding FE-02) will ensure compliance-grade usability.
