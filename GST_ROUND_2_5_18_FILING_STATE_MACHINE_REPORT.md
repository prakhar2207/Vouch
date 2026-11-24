# SRI LEKH GST — ROUND 2.5.18
## GSTR-1 Statutory State Machine & Reconciliation Report

**Repository:** `https://github.com/prakhar2207/Vouch`  
**Production Application:** `https://srilekh.com`  
**Baseline Commit:** `7856cca6e510b5a435a93c83a2eaf285dedbd8b5`  
**Target Branch:** `main`  
**Auditor Roles:** Principal Software Architect, Indian GST Compliance Specialist, Financial Systems Auditor  
**Date:** 2026-11-23  

---

### 1. Executive Summary

Under Indian GST statutory law and the Central Goods and Services Tax Rules, 2017, a tax return cannot be considered statutorily filed without an authentic Application Reference Number (ARN) issued by the GST Common Portal (GSTN).

An earlier code inspection identified an statutory defect: in `get_portal_status()`, receiving `status="PROCESSED"` or `status_cd="1"` from the API gateway transitioned the local filing status to `FILED` even when `arn` was empty or missing!

In Round 2.5.18:
1. **Statutory Invariant:** A filing can **NEVER** be marked `FILED` without a valid, authentic government ARN.
2. **Intermediate Acknowledged State (`SUBMITTED`):** When the provider returns `PROCESSED` or `COMPLETED` but no ARN, the status remains `SUBMITTED`, reflecting that processing is acknowledged by the gateway and waiting for ARN generation.
3. **Immutability of Confirmed Filings:** Once a filing is confirmed `FILED` with a genuine ARN, subsequent queries return immediately and can never downgrade the filing to `FAILED` or `RECONCILIATION_REQUIRED`.

---

### 2. Statutory State Machine Specification

```
                                [ DRAFT ]
                                    |
                            upload_gstr1_direct()
                                    |
                             [ SUBMITTING ]
                                    |
          +-------------------------+-------------------------+
          |                         |                         |
     Provider 200              Network Timeout /         Provider 400
     Accepted                  Gateway 502/503/504       Rejected
          |                         |                         |
          v                         v                         v
     Has authentic ARN?     [ RECONCILIATION_REQUIRED ]   [ FAILED ]
          /    \
     YES /      \ NO
        v        v
   [ FILED ]  [ SUBMITTED ]
                  |
         get_portal_status()
                  |
          +-------+-------+
          |               |
     ARN Returned   No ARN (Still Processing)
          |               |
          v               v
      [ FILED ]      [ SUBMITTED ]
```

#### Detailed State Transition Rules:
1. **`DRAFT` -> `SUBMITTING`:** Created before the network call with `arn=""` and a cryptographic provider reference.
2. **`SUBMITTING` -> `SUBMITTED`:** When provider returns HTTP 200 with `status="PROCESSED"` or reference ID, but no ARN has been generated.
3. **`SUBMITTING` -> `FILED`:** Only when provider HTTP 200 response contains an authentic government ARN.
4. **`SUBMITTING` -> `RECONCILIATION_REQUIRED`:** On network timeout (`ConnectTimeout`, `ReadTimeout`, HTTP 502, 503, 504). Preserves state for status polling.
5. **`SUBMITTING` -> `FAILED`:** On explicit GSTN rejection with validation error messages.
6. **`SUBMITTED` -> `FILED`:** Triggered via `get_portal_status()` when GSTN finishes processing and returns an official ARN.
7. **`FILED` -> IMMUTABLE:** Once `status == 'FILED'` and `arn` is populated:
   - Status checks return the confirmed ARN immediately.
   - Provider errors, gateway timeouts, or transient network failures **never** downgrade a `FILED` return.

---

### 3. Empirical Test Evidence

| Test Case | Scenario Description | Statutory Invariant Enforced | Result |
| :--- | :--- | :--- | :--- |
| `test_processed_response_without_arn_remains_submitted` | Provider returns `PROCESSED` with blank `arn` | Status remains `SUBMITTED`, `arn` is `None` | **PASS** |
| `test_genuine_arn_transitions_to_filed` | Provider returns genuine ARN `092608123456789` | Status transitions to `FILED`, ARN persisted | **PASS** |
| `test_idempotent_reconciliation` | Reconciling already `FILED` return | Immediate return; provider not called | **PASS** |
| `test_filed_status_never_downgraded_on_provider_error` | Status check fails for previously `FILED` return | Filing remains `FILED`; never downgraded | **PASS** |

---

### 4. Conclusion
The GSTR-1 filing lifecycle strictly conforms to Indian statutory accounting invariants. Pseudo-acknowledgements and unconfirmed filings are completely eliminated.
