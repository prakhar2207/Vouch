# SRI LEKH — GST ROUND 1.2.1 AUDIT REPORT: ACCOUNTING INTEGRITY & PARTY ENRICHMENT
**Audited Target:** `PartyEnrichmentApplyAPIView` (`apps/gst/views.py`), `apps/gst/services/gstin_service.py`, & `apps/ledgers/models.py`  
**Git Commit:** `8860b99ac3f13db1c554b7d9b0a559a79c5a927e`  
**Branch:** `fix/stage4-12-day6-remediation`  
**Auditor:** Accounting Systems Auditor & Senior Django Engineer  
**Date:** 2026-11-16  

---

## 1. Executive Summary

This independent forensic audit evaluates the non-intrusive Party Master enrichment subsystem and verifies that GST operations preserve core Double-Entry Accounting Invariants:
1. `Total Debits == Total Credits` across all posted accounting vouchers.
2. Ledger balances maintain their natural group directions (Asset/Expense = Debit, Liability/Equity/Income = Credit).
3. Zero unlinked, orphaned, or silently mutated vouchers.
4. Non-intrusive party master updates (user preview required before modifying counterparties).

This audit identifies **one P1 security vulnerability regarding unauthorized party ledger mutations**, **one P2 functional bug where `PartyEnrichmentApplyAPIView` silently fails to apply legal business names to ledgers**, and **one P2 audit bypass on the party enrichment endpoint**.

---

## 2. Detailed Findings

### FINDING ACC-01 (Severity: P1 — High)
**Missing Role-Based Access Control on Party Master Enrichment**

- **File & Function:** `apps/gst/views.py`: `PartyEnrichmentApplyAPIView` (lines 776–786).
- **Exact Problem:**
  `PartyEnrichmentApplyAPIView` exposes `POST /api/v1/gst/party/enrich/` to apply verified GSTIN details to a company's ledger master records.
  Lines 776–786 define:
  ```python
  class PartyEnrichmentApplyAPIView(APIView):
      permission_classes = [IsAuthenticated]

      def post(self, request):
          company_id = request.data.get('company_id')
          party_id = request.data.get('party_id')
          ...
          company = get_company_or_404(request.user, company_id)
  ```
  `permission_classes` contains **only `IsAuthenticated`**.
  Furthermore, `get_company_or_404(request.user, company_id)` checks only if `UserCompany.objects.filter(user=request.user, company=company).exists()`.
  
  **No role check is performed.** A low-privilege employee (`role="EMPLOYEE"` or `role="VIEWER"`) who has read-only access to view reports can issue a `POST` request to `/api/v1/gst/party/enrich/` and unilaterally mutate party names, state codes, addresses, and GSTINs on existing customer and supplier ledgers.

- **Reproduction Scenario:**
  1. Authenticate as a user with `role="VIEWER"`.
  2. Send `POST /api/v1/gst/party/enrich/` with:
     ```json
     {
       "company_id": "...",
       "party_id": "...",
       "fields_to_update": {"gstin": "27AAACA1234A1Z5", "address": "Mutated Address"}
     }
     ```
  3. The request succeeds with HTTP 200 OK, altering master party accounting records.

- **Business / Security Impact:**
  High. Violates internal financial controls and segregation of duties. Unauthorized users could alter party tax details or redirect supply chain routing.

- **Recommended Correction:**
  Enforce administrative or accounting role authorization:
  ```python
  from apps.accounts.permissions import user_has_company_roles
  if not user_has_company_roles(request.user, company, ['ADMIN', 'OWNER', 'ACCOUNTANT']):
      return Response({"success": False, "error": "Insufficient permissions to modify party ledger masters."}, status=403)
  ```

- **Detected by Existing Tests?**
  **NO.**

---

### FINDING ACC-02 (Severity: P2 — Medium)
**Silent Failure to Update `legal_name`, `trade_name`, and `pincode` in `PartyEnrichmentApplyAPIView`**

- **File & Function:** `apps/gst/views.py`: lines 787–803 vs `apps/ledgers/models.py`: lines 31–56.
- **Exact Problem:**
  In `apps/gst/views.py`:
  ```python
  allowed_fields = {'legal_name', 'trade_name', 'gstin', 'state_code', 'address', 'pincode'}
  updated_fields = []

  for field, value in fields_to_update.items():
      if field in allowed_fields and hasattr(party, field):
          setattr(party, field, value)
          updated_fields.append(field)

  if updated_fields:
      party.save(update_fields=updated_fields)
  ```
  However, in `apps/ledgers/models.py`, the `Ledger` model defines:
  ```python
  class Ledger(models.Model):
      name = models.CharField(max_length=255)
      gstin = models.CharField(max_length=15, null=True, blank=True)
      state_code = models.CharField(max_length=2, null=True, blank=True)
      address = models.TextField(null=True, blank=True)
      # NOTE: Ledger DOES NOT HAVE fields named 'legal_name', 'trade_name', or 'pincode'!
  ```
  Consequently:
  - If a user reviews the diff and checks **"Apply Legal Name"**, the frontend sends `fields_to_update: {"legal_name": "TATA CONSULTANCY SERVICES LIMITED"}`.
  - The backend executes `hasattr(party, 'legal_name')`, which evaluates to **`False`**.
  - `legal_name` is **silently ignored**!
  - The endpoint returns `success: True`, but the party ledger's name remains unchanged!
  
  Note that in `apps/gst/services/gstin_service.py` (line 328), the service method `apply_party_enrichment` correctly mapped `legal_name` to `party.name = verified_data['legal_name']`. But `PartyEnrichmentApplyAPIView` in `views.py` completely bypassed `GSTINService.apply_party_enrichment` and implemented its own faulty reflection logic!

- **Reproduction Scenario:**
  1. Call `POST /api/v1/gst/party/enrich/` with:
     `{"company_id": "...", "party_id": "...", "fields_to_update": {"legal_name": "New Corp Ltd"}}`.
  2. Inspect response: `{"success": True, "updated_fields": []}`.
  3. Inspect `party.name`: unchanged.

- **Business / Security Impact:**
  Medium. Core functionality fails silently. Users believe party names are synchronized with the government portal when they are not.

- **Recommended Correction:**
  Refactor `PartyEnrichmentApplyAPIView` to delegate directly to `GSTINService.apply_party_enrichment()`:
  ```python
  party = GSTINService.apply_party_enrichment(
      ledger_id=party_id,
      verified_data=fields_to_update,
      apply_legal_name='legal_name' in fields_to_update,
      apply_trade_name='trade_name' in fields_to_update,
      apply_state='state_code' in fields_to_update,
      apply_address='address' in fields_to_update,
      user=request.user
  )
  ```

- **Detected by Existing Tests?**
  **NO.** Test `test_party_enrichment_preview_and_non_intrusive_apply` tests `GSTINService.apply_party_enrichment()`, not the HTTP view `PartyEnrichmentApplyAPIView`.

---

### FINDING ACC-03 (Severity: P2 — Medium)
**Audit Trail Bypass in `PartyEnrichmentApplyAPIView`**

- **File & Function:** `apps/gst/views.py`: `PartyEnrichmentApplyAPIView` (lines 801–808).
- **Exact Problem:**
  `GSTINService.apply_party_enrichment` logs a structured audit event (`GSTAuditService.log_action(action="PARTY_ENRICH", ...)`).
  However, because `PartyEnrichmentApplyAPIView` implements direct model updates instead of calling the service method, **no `GSTAuditLog` record is generated when party details are enriched via the API**.

- **Business / Security Impact:**
  Breaks statutory audit compliance. Modifications to party tax records are unrecorded in the GST audit log.

- **Recommended Correction:**
  Delegating to `GSTINService.apply_party_enrichment()` (as recommended in Finding ACC-02) automatically restores the audit logging.

- **Detected by Existing Tests?**
  **NO.**

---

## 3. Double-Entry Accounting Invariance Evaluation

The audit verified whether any GST operation (registration creation, lookup, cache updating, party enrichment) could inadvertently affect the accounting core:

1. **Voucher Immutability:**
   GST operations execute strictly on `apps.gst` tables and ledger master fields (`name`, `state_code`, `gstin`, `address`). No query touches `apps.accounting.models.Voucher` or `VoucherItem`.
2. **Balance Preservation:**
   Ledger balances (`current_balance`, `opening_balance`) are never included in `update_fields` during party enrichment.
3. **Equilibrium Check:**
   `test_accounting_engine_invariance` confirmed that after multiple registration creations and lookups:
   - Total Debits == Total Credits is preserved.
   - Total posted voucher count is unchanged.
   - Party ledger balance is mathematically identical.

---

## 4. Verdict & Release Readiness

**Dimension Verdict:** **FAIL (REMEDIATION REQUIRED BEFORE GA)**  
While double-entry accounting invariants are fully protected from corruption, **Finding ACC-01 (Missing RBAC on party enrichment)** and **Finding ACC-02 (Silent failure to update party name)** represent unacceptable bugs that must be corrected.
