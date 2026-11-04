# SriLekh EDI Network — Register of Remaining Operational Defects & Smallest Safe Remediations

**Audited Baseline:** `main` (`591841d`) + Post-Remediation Working Tree  
**Evaluation Date:** 2026-11-04  
**Audit Context:** Independent Post-Remediation Verification  

During the independent verification of the five remediated defects (`DEFECT-EDI-01` through `DEFECT-EDI-05`), two minor operational defects were identified. Neither defect compromises double-entry balance equilibrium or permits cryptographic forgery, but both warrant remediation prior to broad multi-server production deployment.

In strict compliance with user instructions (*"Do not change code during this verification phase. If a defect remains, document the smallest safe fix and wait for approval"*), the smallest safe fixes are documented below.

---

## DEFECT-EDI-06: Production Replay Protection Fails-Closed Only on Exact Module String

- **Severity:** P2 (High Reliability / Defense-in-Depth)
- **Module:** [`apps/protocol/qr_bootstrap.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/protocol/qr_bootstrap.py#L130-L135)
- **Component:** `QRSessionManager.initiate_session_from_scan`

### 1. Problem Description & Root Cause
In `apps/protocol/qr_bootstrap.py`, when both Redis and PostgreSQL fail during nonce consumption, the service checks whether it is running in production before falling back to local process memory:

```python
# apps/protocol/qr_bootstrap.py (line 130-132)
from django.conf import settings
if not getattr(settings, 'TESTING', False) and not getattr(settings, 'DEBUG', False) and os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings.production":
    raise SecurityViolation("Durable replay protection store is unavailable. Aborting for security.")
```

If the production container is launched with `DEBUG=False` (the universal Django indicator of production) but `DJANGO_SETTINGS_MODULE` is unset (defaulting in `wsgi.py` / `manage.py` to `config.settings`), or set to `config.settings.prod` or `config.settings.staging`, the string comparison `os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings.production"` evaluates to `False`.

In that deployment topology, if both Redis and PostgreSQL are unavailable, the system silently falls back to in-memory `self.used_nonces.add(...)`, which cannot synchronize across multi-worker Gunicorn/Uvicorn clusters.

### 2. Verified Evidence
From [`scratch/verify_qr_replay.py`](file:///C:/Users/prakh/.gemini/antigravity/brain/1ee00218-7707-4a3f-aa67-f5b0f89cd317/scratch/verify_qr_replay.py):
```
[FINDING CONFIRMED] C2 (DEBUG=False with DJANGO_SETTINGS_MODULE='config.settings'): Permitted unsafe in-memory fallback because string did not equal 'config.settings.production'.
```

### 3. Smallest Safe Fix (Pending Approval)
Replace the rigid environment variable string check with Django's standard production indicators:

```python
# Proposed Smallest Safe Fix in apps/protocol/qr_bootstrap.py
from django.conf import settings
is_production = (not getattr(settings, 'DEBUG', True)) and (not getattr(settings, 'TESTING', False))
if is_production:
    raise SecurityViolation("Durable replay protection store is unavailable. Aborting for security.")
```

---

## DEFECT-EDI-07: Pending EntityMapping Rolled Back by Atomic LedgerBridge Transaction

- **Severity:** P2 (Operational Workflow / Queue Visibility)
- **Module:** [`apps/protocol/bridge.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/protocol/bridge.py#L91), [`apps/protocol/bridge.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/protocol/bridge.py#L251-L268)
- **Component:** `LedgerBridge.execute_converged_accounting` (Tier 3 Semantic Resolution)

### 1. Problem Description & Root Cause
`LedgerBridge.execute_converged_accounting` is decorated with `@transaction.atomic` to ensure that invoice vouchers, credit notes, and ledger entries post atomically.

In Tier 3, when an ambiguous product match is detected ($0.70 \le \text{score} < 0.90$), the method records an `EntityMapping` with `approval_state=ApprovalState.PENDING.value` and immediately raises `LedgerBridgeError`:

```python
# apps/protocol/bridge.py (lines 251-268)
EntityMapping.objects.get_or_create(
    source_company_id=source_id,
    destination_company_id=dest_id,
    foreign_sku=line.sku,
    mapping_version=1,
    defaults={
        "mapping_id": f"MAP-{uuid.uuid4().hex[:12].upper()}",
        "local_sku": matched_item.get('sku', ''),
        "confidence_level": confidence.value,
        "approval_state": ApprovalState.PENDING.value,
        "conversion_multiplier": 1.0,
        "hsn_override": line.hsn_code
    }
)
raise LedgerBridgeError(
    f"Product line '{line.sku}' matched '{matched_item.get('sku')}' with ambiguous confidence "
    f"({score:.2f}). Recorded as PENDING approval; auto-provisioning is blocked."
)
```

Because `LedgerBridgeError` is raised inside the `@transaction.atomic` block, Django rolls back the entire database transaction, including the newly created `EntityMapping` record!

- **Positive Invariant:** Zero unauthorized products or vouchers are posted (the accounting integrity invariant holds).
- **Operational Defect:** The `PENDING` mapping record is not persisted in PostgreSQL. As a result, the administrator's "Pending Approvals" dashboard cannot display the pending item for human review. Subsequent sync calls repeatedly attempt Tier 3 and roll back without advancing the workflow.

### 2. Verified Evidence
From [`scratch/verify_mapping_enforcement.py`](file:///C:/Users/prakh/.gemini/antigravity/brain/1ee00218-7707-4a3f-aa67-f5b0f89cd317/scratch/verify_mapping_enforcement.py):
```
[FINDING CONFIRMED] EntityMapping creation was rolled back by @transaction.atomic when LedgerBridgeError was raised!
```

### 3. Smallest Safe Fix (Pending Approval)
Persist the pending mapping using a separate database transaction or commit it before raising the error, or catch the specific ambiguous mapping error in `SyncService` outside the rollback:

```python
# Proposed Smallest Safe Fix in apps/protocol/bridge.py
from django.db import transaction as db_transaction

# In Tier 3, persist the PENDING mapping in an autonomous or separate transaction block:
with db_transaction.atomic():
    EntityMapping.objects.get_or_create(
        source_company_id=source_id,
        destination_company_id=dest_id,
        foreign_sku=line.sku,
        mapping_version=1,
        defaults={ ... }
    )

# Then raise the blocking error so financial vouchers are rolled back
raise LedgerBridgeError(...)
```
*(Alternatively, in `apps/protocol/sync_service.py`, when `LedgerBridge.execute_converged_accounting` raises `LedgerBridgeError` containing ambiguous match details, write the pending mapping record).*

---

## 4. Summary Matrix of Remaining Defects

| Defect ID | Severity | Description | Safety Risk | Operational Risk | Recommended Fix Effort |
|---|---|---|---|---|---|
| **DEFECT-EDI-06** | P2 | QR replay fail-closed relies on exact module string | Low (Requires simultaneous Redis + DB failure) | Medium (Multi-worker cluster inconsistency if both caches fail) | 3 lines in `qr_bootstrap.py` |
| **DEFECT-EDI-07** | P2 | Ambiguous mapping pending record rolled back by atomic block | None (Vouchers/products are strictly blocked) | Medium (Admin cannot see pending queue without manual DB insert) | 4 lines in `bridge.py` |

Neither defect allows unauthorized financial commits, data corruption, or cross-tenant data leaks.
