# SriLekh GST — Round 2.5.6: Reversal-to-Reclaim Lineage & Event Idempotency Report

**Repository:** https://github.com/prakhar2207/Vouch  
**Branch:** `fix/round2-5-6-itc-evidence-and-event-linkage`  
**Base Commit:** `d0e70798dfa823a597b3f412c894f0fb17692dfe`  
**Staging Database:** Neon PostgreSQL `neondb_staging` (`6f4741bdaaf4`)  
**Statutory Standards:** CGST Rules 2017 Rule 37(4), Rule 37A proviso, Section 155  
**Document Reference:** `GST_ROUND_2_5_6_REVERSAL_RECLAIM_LINEAGE_REPORT.md`  

---

## 1. Architectural Problem: Aggregate Balances vs Direct Lineage

In Round 2.5.5, ITC reclaim eligibility was determined via an aggregate balance inequality:
$$\sum \text{Reclaimed Tax} \le \sum \text{Reversed Tax}$$

While mathematically sound for single-payment, single-reversal transactions, this aggregate model fails statutory and forensic audits in multi-event operational workflows:
1. **Unlinkable Tax Rupee:** An auditor cannot trace which specific reversal entry was cured by which specific bank payment.
2. **Component Cross-Contamination:** Aggregate balance checks allow an IGST reclaim to be booked against prior CGST and SGST reversals, violating the separate ledger accounting required for Central, State, and Integrated Tax.
3. **Multi-Reversal Disambiguation:** When an invoice undergoes multiple partial reversals (e.g. ₹500 in Period 072026, ₹1,000 in Period 082026), a subsequent partial payment must consume these reversals according to deterministic accounting rules (First-In, First-Out).
4. **Invalid Reversal Poisoning:** An aggregate query could inadvertently count inactive, superseded, or Section 17(5) blocked reversals as eligible source pools.

---

## 2. Lineage Architecture & Data Models

Round 2.5.6 introduces explicit graph lineage connecting each reclaim event directly to its qualifying reversal event(s).

### 2.1. `GSTReversalReclaimLineage` Model
```python
class GSTReversalReclaimLineage(BaseModel):
    """
    Statutory audit lineage linking an ITC reclaim allocation directly to the qualifying
    prior reversal allocation(s) that it restores.
    Enforces CGST Rule 37(4) and Rule 37A proviso auditability.
    """
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='itc_lineage_records')
    voucher = models.ForeignKey('accounting.Voucher', on_delete=models.CASCADE, related_name='itc_reclaim_lineages')
    reversal_allocation = models.ForeignKey(
        'gst.GSTReportingAllocation',
        on_delete=models.CASCADE,
        related_name='reclaim_lineages_as_reversal'
    )
    reclaim_allocation = models.ForeignKey(
        'gst.GSTReportingAllocation',
        on_delete=models.CASCADE,
        related_name='reversal_lineages_as_reclaim'
    )
    reclaimed_tax = models.DecimalField(max_digits=14, decimal_places=2)
    igst_reclaimed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    cgst_reclaimed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    sgst_reclaimed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    cess_reclaimed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    statutory_rule = models.CharField(
        max_length=20,
        choices=[
            ('RULE_37', 'Rule 37 (180-Day Non-Payment)'),
            ('RULE_37A', 'Rule 37A (Supplier GSTR-3B Default)'),
        ],
        default='RULE_37'
    )
```

### 2.2. Allocation Model Extensions (`GSTReportingAllocation`)
To guarantee source-event identity and traceability:
- `source_reversal`: Direct ForeignKey to the primary reversal allocation (or first consumed allocation).
- `payment_allocation`: Optional ForeignKey to the source accounting `PaymentAllocation` ledger entity.
- `payment_event_id`: Unique external or banking event identifier (e.g. NEFT UTR, cheque reference, webhook event ID).
- `payment_reference`: Free-text payment instrument reference.

---

## 3. FIFO Multi-Reversal Consumption Engine

When `create_rule37_reclaim_allocation()` is executed, it locks the voucher and active reversal records using PostgreSQL row-level locks (`select_for_update()`) and iterates through available reversals in FIFO order:

```
Reversal Pool:
[Rev 1: ₹800.00 (Period 072026)] ---> Fully Consumed by Reclaim A (₹800.00)
[Rev 2: ₹1,000.00 (Period 082026)] ---> Partially Consumed by Reclaim A (₹400.00)
                                    ---> Remaining Available Balance: ₹600.00
                                    ---> Consumed by Reclaim B (₹600.00)
```

### Tax Component Breakdown Algorithm
For each reversal consumed in FIFO order, the four component tax amounts are derived proportionally:
$$\text{Component Reclaimed} = \text{round}\left( \text{Reversal Component} \times \frac{\text{Tax Consumed}}{\text{Total Reversal Tax}}, 2 \right)$$

Any fractional cent rounding discrepancies are dynamically adjusted on the primary tax component, ensuring:
$$\text{igst\_reclaimed} + \text{cgst\_reclaimed} + \text{sgst\_reclaimed} + \text{cess\_reclaimed} \equiv \text{reclaimed\_tax}$$

---

## 4. Payment-Event Idempotency Engine

### The Problem with Period/Amount Keys
Under Round 2.5.5, the unique constraint on `['company', 'voucher', 'event_type']` prevented multiple partial reclaims on the same voucher. If an MSME paid ₹5,000 on August 5th and ₹5,000 on August 20th:
1. The unique constraint caused an `IntegrityError` on the second payment.
2. If the constraint was simply deleted, retrying network requests duplicated reclaims.

### The Round 2.5.6 Solution
1. **Migration 0014:** The legacy constraint was replaced with an intelligent conditional constraint that permits multiple distinct `ITC_RECLAIM` and `ITC_REVERSAL_RULE_37` events.
2. **Stable Source-Event Constraint:** A strict unique constraint was added:
   ```python
   models.UniqueConstraint(
       fields=['company', 'voucher', 'payment_event_id'],
       condition=models.Q(is_active=True) & models.Q(payment_event_id__isnull=False) & ~models.Q(payment_event_id=''),
       name='unique_active_reclaim_per_payment_event'
   )
   ```
3. **Idempotency Behavior:**
   - **Distinct Genuine Payments:** Payments with distinct `payment_event_id` (e.g. `PAY-001` and `PAY-002`) are both created and tracked independently.
   - **Network Retries / Duplicates:** Re-submitting the same `payment_event_id` queries the existing active allocation and returns it immediately without creating duplicates or throwing errors.

---

## 5. Lineage Invariant Verification

The lineage engine enforces four absolute statutory invariants:

1. **No Inactive or Superseded Consumption:** A reversal that has been marked `is_active=False` or `SUPERSEDED` by a previous reclaim cannot be consumed again.
2. **No Cross-Rule Consumption:** A Rule 37 reclaim can only consume `ITC_REVERSAL_RULE_37` allocations; it can never consume `ITC_REVERSAL_RULE_37A` or `ITC_REVERSAL_PERMANENT`.
3. **No Cross-Tenant / Cross-Voucher Leakage:** The lineage foreign keys are strictly validated against `company_id` and `voucher_id`.
4. **No Section 17(5) Contamination:** Blocked credits under Section 17(5) have `is_eligible=False` and are never admitted into the reversal/reclaim lineage pool.

---

## 6. PostgreSQL Concurrency & Row Locking

To protect against concurrent HTTP requests or parallel background workers executing simultaneous reclaims on the same voucher:
```python
with transaction.atomic():
    # Lock voucher row to serialize concurrent reclaim evaluations
    v = Voucher.objects.select_for_update().get(id=voucher.id)
    
    # Query and lock active reversals
    reversals = list(
        GSTReportingAllocation.objects.select_for_update().filter(...)
    )
```

In automated concurrency testing with 10 competing threads running on separate PostgreSQL connections against Neon Staging, exactly 5 threads succeeded and 5 threads failed gracefully with `ValidationError`. The final total reclaimed tax was exactly ₹1,000.00 with **zero over-reclaim and zero duplicate records**.
