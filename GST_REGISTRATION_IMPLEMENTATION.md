# SriLekh — Multi-GSTIN Registration Management Implementation

## 1. Overview & Architecture

Indian MSMEs, manufacturers, distributors, and logistics firms frequently operate across state borders under the same PAN. Under Indian GST law, a taxpayer must register a distinct 15-character Goods and Services Tax Identification Number (GSTIN) in every state or Union Territory where they maintain a place of business.

Round 1 establishes **Multi-GSTIN Registration Management** in SriLekh with strict multi-tenant isolation, state-code consistency, and dynamic verification tracking.

---

## 2. Data Model (`GSTRegistration`)

The `GSTRegistration` model (`apps/gst/models.py`) encapsulates all state registrations belonging to an entity:

```python
class GSTRegistration(BaseModel):
    VERIFICATION_STATUS_CHOICES = [
        ('NOT_VERIFIED', 'Not Verified'),
        ('PENDING', 'Pending Verification'),
        ('VERIFIED', 'Verified Active'),
        ('INVALID', 'Invalid Format / Checksum'),
        ('INACTIVE', 'Cancelled / Suspended'),
        ('FAILED', 'Verification Failed'),
        ('PROVIDER_UNAVAILABLE', 'Provider Unavailable'),
        ('EXPIRED', 'Verification Expired (>90 Days)'),
    ]

    company = models.ForeignKey(
        'company.Company',
        on_delete=models.CASCADE,
        related_name='gst_registrations'
    )
    gstin = models.CharField(max_length=15, db_index=True)
    state_code = models.CharField(max_length=2)
    state_name = models.CharField(max_length=100)
    trade_name = models.CharField(max_length=200, blank=True)
    legal_name = models.CharField(max_length=200, blank=True)
    registered_address = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    composition_scheme = models.BooleanField(default=False)
    registration_date = models.DateField(null=True, blank=True)
    
    # Round 1 Dynamic Verification Lifecycle Tracking
    verification_status = models.CharField(
        max_length=25,
        choices=VERIFICATION_STATUS_CHOICES,
        default='NOT_VERIFIED',
        db_index=True,
    )
    last_verified_at = models.DateTimeField(null=True, blank=True)
    provider_reference_id = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        unique_together = ('company', 'gstin')
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['gstin', 'is_active']),
        ]
```

### Invariants Enforced
1. **Multi-Tenant Scoping**: All registrations are keyed to `company`. Cross-tenant queries are blocked at both ORM and serializer levels.
2. **PAN & State Code Consistency**: The first 2 characters must match `state_code` in `VALID_GST_STATE_CODES`. The middle 10 characters (3 to 12) must match the company's PAN.
3. **Primary Flag Exclusivity**: Only one active registration per company can have `is_primary=True`. Marking a new registration as primary automatically demotes the prior primary registration.
4. **Non-Destructive Deactivation**: Registrations cannot be hard-deleted if referenced in historical vouchers. Calling deactivation sets `is_active=False` and preserves audit history.

---

## 3. Service Layer (`GSTRegistrationService`)

The service layer is implemented in `apps/gst/services/registration_service.py` to decouple business logic from API endpoints:

- `list_registrations(company_id, active_only=True)`: Retrieves tenant-filtered registrations ordered by primary status and state.
- `get_registration(company_id, registration_id)`: Fetches a single registration with strict tenant verification.
- `verify_preview(company_id, gstin, timeout=10)`: Performs local format & checksum validation, and optionally queries the Sandbox API to return a non-committing preview diff of legal name, trade name, address, and status.
- `create_registration(company_id, data)`: Validates format, checksum, PAN match, creates the record, updates primary status atomically in a transaction, and triggers initial verification status.
- `verify_existing_registration(company_id, registration_id)`: Re-verifies an existing registration against Sandbox by Quicko, updating `verification_status` and `last_verified_at`.
- `update_registration(company_id, registration_id, data)`: Updates metadata (trade name, address, primary status) without altering the immutable statutory GSTIN.
- `deactivate_registration(company_id, registration_id)`: Sets `is_active=False`. Rejects deactivating the sole primary registration if active non-primary registrations exist.

---

## 4. API Endpoints

The endpoints are secured with `IsAuthenticated` and `HasRole(['OWNER', 'ADMIN', 'CA'])`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/gst/registrations/<company_id>/` | List all GSTIN registrations for the company |
| `POST` | `/api/v1/gst/registrations/<company_id>/` | Create a new GSTIN registration |
| `GET` | `/api/v1/gst/registrations/<company_id>/<registration_id>/` | Retrieve registration details |
| `PUT` | `/api/v1/gst/registrations/<company_id>/<registration_id>/` | Update registration metadata |
| `POST` | `/api/v1/gst/registrations/<company_id>/verify-preview/` | Verify GSTIN & preview details without creating |
| `POST` | `/api/v1/gst/registrations/<company_id>/<registration_id>/verify/` | Re-verify existing registration via Sandbox |
| `POST` | `/api/v1/gst/registrations/<company_id>/<registration_id>/deactivate/` | Deactivate registration |
| `POST` | `/api/v1/gst/registrations/<company_id>/<registration_id>/reactivate/` | Reactivate previously deactivated registration |

---

## 5. Frontend Management Interface

A dedicated Multi-GSTIN settings tab is available in `frontend/src/components/settings/GSTRegistrationsView.tsx` embedded in `/settings` under the `gst-registrations` sub-navigation:

1. **State Registration Table**: Lists state, state code, GSTIN, primary badge, status badge, and actions.
2. **Add Registration Modal**: Allows inputting GSTIN, state, trade name, and address.
3. **Verify & Auto-Fill Flow**: Clicking "Verify with GST" triggers a pre-fetch preview, allowing users to confirm the Legal and Trade names before saving.
4. **Primary Designation**: Quick toggle to switch primary GSTIN.
5. **Active Status Controls**: Safe toggle to deactivate or reactivate secondary GSTINs.
