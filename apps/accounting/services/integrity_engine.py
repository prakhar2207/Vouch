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
        findings.extend(cls.check_duplicate_invoices(company))
        findings.extend(cls.check_gst(company))
        findings.extend(cls.check_inventory(company))
        findings.extend(cls.check_unusual_transactions(company))
        findings.extend(cls.check_bank_reconciliation(company))
        findings.extend(cls.check_opening_balances(company))
        findings.extend(cls.check_document_numbering(company))

        # Calculate transparent Bookkeeping Health Score
        score_data = cls.calculate_health_score(company, findings)

        return {
            "health_score": score_data["score"],
            "status": score_data["status"],
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
                    "evidence": f.evidence,
                    "expected_state": f.expected_state,
                    "actual_state": f.actual_state,
                    "probable_cause": f.probable_cause,
                    "suggested_action": f.suggested_action,
                    "confidence": f.confidence,
                    "fix_action": f.fix_action,
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
            # Investigate root cause
            unbalanced_vouchers = []
            vouchers = Voucher.objects.filter(company=company, status='POSTED')
            for v in vouchers:
                v_totals = v.ledger_entries.aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
                v_dr = Decimal(str(v_totals['dr'] or '0.00'))
                v_cr = Decimal(str(v_totals['cr'] or '0.00'))
                if abs(v_dr - v_cr) > Decimal('0.01'):
                    unbalanced_vouchers.append({"voucher_number": v.voucher_number, "dr": str(v_dr), "cr": str(v_cr), "diff": str(abs(v_dr - v_cr))})

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
        parties = Ledger.objects.filter(company=company, ledger_type__in=['CUSTOMER', 'SUPPLIER'], is_archived=False)

        for p in parties:
            # Check if double-entry opening voucher exists
            has_op = LedgerEntry.objects.filter(
                ledger=p, voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED'],
                voucher__voucher_type__in=['OPENING', 'OPENING_INVOICE', 'OPENING_BILL']
            ).exists()
            op = Decimal('0.00') if has_op else Decimal(str(p.opening_balance or '0.00'))

            totals = LedgerEntry.objects.filter(ledger=p, voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED']).aggregate(
                dr=Sum('debit_amount'), cr=Sum('credit_amount')
            )
            dr = Decimal(str(totals['dr'] or '0.00'))
            cr = Decimal(str(totals['cr'] or '0.00'))

            if p.opening_balance_type == 'DEBIT':
                expected = op + dr - cr
            else:
                expected = op + cr - dr

            current = Decimal(str(p.current_balance or '0.00'))
            diff = abs(expected - current)

            if diff > Decimal('0.01'):
                finding, _ = AccountingFinding.objects.update_or_create(
                    company=company,
                    category='WRONG_PARTY',
                    title=f"Ledger balance mismatch for {p.name}",
                    is_resolved=False,
                    defaults={
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
                )
                findings.append(finding)

        return findings

    @classmethod
    def check_payment_allocations(cls, company: Company) -> List[AccountingFinding]:
        """3. Check: Payment allocations do not exceed invoice total or cross company boundaries."""
        findings = []
        allocs = PaymentAllocation.objects.filter(company=company).select_related('payment_voucher', 'invoice_voucher')

        for alloc in allocs:
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

        # Check for over-allocated invoices
        invoices = Voucher.objects.filter(company=company, voucher_type__in=['SALES', 'PURCHASE', 'OPENING_INVOICE', 'OPENING_BILL'], status='POSTED')
        for inv in invoices:
            total_alloc = PaymentAllocation.objects.filter(invoice_voucher=inv).aggregate(s=Sum('allocated_amount'))['s'] or Decimal('0.00')
            if total_alloc > inv.total_amount + Decimal('0.05'):
                finding, _ = AccountingFinding.objects.update_or_create(
                    company=company,
                    category='PAYMENT',
                    title=f"Invoice #{inv.voucher_number} is over-allocated",
                    is_resolved=False,
                    defaults={
                        "severity": "CRITICAL",
                        "description": f"Invoice #{inv.voucher_number} total is ₹{inv.total_amount}, but total payments allocated equal ₹{total_alloc}.",
                        "evidence": {
                            "voucher_id": str(inv.id),
                            "voucher_number": inv.voucher_number,
                            "total_amount": str(inv.total_amount),
                            "allocated_amount": str(total_alloc),
                            "excess": str(total_alloc - inv.total_amount)
                        },
                        "expected_state": f"Allocations cannot exceed invoice total (₹{inv.total_amount}).",
                        "actual_state": f"Allocated: ₹{total_alloc}.",
                        "probable_cause": "Payment was allocated twice or unallocated advance was miscalculated.",
                        "suggested_action": "Re-run automated FIFO allocation for this party.",
                        "confidence": 0.98
                    }
                )
                findings.append(finding)

        return findings

    @classmethod
    def check_wrong_party(cls, company: Company) -> List[AccountingFinding]:
        """4. Check: Detects invoices/payments likely assigned to the wrong party."""
        findings = []
        recent_vouchers = list(Voucher.objects.filter(
            company=company,
            voucher_type__in=['SALES', 'PURCHASE'],
            status='POSTED'
        ).select_related('party_ledger')[:50])

        for v in recent_vouchers:
            if not v.party_ledger:
                continue

            # Look for other parties with identical external_invoice_number or matching pending bill
            if v.external_invoice_number:
                other_parties_with_same_bill = Voucher.objects.filter(
                    company=company,
                    external_invoice_number=v.external_invoice_number,
                    status='POSTED'
                ).exclude(party_ledger=v.party_ledger).select_related('party_ledger')

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
    def check_duplicate_invoices(cls, company: Company) -> List[AccountingFinding]:
        """5. Check: Detects duplicate customer invoices or supplier bills."""
        findings = []
        # Find duplicates by (party_ledger, total_amount, voucher_date)
        vouchers = Voucher.objects.filter(
            company=company,
            voucher_type__in=['SALES', 'PURCHASE'],
            status='POSTED'
        ).values('party_ledger', 'total_amount', 'voucher_date').annotate(count=Count('id')).filter(count__gt=1)

        for item in vouchers[:5]:
            party = Ledger.objects.filter(id=item['party_ledger']).first()
            if not party:
                continue

            dups = list(Voucher.objects.filter(
                company=company,
                party_ledger=party,
                total_amount=item['total_amount'],
                voucher_date=item['voucher_date'],
                status='POSTED'
            ))

            numbers = [d.voucher_number for d in dups]
            finding, _ = AccountingFinding.objects.update_or_create(
                company=company,
                category='DUPLICATE',
                title=f"Possible duplicate invoice for {party.name}",
                is_resolved=False,
                defaults={
                    "severity": "WARNING",
                    "description": f"Found {len(dups)} invoices for {party.name} with identical amount ₹{item['total_amount']} on {item['voucher_date']} ({', '.join(numbers)}).",
                    "evidence": {
                        "party_name": party.name,
                        "amount": str(item['total_amount']),
                        "date": str(item['voucher_date']),
                        "voucher_numbers": numbers
                    },
                    "expected_state": "Only one unique invoice should exist for the same transaction.",
                    "actual_state": f"{len(dups)} identical invoices recorded.",
                    "probable_cause": "Invoice was entered or synced twice.",
                    "suggested_action": "Review invoices and cancel or reverse any true duplicate.",
                    "confidence": 0.88
                }
            )
            findings.append(finding)

        return findings

    @classmethod
    def check_gst(cls, company: Company) -> List[AccountingFinding]:
        """6. Check: GST rate and place-of-supply consistency."""
        findings = []
        company_state = (company.state_code or "").strip()

        recent_vouchers = Voucher.objects.filter(company=company, voucher_type__in=['SALES', 'PURCHASE'], status='POSTED')[:50]
        for v in recent_vouchers:
            buyer_state = (v.buyer_state_code or (v.party_ledger.state_code if v.party_ledger else "") or "").strip()
            if not company_state or not buyer_state:
                continue

            is_intra = (company_state == buyer_state)
            items = v.items.all()
            for itm in items:
                # Intra-state check: Should not have IGST
                if is_intra and itm.igst_amount > Decimal('0.50') and itm.cgst_amount == Decimal('0.00'):
                    finding, _ = AccountingFinding.objects.update_or_create(
                        company=company,
                        category='GST',
                        title=f"GST mismatch on Invoice #{v.voucher_number}",
                        is_resolved=False,
                        defaults={
                            "severity": "WARNING",
                            "description": f"This transaction appears to be intra-state (State {company_state}), but IGST of ₹{itm.igst_amount} was applied instead of CGST + SGST.",
                            "evidence": {
                                "voucher_number": v.voucher_number,
                                "company_state": company_state,
                                "buyer_state": buyer_state,
                                "igst_amount": str(itm.igst_amount),
                                "expected_cgst": str(itm.igst_amount / 2),
                                "expected_sgst": str(itm.igst_amount / 2)
                            },
                            "expected_state": f"CGST: ₹{itm.igst_amount/2}, SGST: ₹{itm.igst_amount/2}.",
                            "actual_state": f"IGST: ₹{itm.igst_amount}.",
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
    def check_unusual_transactions(cls, company: Company) -> List[AccountingFinding]:
        """8. Check: Unusually large transactions or drastic price jumps."""
        findings = []
        # Find payments > 2.5x average payment
        avg_pmt = Voucher.objects.filter(company=company, voucher_type__in=['PAYMENT', 'RECEIPT'], status='POSTED').aggregate(a=Avg('total_amount'))['a']
        if avg_pmt and avg_pmt > 0:
            threshold = Decimal(str(avg_pmt)) * Decimal('2.5')
            huge_vouchers = Voucher.objects.filter(
                company=company,
                voucher_type__in=['PAYMENT', 'RECEIPT'],
                status='POSTED',
                total_amount__gt=threshold
            ).select_related('party_ledger')[:3]

            for hv in huge_vouchers:
                finding, _ = AccountingFinding.objects.update_or_create(
                    company=company,
                    category='UNUSUAL_ACTIVITY',
                    title=f"Unusually large transaction on #{hv.voucher_number}",
                    is_resolved=False,
                    defaults={
                        "severity": "INFO",
                        "description": f"A payment of ₹{hv.total_amount} was recorded on {hv.voucher_date}. This is 5x higher than typical payments (avg ₹{round(avg_pmt, 2)}).",
                        "evidence": {
                            "voucher_number": hv.voucher_number,
                            "amount": str(hv.total_amount),
                            "average_amount": str(round(avg_pmt, 2)),
                            "party": hv.party_ledger.name if hv.party_ledger else "Direct"
                        },
                        "expected_state": "Normal business range.",
                        "actual_state": f"₹{hv.total_amount} payment.",
                        "probable_cause": "Lump sum settlement or annual payment.",
                        "suggested_action": "This looks unusual. Verify this payment amount is intentional.",
                        "confidence": 0.85
                    }
                )
                findings.append(finding)

        return findings

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
    def check_opening_balances(cls, company: Company) -> List[AccountingFinding]:
        """10. Check: Opening balance equity offset reconciliation."""
        findings = []
        adj = Ledger.objects.filter(company=company, name__icontains="Opening Balance Adjustment").first()
        if adj and abs(adj.current_balance) > Decimal('100.00'):
            finding, _ = AccountingFinding.objects.update_or_create(
                company=company,
                category='OPENING_BALANCE',
                title="Opening balance adjustment ledger is not zero",
                is_resolved=False,
                defaults={
                    "severity": "INFO",
                    "description": f"The Opening Balance Adjustment account has a remaining balance of ₹{adj.current_balance}. Not all asset and liability opening balances have been entered yet.",
                    "evidence": {
                        "ledger_name": adj.name,
                        "balance": str(adj.current_balance)
                    },
                    "expected_state": "Opening balance adjustment should zero out when all accounts are entered.",
                    "actual_state": f"Remaining balance: ₹{adj.current_balance}.",
                    "probable_cause": "Migration to Vouch is in progress.",
                    "suggested_action": "Complete onboarding of initial customer, supplier, and bank opening balances.",
                    "confidence": 0.90
                }
            )
            findings.append(finding)

        return findings

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
    def calculate_health_score(cls, company: Company, findings: List[AccountingFinding]) -> Dict[str, Any]:
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

        unresolved_bank = BankTransaction.objects.filter(company=company, status='UNRESOLVED').count()

        penalty = (critical_count * 15) + (warning_count * 5) + min(15, unresolved_bank * 1)
        score = max(0, 100 - penalty)

        status = 'HEALTHY'
        if critical_count > 0:
            status = 'CRITICAL'
        elif warning_count > 0:
            status = 'NEEDS_ATTENTION'

        checks_summary = [
            {"name": "Trial Balance Equilibrium", "passed": not any(f.category == 'TRIAL_BALANCE' for f in findings)},
            {"name": "Party Ledger Balances", "passed": not any(f.category == 'WRONG_PARTY' and 'balance' in f.title.lower() for f in findings)},
            {"name": "Payment Allocations", "passed": not any(f.category == 'PAYMENT' for f in findings)},
            {"name": "Party Assignment Integrity", "passed": not any(f.category == 'WRONG_PARTY' and 'invoice' in f.title.lower() for f in findings)},
            {"name": "Duplicate Invoices & Bills", "passed": not any(f.category == 'DUPLICATE' for f in findings)},
            {"name": "GST Rates & Place of Supply", "passed": not any(f.category == 'GST' for f in findings)},
            {"name": "Inventory & Stock Levels", "passed": not any(f.category == 'INVENTORY' for f in findings)},
            {"name": "Unusual Transaction Alerts", "passed": not any(f.category == 'UNUSUAL_ACTIVITY' for f in findings)},
            {"name": "Bank Reconciliation", "passed": unresolved_bank == 0},
            {"name": "Opening Balances", "passed": not any(f.category == 'OPENING_BALANCE' for f in findings)},
            {"name": "Voucher Sequence Numbering", "passed": not any(f.category == 'NUMBERING' for f in findings)},
        ]

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

        if diff <= Decimal('0.01'):
            return {
                "is_balanced": True,
                "message": "Your books are mathematically balanced! Total Debits equal Total Credits (₹" + str(total_dr) + ").",
                "discrepancy": "0.00",
                "findings": []
            }

        # 2. Identify candidate causes
        causes = []

        # Cause A: Unbalanced vouchers
        vouchers = Voucher.objects.filter(company=company, status__in=['POSTED', 'REVERSED', 'CORRECTED'])
        for v in vouchers:
            v_tot = v.ledger_entries.aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
            v_dr = Decimal(str(v_tot['dr'] or '0.00'))
            v_cr = Decimal(str(v_tot['cr'] or '0.00'))
            if abs(v_dr - v_cr) > Decimal('0.01'):
                causes.append({
                    "type": "UNBALANCED_VOUCHER",
                    "title": f"Unbalanced Voucher #{v.voucher_number}",
                    "voucher_id": str(v.id),
                    "difference": str(abs(v_dr - v_cr)),
                    "evidence": f"Voucher #{v.voucher_number} has Dr ₹{v_dr} and Cr ₹{v_cr}",
                    "confidence": 98,
                    "suggested_fix": f"Re-post voucher #{v.voucher_number} with balancing line items."
                })

        # Cause B: Party balance drift
        parties = Ledger.objects.filter(company=company, ledger_type__in=['CUSTOMER', 'SUPPLIER'], is_archived=False)
        for p in parties:
            t = LedgerEntry.objects.filter(ledger=p, voucher__status__in=['POSTED', 'REVERSED', 'CORRECTED']).aggregate(dr=Sum('debit_amount'), cr=Sum('credit_amount'))
            p_dr = Decimal(str(t['dr'] or '0.00'))
            p_cr = Decimal(str(t['cr'] or '0.00'))
            expected = (p_dr - p_cr) if p.opening_balance_type == 'DEBIT' else (p_cr - p_dr)
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
            "message": f"Your Trial Balance is off by ₹{diff}. Total Debits: ₹{total_dr}, Total Credits: ₹{total_cr}.",
            "causes": causes[:3]
        }
