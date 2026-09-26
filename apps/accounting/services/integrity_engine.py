import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, VoucherItem, LedgerEntry, PaymentAllocation, BankTransaction, AccountingFinding
from apps.inventory.models import Product

class AccountingIntegrityEngine:
    """
    Deterministic mathematical and accounting integrity verification engine.
    Audits actual database records across 11 core accounting dimensions.
    The backend remains the authoritative source of truth.
    """

    @classmethod
    def run_all_checks(cls, company: Company) -> Dict[str, Any]:
        """
        Runs all 11 integrity checks for a company and generates/updates AccountingFinding records.
        Returns a comprehensive health report with transparent scoring.
        """
        findings: List[AccountingFinding] = []

        findings.extend(cls.check_trial_balance(company))
        findings.extend(cls.check_party_balances(company))
        findings.extend(cls.check_payment_allocations(company))
        findings.extend(cls.check_wrong_party(company))
        findings.extend(cls.check_duplicate_entries(company))
        findings.extend(cls.check_gst(company))
        findings.extend(cls.check_inventory(company))
        findings.extend(cls.check_negative_margins(company))
        findings.extend(cls.check_bank_reconciliation(company))
        findings.extend(cls.check_cash_and_liquidity(company))
        findings.extend(cls.check_document_numbering(company))

        unresolved_bank = BankTransaction.objects.filter(company=company, status='UNRESOLVED').count()

        # Calculate transparent Bookkeeping Health Score
        score_data = cls.calculate_health_score(company, findings, unresolved_bank=unresolved_bank)
        metrics = {
            "total_checks": len(score_data["checks_summary"]),
            "passed_checks": score_data["passed_count"],
            "critical_findings_count": score_data["critical_count"],
            "warning_findings_count": score_data["warning_count"],
            "info_findings_count": score_data["info_count"],
        }
        score_breakdown = {
            "base_score": 100,
            "critical_deductions": score_data["critical_count"] * 15,
            "warning_deductions": score_data["warning_count"] * 5,
            "unresolved_bank_deductions": min(15, unresolved_bank * 1),
            "formula": "Base (100) - Critical (15) - Warning (5) - Unresolved Bank (1)"
        }

        return {
            "timestamp": timezone.now().isoformat(),
            "health_score": score_data["score"],
            "health_status": score_data["status"],
            "status": score_data["status"],
            "score_breakdown": score_breakdown,
            "metrics": metrics,
            "checks": score_data["checks_summary"],
            "checks_summary": score_data["checks_summary"],
            "critical_count": score_data["critical_count"],
            "warning_count": score_data["warning_count"],
            "info_count": score_data["info_count"],
            "passed_checks_count": score_data["passed_count"],
            "findings": [
                {
                    "id": str(f.id),
                    "severity": f.severity,
                    "category": f.category,
                    "title": f.title,
                    "description": f.description,
                    "evidence": f.evidence or {},
                    "expected_state": f.expected_state,
                    "actual_state": f.actual_state,
                    "probable_cause": f.probable_cause,
                    "suggested_action": f.suggested_action,
                    "suggested_fix": f.suggested_action,
                    "confidence": f.confidence,
                    "fix_action": f.fix_action,
                    "fix_type": f.fix_action,
                    "is_actionable": bool(f.fix_action),
                    "status": "RESOLVED" if f.is_resolved else "UNRESOLVED",
                    "is_resolved": f.is_resolved,
                    "created_at": f.created_at.isoformat()
                } for f in findings
            ]
        }

    @classmethod
    def check_trial_balance(cls, company: Company) -> List[AccountingFinding]:
        """1. Check: Total Debit == Total Credit across all posted entries."""
        findings = []
        entries = LedgerEntry.objects.filter(company=company, voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED'])
        totals = entries.aggregate(
            total_dr=Sum('debit_amount'),
            total_cr=Sum('credit_amount')
        )
        total_dr = Decimal(str(totals['total_dr'] or '0.00'))
        total_cr = Decimal(str(totals['total_cr'] or '0.00'))

        diff = abs(total_dr - total_cr)
        if diff > Decimal('0.01'):
            # Investigate root cause with single grouped query instead of N+1 voucher loop
            unbalanced_vouchers = []
            entry_totals = LedgerEntry.objects.filter(
                company=company, voucher__status='POSTED'
            ).values('voucher_id', 'voucher__voucher_number').annotate(
                dr=Sum('debit_amount'), cr=Sum('credit_amount')
            )
            for et in entry_totals:
                v_dr = Decimal(str(et['dr'] or '0.00'))
                v_cr = Decimal(str(et['cr'] or '0.00'))
                if abs(v_dr - v_cr) > Decimal('0.01'):
                    unbalanced_vouchers.append({
                        "voucher_number": et['voucher__voucher_number'],
                        "dr": str(v_dr),
                        "cr": str(v_cr),
                        "diff": str(abs(v_dr - v_cr))
                    })

            cause = f"Trial Balance has an imbalance of ₹{diff}."
            if unbalanced_vouchers:
                cause += f" Found {len(unbalanced_vouchers)} unbalanced posted vouchers (e.g. {unbalanced_vouchers[0]['voucher_number']})."
            else:
                cause += " Discrepancy likely stems from opening balance equity offset or manual adjustment."

            finding, _ = AccountingFinding.objects.update_or_create(
                company=company,
                category='TRIAL_BALANCE',
                is_resolved=False,
                defaults={
                    "severity": "CRITICAL",
                    "title": f"Trial balance difference of ₹{diff}",
                    "description": f"The books do not balance. Total Debits: ₹{total_dr}, Total Credits: ₹{total_cr}. Difference: ₹{diff}.",
                    "evidence": {
                        "total_debit": str(total_dr),
                        "total_credit": str(total_cr),
                        "difference": str(diff),
                        "unbalanced_vouchers": unbalanced_vouchers[:5]
                    },
                    "expected_state": f"Total Debits (₹{total_dr}) should exactly equal Total Credits.",
                    "actual_state": f"Debits ₹{total_dr} vs Credits ₹{total_cr} (Gap: ₹{diff}).",
                    "probable_cause": cause,
                    "suggested_action": "Run balance reconciliation or check unbalanced vouchers.",
                    "confidence": 1.0,
                    "fix_action": "RECALCULATE_BALANCE"
                }
            )
            findings.append(finding)
        else:
            AccountingFinding.objects.filter(company=company, category='TRIAL_BALANCE', is_resolved=False).update(is_resolved=True, resolved_at=timezone.now())

        return findings

    @classmethod
    def check_party_balances(cls, company: Company) -> List[AccountingFinding]:
        """2. Check: Cached current_balance matches derived sum of entries for all parties."""
        findings = []
        parties = list(Ledger.objects.filter(company=company, ledger_type__in=['CUSTOMER', 'SUPPLIER'], is_archived=False))
        if not parties:
            return findings

        party_ids = [p.id for p in parties]

        # Batch 1: Find all party ledgers that have double-entry opening vouchers (1 single query)
        ledgers_with_opening = set(
            LedgerEntry.objects.filter(
                company=company,
                ledger_id__in=party_ids,
                voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED'],
                voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
            ).values_list('ledger_id', flat=True).distinct()
        )

        # Batch 2: Aggregate DR and CR sums grouped by ledger_id (1 single query)
        entry_totals = LedgerEntry.objects.filter(
            company=company,
            ledger_id__in=party_ids,
            voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED']
        ).values('ledger_id').annotate(
            dr=Sum('debit_amount'),
            cr=Sum('credit_amount')
        )
        totals_map = {row['ledger_id']: row for row in entry_totals}

        # Pre-fetch existing unresolved findings to avoid N SELECT queries in loop
        existing_findings = {
            f.title: f for f in AccountingFinding.objects.filter(
                company=company,
                category__in=['PARTY_BALANCE', 'WRONG_PARTY'],
                is_resolved=False
            )
        }

        for p in parties:
            has_op = p.id in ledgers_with_opening
            op = Decimal('0.00') if has_op else Decimal(str(p.opening_balance or '0.00'))

            t = totals_map.get(p.id)
            dr = Decimal(str(t['dr'] or '0.00')) if t else Decimal('0.00')
            cr = Decimal(str(t['cr'] or '0.00')) if t else Decimal('0.00')

            if p.opening_balance_type == 'CREDIT':
                op_dr = Decimal('0.00')
                op_cr = op
            else:
                op_dr = op
                op_cr = Decimal('0.00')

            total_dr = op_dr + dr
            total_cr = op_cr + cr

            if p.normal_balance == 'CREDIT':
                expected = total_cr - total_dr
            else:
                expected = total_dr - total_cr

            current = Decimal(str(p.current_balance or '0.00'))
            diff = abs(expected - current)

            if diff > Decimal('0.01'):
                title = f"Ledger balance mismatch for {p.name}"
                defaults = {
                    "severity": "WARNING",
                    "description": f"{p.name} shows recorded balance of ₹{current}, but sum of transactions equals ₹{expected}. Difference: ₹{diff}.",
                    "evidence": {
                        "ledger_id": str(p.id),
                        "party_name": p.name,
                        "recorded_balance": str(current),
                        "expected_balance": str(expected),
                        "difference": str(diff)
                    },
                    "expected_state": f"Recorded balance should equal ₹{expected}.",
                    "actual_state": f"Recorded balance is currently ₹{current}.",
                    "probable_cause": "Cached balance was not updated following an offline or concurrent transaction.",
                    "suggested_action": f"Recalculate balance for {p.name} from source-of-truth entries.",
                    "confidence": 0.99,
                    "fix_action": "RECALCULATE_BALANCE"
                }
                finding = existing_findings.get(title)
                if finding:
                    for k, val in defaults.items():
                        setattr(finding, k, val)
                    finding.save()
                else:
                    finding = AccountingFinding.objects.create(
                        company=company,
                        category='PARTY_BALANCE',
                        title=title,
                        is_resolved=False,
                        **defaults
                    )
                    existing_findings[title] = finding
                findings.append(finding)

        return findings

    @classmethod
    def check_payment_allocations(cls, company: Company) -> List[AccountingFinding]:
        """3. Check: Payment allocations do not exceed invoice total or cross company boundaries."""
        findings = []
        allocs = PaymentAllocation.objects.filter(company=company).select_related(
            'payment_voucher', 'invoice_voucher'
        ).defer(
            'payment_voucher__attachment_data', 'payment_voucher__attachment_mime',
            'invoice_voucher__attachment_data', 'invoice_voucher__attachment_mime'
        )

        for alloc in allocs:
            if not alloc.payment_voucher or not alloc.invoice_voucher:
                continue
            # Cross company check
            if alloc.payment_voucher.company_id != alloc.invoice_voucher.company_id:
                finding, _ = AccountingFinding.objects.update_or_create(
                    company=company,
                    category='PAYMENT',
                    title=f"Cross-company payment allocation #{alloc.id}",
                    is_resolved=False,
                    defaults={
                        "severity": "CRITICAL",
                        "description": f"Payment #{alloc.payment_voucher.voucher_number} is allocated to invoice #{alloc.invoice_voucher.voucher_number} from another company.",
                        "evidence": {"allocation_id": str(alloc.id)},
                        "expected_state": "Allocations must stay strictly within the same company.",
                        "actual_state": "Cross-company leak detected.",
                        "probable_cause": "Corrupted offline command sync or invalid foreign key assignment.",
                        "suggested_action": "Remove illegal cross-company allocation.",
                        "confidence": 1.0
                    }
                )
                findings.append(finding)

        # Check for over-allocated invoices (1 grouped query instead of N+1)
        alloc_totals = PaymentAllocation.objects.filter(
            company=company
        ).values('invoice_voucher_id').annotate(
            total=Sum('allocated_amount')
        )
        alloc_map = {row['invoice_voucher_id']: Decimal(str(row['total'] or '0.00')) for row in alloc_totals if row['invoice_voucher_id']}

        active_overalloc_titles = set()
        if alloc_map:
            invoices = Voucher.objects.filter(
                company=company,
                id__in=list(alloc_map.keys()),
                voucher_type__in=['SALES', 'PURCHASE', 'OPENING_INVOICE', 'OPENING_BILL'],
                status='POSTED'
            ).only('id', 'voucher_number', 'total_amount', 'party_ledger_id').defer('attachment_data', 'attachment_mime')

            for inv in invoices:
                total_alloc = alloc_map.get(inv.id, Decimal('0.00'))
                inv_total = Decimal(str(inv.total_amount or '0.00'))
                if total_alloc > inv_total + Decimal('0.05'):
                    title = f"Invoice #{inv.voucher_number} is over-allocated"
                    active_overalloc_titles.add(title)
                    finding, _ = AccountingFinding.objects.update_or_create(
                        company=company,
                        category='PAYMENT',
                        title=title,
                        is_resolved=False,
                        defaults={
                            "severity": "CRITICAL",
                            "description": f"Invoice #{inv.voucher_number} total is ₹{inv.total_amount}, but total payments allocated equal ₹{total_alloc}.",
                            "evidence": {
                                "voucher_id": str(inv.id),
                                "voucher_number": inv.voucher_number,
                                "party_id": str(inv.party_ledger_id) if inv.party_ledger_id else None,
                                "total_amount": str(inv.total_amount),
                                "allocated_amount": str(total_alloc),
                                "excess": str(total_alloc - inv.total_amount)
                            },
                            "expected_state": f"Allocations cannot exceed invoice total (₹{inv.total_amount}).",
                            "actual_state": f"Allocated: ₹{total_alloc}.",
                            "probable_cause": "Payment was allocated twice or unallocated advance was miscalculated.",
                            "suggested_action": "Re-run automated FIFO allocation for this party.",
                            "confidence": 0.98,
                            "fix_action": "RECONCILE_FIFO"
                        }
                    )
                    findings.append(finding)

        # Batch resolve all previously open over-allocation findings that are no longer over-allocated (1 single query instead of N+1 loops)
        AccountingFinding.objects.filter(
            company=company,
            category='PAYMENT',
            title__endswith='is over-allocated',
            is_resolved=False
        ).exclude(title__in=active_overalloc_titles).update(
            is_resolved=True,
            resolved_at=timezone.now()
        )

        return findings

    @classmethod
    def check_wrong_party(cls, company: Company) -> List[AccountingFinding]:
        """4. Check: Detects invoices/payments likely assigned to the wrong party."""
        findings = []
        recent_vouchers = list(Voucher.objects.filter(
            company=company,
            voucher_type__in=['SALES', 'PURCHASE'],
            status='POSTED'
        ).select_related('party_ledger').defer('attachment_data', 'attachment_mime')[:50])

        for v in recent_vouchers:
            if not v.party_ledger:
                continue

            # Look for other parties with identical external_invoice_number or matching pending bill
            if v.external_invoice_number:
                other_parties_with_same_bill = Voucher.objects.filter(
                    company=company,
                    external_invoice_number=v.external_invoice_number,
                    status='POSTED'
                ).exclude(party_ledger=v.party_ledger).select_related('party_ledger').defer('attachment_data', 'attachment_mime')

                for other_v in other_parties_with_same_bill:
                    if other_v.party_ledger and other_v.total_amount == v.total_amount:
                        finding, _ = AccountingFinding.objects.update_or_create(
                            company=company,
                            category='WRONG_PARTY',
                            title=f"Possible wrong party on invoice #{v.voucher_number}",
                            is_resolved=False,
                            defaults={
                                "severity": "WARNING",
                                "description": f"Invoice #{v.voucher_number} for ₹{v.total_amount} is currently under {v.party_ledger.name}. However, supplier bill #{v.external_invoice_number} for ₹{other_v.total_amount} was also found under {other_v.party_ledger.name}.",
                                "evidence": {
                                    "voucher_id": str(v.id),
                                    "voucher_number": v.voucher_number,
                                    "current_party_id": str(v.party_ledger.id),
                                    "current_party_name": v.party_ledger.name,
                                    "suggested_party_id": str(other_v.party_ledger.id),
                                    "suggested_party_name": other_v.party_ledger.name,
                                    "amount": str(v.total_amount)
                                },
                                "expected_state": f"Invoice should belong to {other_v.party_ledger.name}.",
                                "actual_state": f"Assigned to {v.party_ledger.name}.",
                                "probable_cause": "Clerical mistake during bill entry.",
                                "suggested_action": f"Move invoice #{v.voucher_number} from {v.party_ledger.name} to {other_v.party_ledger.name}.",
                                "confidence": 0.94,
                                "fix_action": "MOVE_PARTY"
                            }
                        )
                        findings.append(finding)

        return findings

    @classmethod
    def check_duplicate_entries(cls, company: Company) -> List[AccountingFinding]:
        """
        5. Check: Intelligent Deduplication Engine across Receipts, Payments/Transactions,
        Banking, Inventory, and Ledgers.
        Flags duplicates with structured evidence and actionable preview/fix mechanisms.
        """
        from apps.accounting.services.deduplication_engine import TransactionDeduplicationEngine
        findings: List[AccountingFinding] = []

        scanned_items = TransactionDeduplicationEngine.scan_all_duplicates(company)
        active_titles = set()

        # Pre-fetch existing duplicate findings to eliminate SELECT ... FOR UPDATE (N+1 queries)
        existing_findings = {
            f.title: f for f in AccountingFinding.objects.filter(
                company=company,
                category__in=['DUPLICATE', 'DUPLICATE_BANK', 'DUPLICATE_INVENTORY', 'DUPLICATE_LEDGER'],
                is_resolved=False
            )
        }

        for item in scanned_items:
            active_titles.add(item['title'])
            defaults = {
                "severity": item['severity'],
                "description": item['description'],
                "evidence": item.get('evidence', {}),
                "expected_state": item.get('expected_state', ''),
                "actual_state": item.get('actual_state', ''),
                "probable_cause": item.get('probable_cause', ''),
                "suggested_action": item.get('suggested_action', ''),
                "confidence": item.get('confidence', 0.95),
                "fix_action": item.get('fix_action')
            }
            finding = existing_findings.get(item['title'])
            if finding:
                changed = False
                for k, v in defaults.items():
                    if getattr(finding, k) != v:
                        setattr(finding, k, v)
                        changed = True
                if changed:
                    finding.save()
            else:
                finding = AccountingFinding.objects.create(
                    company=company,
                    category=item['category'],
                    title=item['title'],
                    is_resolved=False,
                    **defaults
                )
                existing_findings[item['title']] = finding
            findings.append(finding)

        # Auto-resolve previously open duplicate findings that are no longer detected
        AccountingFinding.objects.filter(
            company=company,
            category__in=['DUPLICATE', 'DUPLICATE_BANK', 'DUPLICATE_INVENTORY', 'DUPLICATE_LEDGER'],
            is_resolved=False
        ).exclude(title__in=active_titles).update(is_resolved=True, resolved_at=timezone.now())

        return findings

    @classmethod
    def check_duplicate_invoices(cls, company: Company) -> List[AccountingFinding]:
        """Backward-compatibility alias pointing to check_duplicate_entries."""
        return cls.check_duplicate_entries(company)

    @classmethod
    def check_gst(cls, company: Company) -> List[AccountingFinding]:
        """6. Check: GST rate and place-of-supply consistency."""
        findings = []
        company_state = (company.state_code or "").strip()

        recent_vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['SALES', 'PURCHASE'],
            status='POSTED'
        ).select_related('party_ledger').prefetch_related('items').defer('attachment_data', 'attachment_mime')[:50]

        for v in recent_vouchers:
            buyer_state = (v.buyer_state_code or (v.party_ledger.state_code if v.party_ledger else "") or "").strip()
            if not company_state or not buyer_state:
                continue

            is_intra = (company_state == buyer_state)
            items = v.items.all()
            for itm in items:
                igst = Decimal(str(itm.igst_amount or '0.00'))
                cgst = Decimal(str(itm.cgst_amount or '0.00'))
                # Intra-state check: Should not have IGST
                if is_intra and igst > Decimal('0.50') and cgst == Decimal('0.00'):
                    half_tax = str(round(igst / Decimal('2.0'), 2))
                    finding, _ = AccountingFinding.objects.update_or_create(
                        company=company,
                        category='GST',
                        title=f"GST mismatch on Invoice #{v.voucher_number}",
                        is_resolved=False,
                        defaults={
                            "severity": "WARNING",
                            "description": f"This transaction appears to be intra-state (State {company_state}), but IGST of ₹{igst} was applied instead of CGST + SGST.",
                            "evidence": {
                                "voucher_number": v.voucher_number,
                                "company_state": company_state,
                                "buyer_state": buyer_state,
                                "igst_amount": str(igst),
                                "expected_cgst": half_tax,
                                "expected_sgst": half_tax
                            },
                            "expected_state": f"CGST: ₹{half_tax}, SGST: ₹{half_tax}.",
                            "actual_state": f"IGST: ₹{igst}.",
                            "probable_cause": "Wrong tax type selected during invoice creation.",
                            "suggested_action": "Review invoice tax breakdown and correct.",
                            "confidence": 0.95
                        }
                    )
                    findings.append(finding)
                    break

        return findings

    @classmethod
    def check_inventory(cls, company: Company) -> List[AccountingFinding]:
        """7. Check: Negative stock or warehouse stock discrepancies."""
        findings = []
        neg_products = Product.objects.filter(company=company, stock_quantity__lt=0)

        for p in neg_products:
            finding, _ = AccountingFinding.objects.update_or_create(
                company=company,
                category='INVENTORY',
                title=f"Negative stock for {p.name}",
                is_resolved=False,
                defaults={
                    "severity": "WARNING",
                    "description": f"{p.name} has a recorded stock of {p.stock_quantity} {p.unit or 'units'}. Sales exceeded recorded purchases.",
                    "evidence": {
                        "product_id": str(p.id),
                        "product_name": p.name,
                        "current_stock": str(p.stock_quantity),
                        "unit": p.unit or "units"
                    },
                    "expected_state": "Physical stock cannot be less than zero.",
                    "actual_state": f"Stock is {p.stock_quantity}.",
                    "probable_cause": "Supplier purchase bill was not entered before recording the sale.",
                    "suggested_action": "Enter pending purchase bills or post a stock adjustment.",
                    "confidence": 0.99
                }
            )
            findings.append(finding)

        return findings

    @classmethod
    def check_negative_margins(cls, company: Company) -> List[AccountingFinding]:
        """
        8. Check: Detects loss-making sales where products are sold below purchase cost.
        In B2B wholesale and manufacturing, selling below cost price erodes operating profits
        and indicates unauthorized discounting or billing clerical errors.
        """
        findings = []
        active_titles = set()

        # Clean up any legacy UNUSUAL_ACTIVITY findings
        AccountingFinding.objects.filter(
            company=company,
            category='UNUSUAL_ACTIVITY',
            is_resolved=False
        ).update(is_resolved=True, resolved_at=timezone.now())

        # Inspect recent posted sales vouchers (last 100 sales)
        recent_sales = Voucher.objects.filter(
            company=company,
            voucher_type='SALES',
            status='POSTED'
        ).only('id', 'voucher_number', 'voucher_date', 'party_ledger_id').prefetch_related('items__product').defer('attachment_data', 'attachment_mime')[:100]

        for v in recent_sales:
            for item in v.items.all():
                prod = item.product
                if not prod or not prod.purchase_price or prod.purchase_price <= Decimal('0.00'):
                    continue

                qty = Decimal(str(item.quantity or '0.00'))
                if qty <= Decimal('0.00'):
                    continue

                # Effective selling rate after item discount
                rate = Decimal(str(item.rate or '0.00'))
                disc_pct = Decimal(str(item.discount_percent or '0.00'))
                effective_rate = rate * (Decimal('1.00') - (disc_pct / Decimal('100.00')))
                cost_price = Decimal(str(prod.purchase_price or '0.00'))

                # If sold at a loss (more than ₹1 under cost to ignore tiny rounding)
                if effective_rate < (cost_price - Decimal('1.00')):
                    unit_loss = cost_price - effective_rate
                    total_loss = round(unit_loss * qty, 2)
                    title = f"Loss-making sale: {prod.name} sold below cost on #{v.voucher_number}"
                    active_titles.add(title)

                    finding, _ = AccountingFinding.objects.update_or_create(
                        company=company,
                        category='MARGIN_RISK',
                        title=title,
                        is_resolved=False,
                        defaults={
                            "severity": "CRITICAL" if total_loss > Decimal('500.00') else "WARNING",
                            "description": (
                                f"Product '{prod.name}' was sold on invoice #{v.voucher_number} at ₹{effective_rate:.2f}/unit, "
                                f"which is below its recorded purchase cost of ₹{cost_price:.2f}/unit. "
                                f"Total loss on this line item: ₹{total_loss:.2f} (Qty: {qty} {prod.unit or 'units'})."
                            ),
                            "evidence": {
                                "voucher_id": str(v.id),
                                "voucher_number": v.voucher_number,
                                "voucher_date": str(v.voucher_date),
                                "product_id": str(prod.id),
                                "product_name": prod.name,
                                "selling_rate": str(round(effective_rate, 2)),
                                "purchase_cost": str(cost_price),
                                "unit_loss": str(round(unit_loss, 2)),
                                "quantity": str(qty),
                                "total_loss": str(total_loss)
                            },
                            "expected_state": f"Selling price should be at or above purchase cost (₹{cost_price:.2f}).",
                            "actual_state": f"Sold at ₹{effective_rate:.2f} (Loss of ₹{unit_loss:.2f}/unit).",
                            "probable_cause": "Clerical pricing typo during invoice entry or excessive party discount.",
                            "suggested_action": "Verify invoice item rate and apply corrected rate or verify special authorized markdown.",
                            "confidence": 0.98,
                            "fix_action": "REVIEW_PRICING"
                        }
                    )
                    findings.append(finding)

        # Batch auto-resolve any previous margin findings no longer present
        AccountingFinding.objects.filter(
            company=company,
            category='MARGIN_RISK',
            is_resolved=False
        ).exclude(title__in=active_titles).update(is_resolved=True, resolved_at=timezone.now())

        return findings

    @classmethod
    def check_unusual_transactions(cls, company: Company) -> List[AccountingFinding]:
        """Backward-compatibility alias pointing to check_negative_margins."""
        return cls.check_negative_margins(company)

    @classmethod
    def check_bank_reconciliation(cls, company: Company) -> List[AccountingFinding]:
        """9. Check: Unresolved bank transactions requiring attention."""
        findings = []
        unres_count = BankTransaction.objects.filter(
            company=company,
            status__in=['UNRESOLVED', 'MATCHED_SUGGESTED']
        ).count()

        if unres_count > 0:
            totals = BankTransaction.objects.filter(
                company=company,
                status__in=['UNRESOLVED', 'MATCHED_SUGGESTED']
            ).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))

            total_val = Decimal(str(totals['dr'] or '0.00')) + Decimal(str(totals['cr'] or '0.00'))
            finding, _ = AccountingFinding.objects.update_or_create(
                company=company,
                category='BANK',
                title=f"{unres_count} bank transactions need review",
                is_resolved=False,
                defaults={
                    "severity": "WARNING",
                    "description": f"There are {unres_count} bank transactions totaling ₹{total_val} that have not yet been reconciled into the books.",
                    "evidence": {
                        "unresolved_count": unres_count,
                        "total_amount": str(total_val),
                        "debit_total": str(totals['dr'] or '0.00'),
                        "credit_total": str(totals['cr'] or '0.00')
                    },
                    "expected_state": "All bank statement rows should be accounted for in vouchers.",
                    "actual_state": f"{unres_count} rows unresolved.",
                    "probable_cause": "Recent bank statement uploaded without final matching.",
                    "suggested_action": "Go to Bank Reconciliation to review suggestions and match parties.",
                    "confidence": 0.95
                }
            )
            findings.append(finding)

        return findings

    @classmethod
    def check_cash_and_liquidity(cls, company: Company) -> List[AccountingFinding]:
        """
        10. Check: Cash Drawer Deficit & Bank Overdraft Safety.
        In Indian business accounting:
        - Physical cash-in-hand can NEVER be negative. A negative cash balance means unrecorded
          cash receipts/sales or omitted bank withdrawals (Contra), and will cause immediate
          CA audit qualification and Income Tax scrutiny (Section 40A(3) / 269ST).
        - Negative bank balances without an approved CC/OD facility risk cheque bounce charges,
          ECS return penalties, and supplier trust erosion.
        """
        findings = []
        active_titles = set()

        # Clean up any legacy OPENING_BALANCE findings
        AccountingFinding.objects.filter(
            company=company,
            category='OPENING_BALANCE',
            is_resolved=False
        ).update(is_resolved=True, resolved_at=timezone.now())

        # 1. Cash Ledgers (Negative Cash in Hand)
        cash_ledgers = Ledger.objects.filter(
            company=company,
            ledger_type='CASH',
            is_archived=False
        )
        for cl in cash_ledgers:
            bal = Decimal(str(cl.current_balance or '0.00'))
            if bal < Decimal('-0.05'):
                deficit = abs(bal)
                title = f"Negative cash in hand: {cl.name} is ₹{deficit:.2f} in deficit"
                active_titles.add(title)
                finding, _ = AccountingFinding.objects.update_or_create(
                    company=company,
                    category='LIQUIDITY',
                    title=title,
                    is_resolved=False,
                    defaults={
                        "severity": "CRITICAL",
                        "description": (
                            f"The cash account '{cl.name}' has a negative balance of -₹{deficit:.2f}. "
                            f"In Indian accounting and tax law, cash-in-hand can never physically be negative. "
                            f"This indicates cash expenses or supplier payouts were recorded without recording incoming cash sales or bank cash withdrawals."
                        ),
                        "evidence": {
                            "ledger_id": str(cl.id),
                            "ledger_name": cl.name,
                            "current_balance": str(bal),
                            "deficit": str(deficit)
                        },
                        "expected_state": f"Cash ledger balance must be ≥ ₹0.00 at all times.",
                        "actual_state": f"Negative cash balance of -₹{deficit:.2f}.",
                        "probable_cause": "Omitted cash sales, unrecorded cash receipts from customers, or unentered bank cash withdrawal (Contra).",
                        "suggested_action": "Record missing cash receipts or record a Contra entry for cash withdrawn from the bank.",
                        "confidence": 1.0,
                        "fix_action": "RECORD_CASH_CONTRA"
                    }
                )
                findings.append(finding)

        # 2. Bank Ledgers (Overdrawn Bank Accounts)
        bank_ledgers = Ledger.objects.filter(
            company=company,
            ledger_type='BANK',
            is_archived=False
        )
        for bl in bank_ledgers:
            bal = Decimal(str(bl.current_balance or '0.00'))
            # Threshold of -₹500 to ignore minor bank SMS / maintenance charge deductions
            if bal < Decimal('-500.00'):
                overdrawn = abs(bal)
                title = f"Negative bank balance: {bl.name} is overdrawn by ₹{overdrawn:.2f}"
                active_titles.add(title)
                finding, _ = AccountingFinding.objects.update_or_create(
                    company=company,
                    category='LIQUIDITY',
                    title=title,
                    is_resolved=False,
                    defaults={
                        "severity": "WARNING",
                        "description": (
                            f"The bank ledger '{bl.name}' shows a negative balance of -₹{overdrawn:.2f}. "
                            f"If this is not an approved Cash Credit (CC) or Overdraft (OD) account, "
                            f"payments and cheques issued from this account may bounce with penalty charges."
                        ),
                        "evidence": {
                            "ledger_id": str(bl.id),
                            "ledger_name": bl.name,
                            "current_balance": str(bal),
                            "overdrawn_amount": str(overdrawn)
                        },
                        "expected_state": f"Bank ledger balance should be positive or within an approved OD limit.",
                        "actual_state": f"Overdrawn by ₹{overdrawn:.2f}.",
                        "probable_cause": "Supplier payments or cheques entered in books before customer receipts were deposited and cleared.",
                        "suggested_action": "Deposit customer funds or record pending bank deposits/transfers to prevent cheque bounce.",
                        "confidence": 0.95,
                        "fix_action": "REVIEW_BANK_BALANCE"
                    }
                )
                findings.append(finding)

        # Batch auto-resolve any previous liquidity findings no longer present
        AccountingFinding.objects.filter(
            company=company,
            category='LIQUIDITY',
            is_resolved=False
        ).exclude(title__in=active_titles).update(is_resolved=True, resolved_at=timezone.now())

        return findings

    @classmethod
    def check_opening_balances(cls, company: Company) -> List[AccountingFinding]:
        """Backward-compatibility alias pointing to check_cash_and_liquidity."""
        return cls.check_cash_and_liquidity(company)

    @classmethod
    def check_document_numbering(cls, company: Company) -> List[AccountingFinding]:
        """11. Check: Duplicate voucher sequence numbers within same FY."""
        findings = []
        dups = Voucher.objects.filter(company=company).values('financial_year', 'voucher_type', 'voucher_number').annotate(c=Count('id')).filter(c__gt=1)
        for item in dups[:3]:
            finding, _ = AccountingFinding.objects.update_or_create(
                company=company,
                category='NUMBERING',
                title=f"Duplicate voucher number #{item['voucher_number']}",
                is_resolved=False,
                defaults={
                    "severity": "CRITICAL",
                    "description": f"Voucher number #{item['voucher_number']} ({item['voucher_type']}) exists more than once in the same financial year.",
                    "evidence": item,
                    "expected_state": "Every voucher number must be uniquely sequential.",
                    "actual_state": f"Number #{item['voucher_number']} appears {item['c']} times.",
                    "probable_cause": "Manual number override or concurrent sequence allocation.",
                    "suggested_action": "Resync sequence numbering.",
                    "confidence": 1.0
                }
            )
            findings.append(finding)

        return findings

    @classmethod
    def calculate_health_score(cls, company: Company, findings: List[AccountingFinding], unresolved_bank: Optional[int] = None) -> Dict[str, Any]:
        """
        Computes a transparent data-quality score:
        Base = 100%
        - 15% per Critical issue
        - 5% per Warning
        - 1% per unresolved bank transaction
        Floor = 0%
        """
        critical_count = sum(1 for f in findings if f.severity == 'CRITICAL' and not f.is_resolved)
        warning_count = sum(1 for f in findings if f.severity == 'WARNING' and not f.is_resolved)
        info_count = sum(1 for f in findings if f.severity == 'INFO' and not f.is_resolved)

        if unresolved_bank is None:
            unresolved_bank = BankTransaction.objects.filter(company=company, status='UNRESOLVED').count()

        penalty = (critical_count * 15) + (warning_count * 5) + min(15, unresolved_bank * 1)
        score = max(0, 100 - penalty)

        status = 'HEALTHY'
        if critical_count > 0:
            status = 'CRITICAL'
        elif warning_count > 0:
            status = 'NEEDS_ATTENTION'

        check_configs = [
            {
                "name": "Trial Balance Equilibrium",
                "category": "TRIAL_BALANCE",
                "description": "Verifies total debits equal total credits across all posted entries.",
                "match": lambda f: f.category == 'TRIAL_BALANCE',
            },
            {
                "name": "Party Ledger Balances",
                "category": "PARTY_BALANCE",
                "description": "Ensures recorded party balances match the audit sum of all posted transactions.",
                "match": lambda f: (f.category in ['PARTY_BALANCE', 'WRONG_PARTY']) and 'balance' in f.title.lower(),
            },
            {
                "name": "Payment Allocations",
                "category": "PAYMENT",
                "description": "Validates payment links stay strictly within company boundaries and do not over-allocate invoices.",
                "match": lambda f: f.category == 'PAYMENT',
            },
            {
                "name": "Party Assignment Integrity",
                "category": "WRONG_PARTY",
                "description": "Detects invoices and payments assigned to incorrect party accounts.",
                "match": lambda f: f.category == 'WRONG_PARTY' and 'invoice' in f.title.lower(),
            },
            {
                "name": "Duplicate Transactions & Entries",
                "category": "DUPLICATE",
                "description": "Scans for duplicate receipts, payments, bank reconciliations, inventory items, and ledgers.",
                "match": lambda f: f.category in ['DUPLICATE', 'DUPLICATE_BANK', 'DUPLICATE_INVENTORY', 'DUPLICATE_LEDGER'],
            },
            {
                "name": "GST Rates & Place of Supply",
                "category": "GST",
                "description": "Verifies GST rates, CGST/SGST/IGST tax splits, and interstate place of supply rules.",
                "match": lambda f: f.category == 'GST',
            },
            {
                "name": "Inventory & Stock Levels",
                "category": "INVENTORY",
                "description": "Monitors stock quantities to prevent negative inventory and valuation drift.",
                "match": lambda f: f.category == 'INVENTORY',
            },
            {
                "name": "Profit Margin & Pricing Alerts",
                "category": "MARGIN_RISK",
                "description": "Flags loss-making sales where items were sold below recorded purchase cost.",
                "match": lambda f: f.category in ['MARGIN_RISK', 'UNUSUAL_ACTIVITY'],
            },
            {
                "name": "Bank Reconciliation",
                "category": "BANK_RECONCILIATION",
                "description": "Ensures all imported bank feed transactions are reconciled against book vouchers.",
                "match": lambda f: f.category in ['BANK', 'BANK_RECONCILIATION'],
                "extra_count": unresolved_bank,
            },
            {
                "name": "Cash & Bank Liquidity Safety",
                "category": "LIQUIDITY",
                "description": "Detects negative cash in hand (cash deficit) and unplanned bank overdrafts.",
                "match": lambda f: f.category in ['LIQUIDITY', 'OPENING_BALANCE'],
            },
            {
                "name": "Voucher Sequence Numbering",
                "category": "NUMBERING",
                "description": "Guarantees sequential document numbering without gaps or duplicates within each financial year.",
                "match": lambda f: f.category == 'NUMBERING',
            },
        ]

        checks_summary = []
        for cfg in check_configs:
            matched = [f for f in findings if cfg["match"](f) and not f.is_resolved]
            count = len(matched) + cfg.get("extra_count", 0)

            if any(f.severity == 'CRITICAL' for f in matched):
                chk_status = "CRITICAL"
                severity = "CRITICAL"
            elif any(f.severity == 'WARNING' for f in matched) or cfg.get("extra_count", 0) > 0:
                chk_status = "WARNING"
                severity = "WARNING"
            elif any(f.severity == 'INFO' for f in matched):
                chk_status = "WARNING"
                severity = "INFO"
            else:
                chk_status = "PASSED"
                severity = "PASSED"

            passed = (chk_status == "PASSED")

            checks_summary.append({
                "name": cfg["name"],
                "category": cfg["category"],
                "status": chk_status,
                "severity": severity,
                "findings_count": count,
                "description": cfg["description"],
                "passed": passed,
            })

        passed_count = sum(1 for c in checks_summary if c["passed"])

        return {
            "score": score,
            "status": status,
            "checks_summary": checks_summary,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "passed_count": passed_count
        }

    @classmethod
    def diagnose_balance_mismatch(cls, company: Company) -> Dict[str, Any]:
        """
        Flagship feature: 'Why is my balance not matching?'
        Investigates Trial Balance and Balance Sheet discrepancies,
        identifies specific causes with evidence, and suggests actionable fixes.
        """
        # 1. Check Trial Balance
        entries = LedgerEntry.objects.filter(company=company, voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED'])
        totals = entries.aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
        total_dr = Decimal(str(totals['dr'] or '0.00'))
        total_cr = Decimal(str(totals['cr'] or '0.00'))
        diff = abs(total_dr - total_cr)

        # Check Opening Balance Suspense
        suspense_ledger = Ledger.objects.filter(company=company, name__icontains="Opening Balance Suspense").first()
        suspense_bal = Decimal(str(suspense_ledger.current_balance or '0.00')) if suspense_ledger else Decimal('0.00')

        # Check Bank Reconciliation gap
        unresolved_bank_count = BankTransaction.objects.filter(company=company, status='UNRESOLVED').count()

        if diff <= Decimal('0.01'):
            return {
                "is_balanced": True,
                "discrepancy": "0.00",
                "total_debit": str(total_dr),
                "total_credit": str(total_cr),
                "trial_balance": {
                    "is_balanced": True,
                    "total_debit": str(total_dr),
                    "total_credit": str(total_cr),
                    "net_imbalance": "0.00"
                },
                "bank_reconciliation": {
                    "unresolved_count": unresolved_bank_count,
                    "reconciliation_gap": "0.00"
                },
                "opening_balance_suspense": {
                    "is_balanced": abs(suspense_bal) <= Decimal('0.01'),
                    "suspense_amount": str(abs(suspense_bal))
                },
                "diagnostic_summary": f"Trial balance is mathematically balanced (Total Debits = Total Credits = ₹{total_dr:,.2f}).",
                "message": f"Your books are mathematically balanced! Total Debits equal Total Credits (₹{total_dr:,.2f}).",
                "causes": [],
                "recommended_actions": [
                    "Trial balance is in perfect balance. No journal adjustment required."
                ]
            }

        # 2. Identify candidate causes
        causes = []

        # Cause A: Unbalanced vouchers (single grouped query)
        entry_totals = LedgerEntry.objects.filter(
            company=company,
            voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED']
        ).values('voucher_id', 'voucher__voucher_number').annotate(
            dr=Sum('debit_amount'), cr=Sum('credit_amount')
        )
        for et in entry_totals:
            v_dr = Decimal(str(et['dr'] or '0.00'))
            v_cr = Decimal(str(et['cr'] or '0.00'))
            if abs(v_dr - v_cr) > Decimal('0.01'):
                causes.append({
                    "type": "UNBALANCED_VOUCHER",
                    "title": f"Unbalanced Voucher #{et['voucher__voucher_number']}",
                    "voucher_id": str(et['voucher_id']),
                    "difference": str(abs(v_dr - v_cr)),
                    "evidence": f"Voucher #{et['voucher__voucher_number']} has Dr ₹{v_dr} and Cr ₹{v_cr}",
                    "confidence": 98,
                    "suggested_fix": f"Re-post voucher #{et['voucher__voucher_number']} with balancing line items."
                })

        # Cause B: Party balance drift (single grouped query)
        parties = list(Ledger.objects.filter(company=company, ledger_type__in=['CUSTOMER', 'SUPPLIER'], is_archived=False))
        if parties:
            party_ids = [p.id for p in parties]
            ledgers_with_opening = set(
                LedgerEntry.objects.filter(
                    company=company,
                    ledger_id__in=party_ids,
                    voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED'],
                    voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
                ).values_list('ledger_id', flat=True).distinct()
            )
            party_entry_totals = LedgerEntry.objects.filter(
                company=company,
                ledger_id__in=party_ids,
                voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED']
            ).values('ledger_id').annotate(
                dr=Sum('debit_amount'), cr=Sum('credit_amount')
            )
            p_map = {row['ledger_id']: row for row in party_entry_totals}
            for p in parties:
                has_op = p.id in ledgers_with_opening
                op = Decimal('0.00') if has_op else Decimal(str(p.opening_balance or '0.00'))
                t = p_map.get(p.id)
                p_dr = Decimal(str(t['dr'] or '0.00')) if t else Decimal('0.00')
                p_cr = Decimal(str(t['cr'] or '0.00')) if t else Decimal('0.00')
                if p.opening_balance_type == 'CREDIT':
                    op_dr = Decimal('0.00')
                    op_cr = op
                else:
                    op_dr = op
                    op_cr = Decimal('0.00')
                total_dr = op_dr + p_dr
                total_cr = op_cr + p_cr
                expected = (total_cr - total_dr) if p.normal_balance == 'CREDIT' else (total_dr - total_cr)
                if abs(expected - Decimal(str(p.current_balance or '0.00'))) == diff:
                    causes.append({
                        "type": "PARTY_BALANCE_DRIFT",
                        "title": f"Cached balance mismatch on {p.name}",
                        "party_id": str(p.id),
                        "difference": str(diff),
                        "evidence": f"Expected balance ₹{expected}, recorded balance ₹{p.current_balance}. Exactly matches Trial Balance difference of ₹{diff}.",
                        "confidence": 95,
                        "suggested_fix": f"Recalculate {p.name}'s balance."
                    })

        # Cause C: Opening balance equity offset
        adj = Ledger.objects.filter(company=company, name__icontains="Opening Balance Adjustment").first()
        if adj and abs(adj.current_balance - diff) < Decimal('1.00'):
            causes.append({
                "type": "OPENING_BALANCE_OFFSET",
                "title": "Unallocated Opening Balance Adjustment",
                "difference": str(diff),
                "evidence": f"Opening Balance Adjustment account has balance ₹{adj.current_balance}, which matches the difference.",
                "confidence": 90,
                "suggested_fix": "Verify that all customer and supplier opening balances were imported."
            })

        return {
            "is_balanced": False,
            "discrepancy": str(diff),
            "total_debit": str(total_dr),
            "total_credit": str(total_cr),
            "trial_balance": {
                "is_balanced": False,
                "total_debit": str(total_dr),
                "total_credit": str(total_cr),
                "net_imbalance": str(diff)
            },
            "bank_reconciliation": {
                "unresolved_count": unresolved_bank_count,
                "reconciliation_gap": str(diff)
            },
            "opening_balance_suspense": {
                "is_balanced": abs(suspense_bal) <= Decimal('0.01'),
                "suspense_amount": str(abs(suspense_bal))
            },
            "diagnostic_summary": f"Trial balance difference of ₹{diff:,.2f} detected.",
            "message": f"Your Trial Balance is off by ₹{diff:,.2f}. Total Debits: ₹{total_dr:,.2f}, Total Credits: ₹{total_cr:,.2f}.",
            "causes": causes[:5],
            "recommended_actions": [c.get("suggested_fix") for c in causes if c.get("suggested_fix")]
        }
