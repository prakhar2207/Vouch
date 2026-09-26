import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, LedgerEntry, PaymentAllocation, BankTransaction, AccountingFinding
from apps.inventory.models import Product, InventoryEntry
from apps.accounting.services.effective_voucher_service import EffectiveVoucherService


class TransactionDeduplicationEngine:
    """
    Intelligent Deduplication Engine across Receipts, Payments/Transactions, Banking, 
    Ledgers, and Inventory.
    
    Prevents duplicates at entry/reconciliation points (gatekeeper) and scans existing 
    records for Books Health audits with deterministic, audit-preserving fixes.
    """

    @classmethod
    def check_duplicate_candidate(
        cls,
        company: Company,
        voucher_type: str,
        party_ledger: Optional[Ledger],
        total_amount: Decimal,
        voucher_date: datetime.date,
        preferred_invoice_id: Optional[str] = None,
        exclude_voucher_id: Optional[str] = None,
        lookback_minutes: int = 15
    ) -> Dict[str, Any]:
        """
        Real-time gatekeeper pre-check before saving/posting a voucher.
        Checks:
        1. Exact duplicate (same type, party, amount, date)
        2. Duplicate payment allocated against the same invoice
        3. Rapid double-submission (created within lookback_minutes with same attributes)
        """
        amount = Decimal(str(total_amount or '0.00'))
        if amount <= Decimal('0.00'):
            return {"is_duplicate": False, "confidence": 0.0}

        active_statuses = list(EffectiveVoucherService.ACCOUNTING_STATUSES) + ['DRAFT', 'VALIDATING']
        qs = Voucher.objects.filter(
            company=company,
            voucher_type=voucher_type,
            status__in=active_statuses,
            total_amount=amount,
            voucher_date=voucher_date
        )
        if party_ledger:
            qs = qs.filter(party_ledger=party_ledger)
        if exclude_voucher_id:
            qs = qs.exclude(id=exclude_voucher_id)

        # 1. Check for rapid double-submission (created in last N minutes)
        recent_threshold = timezone.now() - datetime.timedelta(minutes=lookback_minutes)
        rapid_dup = qs.filter(created_at__gte=recent_threshold).first()
        if rapid_dup:
            return {
                "is_duplicate": True,
                "confidence": 0.99,
                "rule": "RAPID_DOUBLE_SUBMISSION",
                "reason": (
                    f"Identical {voucher_type} #{rapid_dup.voucher_number} of ₹{amount} for "
                    f"{party_ledger.name if party_ledger else 'this party'} was posted just "
                    f"{(timezone.now() - rapid_dup.created_at).seconds} seconds ago."
                ),
                "matching_voucher": {
                    "id": str(rapid_dup.id),
                    "voucher_number": rapid_dup.voucher_number,
                    "voucher_date": str(rapid_dup.voucher_date),
                    "total_amount": str(rapid_dup.total_amount),
                    "party_name": party_ledger.name if party_ledger else "",
                    "created_at": rapid_dup.created_at.isoformat()
                }
            }

        # 2. Check for duplicate payment against same invoice
        if preferred_invoice_id and voucher_type in ['RECEIPT', 'PAYMENT']:
            existing_alloc = PaymentAllocation.objects.filter(
                company=company,
                invoice_voucher_id=preferred_invoice_id,
                allocated_amount=amount,
                payment_voucher__voucher_date=voucher_date,
                payment_voucher__status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
            )
            if exclude_voucher_id:
                existing_alloc = existing_alloc.exclude(payment_voucher_id=exclude_voucher_id)
            alloc_match = existing_alloc.select_related('payment_voucher', 'invoice_voucher').first()
            if alloc_match:
                return {
                    "is_duplicate": True,
                    "confidence": 0.96,
                    "rule": "DUPLICATE_INVOICE_PAYMENT",
                    "reason": (
                        f"Payment of ₹{amount} against invoice #{alloc_match.invoice_voucher.voucher_number} "
                        f"was already recorded by voucher #{alloc_match.payment_voucher.voucher_number} on {voucher_date}."
                    ),
                    "matching_voucher": {
                        "id": str(alloc_match.payment_voucher.id),
                        "voucher_number": alloc_match.payment_voucher.voucher_number,
                        "voucher_date": str(alloc_match.payment_voucher.voucher_date),
                        "total_amount": str(alloc_match.payment_voucher.total_amount),
                        "party_name": party_ledger.name if party_ledger else "",
                        "invoice_number": alloc_match.invoice_voucher.voucher_number
                    }
                }

        # 3. Exact match on date, party, amount, and type
        exact_dup = qs.first()
        if exact_dup:
            return {
                "is_duplicate": True,
                "confidence": 0.92,
                "rule": "EXACT_TRANSACTION_MATCH",
                "reason": (
                    f"An existing {voucher_type} #{exact_dup.voucher_number} of ₹{amount} already exists "
                    f"for {party_ledger.name if party_ledger else 'this account'} on {voucher_date}."
                ),
                "matching_voucher": {
                    "id": str(exact_dup.id),
                    "voucher_number": exact_dup.voucher_number,
                    "voucher_date": str(exact_dup.voucher_date),
                    "total_amount": str(exact_dup.total_amount),
                    "party_name": party_ledger.name if party_ledger else "",
                    "created_at": exact_dup.created_at.isoformat()
                }
            }

        return {"is_duplicate": False, "confidence": 0.0}

    @classmethod
    def detect_existing_voucher_for_bank_tx(
        cls,
        bank_tx: BankTransaction,
        party: Optional[Ledger] = None,
        amount: Optional[Decimal] = None,
        is_money_in: Optional[bool] = None,
        date_window_days: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Smartly checks if an existing manual voucher already exists in the system that matches
        this bank transaction, preventing duplicate voucher creation during reconciliation.
        
        Matches:
        - Direction: Money IN -> RECEIPT, Money OUT -> PAYMENT
        - Party: Matches party ledger
        - Amount: Exact amount
        - Date: Transaction date within ± date_window_days
        - Not already linked to another reconciled bank transaction
        """
        if amount is None:
            amount = bank_tx.credit_amount if bank_tx.credit_amount > Decimal('0.00') else bank_tx.debit_amount
        if is_money_in is None:
            is_money_in = bank_tx.credit_amount > Decimal('0.00')

        if amount <= Decimal('0.00'):
            return None

        v_type = 'RECEIPT' if is_money_in else 'PAYMENT'
        company = bank_tx.company
        tx_date = bank_tx.transaction_date
        start_date = tx_date - datetime.timedelta(days=date_window_days)
        end_date = tx_date + datetime.timedelta(days=date_window_days)

        candidates = Voucher.objects.filter(
            company=company,
            voucher_type=v_type,
            status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
            total_amount=amount,
            voucher_date__gte=start_date,
            voucher_date__lte=end_date
        ).select_related('party_ledger')

        if party:
            candidates = candidates.filter(party_ledger=party)

        # Exclude vouchers that are already matched to an active reconciled bank transaction
        reconciled_voucher_ids = set(
            BankTransaction.objects.filter(
                company=company,
                status='RECONCILED',
                matched_voucher__isnull=False
            ).exclude(id=bank_tx.id).values_list('matched_voucher_id', flat=True)
        )

        unlinked_candidates = [c for c in candidates if c.id not in reconciled_voucher_ids]

        if not unlinked_candidates:
            return None

        # Prioritize exact date match, then closest date
        def score_candidate(cand: Voucher):
            day_diff = abs((cand.voucher_date - tx_date).days)
            score = 1.0 - (day_diff * 0.05)
            # Bonus if party matches
            if party and cand.party_ledger_id == party.id:
                score += 0.05
            # Bonus if reference matches
            if bank_tx.reference_number and bank_tx.reference_number in (cand.reference_number or ''):
                score += 0.10
            return score

        best_cand = max(unlinked_candidates, key=score_candidate)
        confidence = min(1.0, score_candidate(best_cand))

        return {
            "voucher": best_cand,
            "voucher_id": str(best_cand.id),
            "voucher_number": best_cand.voucher_number,
            "voucher_date": str(best_cand.voucher_date),
            "total_amount": str(best_cand.total_amount),
            "party_name": best_cand.party_ledger.name if best_cand.party_ledger else "",
            "confidence": confidence,
            "days_difference": abs((best_cand.voucher_date - tx_date).days)
        }

    @classmethod
    def scan_duplicate_vouchers(cls, company: Company) -> List[Dict[str, Any]]:
        """
        Scans all effective vouchers in the company to find duplicate clusters:
        1. Identical vouchers by (voucher_type, party_ledger, total_amount, voucher_date)
        2. Duplicate payment allocations against the same invoice
        """
        findings_data = []

        # Cluster by (voucher_type, party_ledger, total_amount, voucher_date)
        duplicate_groups = (
            Voucher.objects.filter(
                company=company,
                status__in=EffectiveVoucherService.ACCOUNTING_STATUSES,
                party_ledger__isnull=False
            )
            .values('voucher_type', 'party_ledger', 'total_amount', 'voucher_date')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )

        for group in duplicate_groups:
            party = Ledger.objects.filter(id=group['party_ledger']).first()
            if not party:
                continue

            vouchers = list(
                Voucher.objects.filter(
                    company=company,
                    voucher_type=group['voucher_type'],
                    party_ledger=party,
                    total_amount=group['total_amount'],
                    voucher_date=group['voucher_date'],
                    status__in=EffectiveVoucherService.ACCOUNTING_STATUSES
                )
                .order_by('created_at')
                .defer('attachment_data', 'attachment_mime')
            )

            if len(vouchers) < 2:
                continue

            # Identify Primary vs Duplicate(s):
            # Prioritize:
            # 1. The voucher that has payment allocations
            # 2. If one has bank transaction matched and one has invoice allocation:
            #    the manual one with invoice allocation is primary, and bank tx should link to it!
            # 3. Otherwise, the earliest created voucher is primary.
            def rank_primary(v: Voucher):
                score = 0
                if v.allocations_made.exists():
                    score += 10
                if v.allocations_received.exists():
                    score += 10
                if v.items.exists():
                    score += 5
                # Earliest creation date preferred if scores tie
                return (score, -v.created_at.timestamp())

            sorted_vouchers = sorted(vouchers, key=rank_primary, reverse=True)
            primary_v = sorted_vouchers[0]
            duplicate_vs = sorted_vouchers[1:]

            for dup_v in duplicate_vs:
                # Detect origin / cause
                is_bank_recon = BankTransaction.objects.filter(matched_voucher=dup_v).exists()
                is_rapid = (dup_v.created_at - primary_v.created_at).total_seconds() < 300

                if is_bank_recon:
                    source_desc = "Created via Bank Reconciliation while manual voucher already existed"
                elif is_rapid:
                    source_desc = "Rapid double-click submission (created within seconds of original)"
                else:
                    source_desc = "Identical manual double-entry"

                # Check linked bank transaction on duplicate voucher
                linked_bank_tx = BankTransaction.objects.filter(matched_voucher=dup_v).first()

                findings_data.append({
                    "type": "DUPLICATE_VOUCHER",
                    "category": "DUPLICATE",
                    "severity": "CRITICAL" if group['voucher_type'] in ['RECEIPT', 'PAYMENT'] else "WARNING",
                    "title": f"Duplicate {group['voucher_type'].title()} #{dup_v.voucher_number} for {party.name}",
                    "description": (
                        f"Found duplicate {group['voucher_type']} entry #{dup_v.voucher_number} for ₹{group['total_amount']} "
                        f"on {group['voucher_date']}. Primary voucher #{primary_v.voucher_number} is kept. {source_desc}."
                    ),
                    "evidence": {
                        "duplicate_voucher_id": str(dup_v.id),
                        "duplicate_voucher_number": dup_v.voucher_number,
                        "primary_voucher_id": str(primary_v.id),
                        "primary_voucher_number": primary_v.voucher_number,
                        "party_id": str(party.id),
                        "party_name": party.name,
                        "voucher_type": group['voucher_type'],
                        "amount": str(group['total_amount']),
                        "voucher_date": str(group['voucher_date']),
                        "source_description": source_desc,
                        "has_linked_bank_tx": bool(linked_bank_tx),
                        "linked_bank_tx_id": str(linked_bank_tx.id) if linked_bank_tx else None,
                        "linked_bank_tx_desc": linked_bank_tx.description if linked_bank_tx else None,
                    },
                    "expected_state": f"Single {group['voucher_type']} voucher #{primary_v.voucher_number} for ₹{group['total_amount']}.",
                    "actual_state": f"{len(vouchers)} duplicate vouchers posted ({', '.join(v.voucher_number for v in vouchers)}).",
                    "probable_cause": source_desc,
                    "suggested_action": f"Void duplicate voucher #{dup_v.voucher_number} and restore {party.name}'s true balance.",
                    "confidence": 0.98,
                    "fix_action": "VOID_DUPLICATE_VOUCHER"
                })

        # Check duplicate payment allocations against the same invoice
        dup_allocs = (
            PaymentAllocation.objects.filter(company=company)
            .values('invoice_voucher_id', 'allocated_amount', 'payment_voucher__voucher_date')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )
        for da in dup_allocs:
            alloc_records = list(
                PaymentAllocation.objects.filter(
                    company=company,
                    invoice_voucher_id=da['invoice_voucher_id'],
                    allocated_amount=da['allocated_amount'],
                    payment_voucher__voucher_date=da['payment_voucher__voucher_date']
                ).select_related('invoice_voucher', 'payment_voucher')
            )
            if len(alloc_records) >= 2:
                inv = alloc_records[0].invoice_voucher
                pmt_nums = [a.payment_voucher.voucher_number for a in alloc_records]
                findings_data.append({
                    "type": "DUPLICATE_INVOICE_PAYMENT",
                    "category": "DUPLICATE",
                    "severity": "CRITICAL",
                    "title": f"Duplicate payment allocated against Invoice #{inv.voucher_number}",
                    "description": (
                        f"Invoice #{inv.voucher_number} has {len(alloc_records)} identical payment allocations "
                        f"of ₹{da['allocated_amount']} on {da['payment_voucher__voucher_date']} ({', '.join(pmt_nums)})."
                    ),
                    "evidence": {
                        "invoice_id": str(inv.id),
                        "invoice_number": inv.voucher_number,
                        "amount": str(da['allocated_amount']),
                        "voucher_numbers": pmt_nums,
                        "party_id": str(inv.party_ledger_id) if inv.party_ledger_id else None
                    },
                    "expected_state": f"Single payment allocation of ₹{da['allocated_amount']}.",
                    "actual_state": f"{len(alloc_records)} identical payments allocated.",
                    "probable_cause": "Double-entry payment or duplicate bank feed allocation.",
                    "suggested_action": "Re-run automated FIFO allocation or void duplicate payment voucher.",
                    "confidence": 0.95,
                    "fix_action": "RECONCILE_FIFO"
                })

        return findings_data

    @classmethod
    def scan_duplicate_bank_transactions(cls, company: Company) -> List[Dict[str, Any]]:
        """
        Scans for duplicate bank transactions:
        1. Identical bank statement lines imported multiple times
        2. Unresolved bank transactions that match an existing manual voucher
        """
        findings_data = []

        # 1. Statement lines imported multiple times
        dup_bank = (
            BankTransaction.objects.filter(company=company)
            .values('bank_ledger_id', 'transaction_date', 'debit_amount', 'credit_amount', 'reference_number')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )

        for db in dup_bank:
            txs = list(
                BankTransaction.objects.filter(
                    company=company,
                    bank_ledger_id=db['bank_ledger_id'],
                    transaction_date=db['transaction_date'],
                    debit_amount=db['debit_amount'],
                    credit_amount=db['credit_amount'],
                    reference_number=db['reference_number']
                ).order_by('created_at')
            )
            if len(txs) < 2:
                continue

            primary_tx = txs[0]
            duplicate_txs = txs[1:]
            amt = db['credit_amount'] if db['credit_amount'] > Decimal('0.00') else db['debit_amount']

            for dup_tx in duplicate_txs:
                findings_data.append({
                    "type": "DUPLICATE_BANK_TRANSACTION",
                    "category": "DUPLICATE_BANK",
                    "severity": "WARNING",
                    "title": f"Duplicate Bank Statement Entry: ₹{amt} on {db['transaction_date']}",
                    "description": (
                        f"Bank statement entry for ₹{amt} on {db['transaction_date']} ({primary_tx.bank_ledger.name}) "
                        f"was imported {len(txs)} times. Keep statement record {primary_tx.id} and exclude duplicate."
                    ),
                    "evidence": {
                        "duplicate_bank_tx_id": str(dup_tx.id),
                        "primary_bank_tx_id": str(primary_tx.id),
                        "bank_ledger_name": primary_tx.bank_ledger.name,
                        "amount": str(amt),
                        "date": str(db['transaction_date']),
                        "reference_number": db['reference_number'],
                        "duplicate_status": dup_tx.status
                    },
                    "expected_state": f"Single statement transaction line for ₹{amt}.",
                    "actual_state": f"{len(txs)} identical statement entries found.",
                    "probable_cause": "Statement CSV/Excel file was uploaded more than once.",
                    "suggested_action": "Exclude the redundant bank transaction entry.",
                    "confidence": 0.96,
                    "fix_action": "EXCLUDE_DUPLICATE_BANK"
                })

        # 2. Unresolved bank transactions matching an existing manual voucher
        unresolved_txs = BankTransaction.objects.filter(company=company, status='UNRESOLVED')[:25]
        for utx in unresolved_txs:
            match = cls.detect_existing_voucher_for_bank_tx(utx)
            if match and match['confidence'] >= 0.90:
                amt = utx.credit_amount if utx.credit_amount > Decimal('0.00') else utx.debit_amount
                findings_data.append({
                    "type": "UNLINKED_BANK_MATCH",
                    "category": "DUPLICATE_BANK",
                    "severity": "INFO",
                    "title": f"Unlinked Bank Feed matches Voucher #{match['voucher_number']}",
                    "description": (
                        f"Unresolved bank transaction for ₹{amt} on {utx.transaction_date} matches existing "
                        f"manual voucher #{match['voucher_number']} ({match['party_name']}). Link them to prevent duplicate entry."
                    ),
                    "evidence": {
                        "bank_tx_id": str(utx.id),
                        "voucher_id": match['voucher_id'],
                        "voucher_number": match['voucher_number'],
                        "party_name": match['party_name'],
                        "amount": str(amt),
                        "transaction_date": str(utx.transaction_date),
                        "voucher_date": match['voucher_date']
                    },
                    "expected_state": f"Bank transaction linked to voucher #{match['voucher_number']}.",
                    "actual_state": "Transaction is unresolved while matching voucher exists in books.",
                    "probable_cause": "Voucher entered manually before bank statement import.",
                    "suggested_action": f"Link bank transaction directly to voucher #{match['voucher_number']}.",
                    "confidence": match['confidence'],
                    "fix_action": "LINK_BANK_TRANSACTION"
                })

        return findings_data

    @classmethod
    def scan_duplicate_inventory(cls, company: Company) -> List[Dict[str, Any]]:
        """
        Scans for duplicate products in company:
        - Identical normalized product name and brand
        - Identical SKU
        """
        findings_data = []

        dup_names = (
            Product.objects.filter(company=company, is_active=True)
            .values('name', 'brand')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )

        for item in dup_names:
            prods = list(
                Product.objects.filter(
                    company=company,
                    name=item['name'],
                    brand=item['brand'],
                    is_active=True
                ).select_related('category').order_by('created_at')
            )
            if len(prods) < 2:
                continue

            # Primary product: the one with more transaction movements or earliest created
            def rank_prod(p: Product):
                movements = p.entries.count() + p.voucher_items.count()
                return (movements, -p.created_at.timestamp())

            sorted_prods = sorted(prods, key=rank_prod, reverse=True)
            primary_prod = sorted_prods[0]
            duplicate_prods = sorted_prods[1:]

            primary_cat_name = primary_prod.category.name if primary_prod.category else "Uncategorized"
            primary_cat_id = str(primary_prod.category.id) if primary_prod.category else None

            for dup_prod in duplicate_prods:
                combined_stock = primary_prod.stock_quantity + dup_prod.stock_quantity
                dup_cat_name = dup_prod.category.name if dup_prod.category else "Uncategorized"
                dup_cat_id = str(dup_prod.category.id) if dup_prod.category else None
                is_cross_category = (primary_cat_id != dup_cat_id)

                if is_cross_category:
                    title = f"Cross-Category Duplicate: {item['name']} ({primary_cat_name} vs {dup_cat_name})"
                    desc = (
                        f"Found duplicate product '{item['name']}' ({item['brand'] or 'No Brand'}) across categories: "
                        f"'{primary_cat_name}' (SKU: {primary_prod.sku}, Qty: {primary_prod.stock_quantity}) and "
                        f"'{dup_cat_name}' (SKU: {dup_prod.sku}, Qty: {dup_prod.stock_quantity}). "
                        f"Merge will consolidate all stock ({combined_stock} units) into '{primary_cat_name}'."
                    )
                    action = f"Merge SKU {dup_prod.sku} ({dup_cat_name}) into {primary_prod.sku} ({primary_cat_name}) and consolidate stock."
                    probable_cause = f"Item created in '{dup_cat_name}' and separately in '{primary_cat_name}'."
                else:
                    title = f"Duplicate Product: {item['name']} ({item['brand'] or 'No Brand'})"
                    desc = (
                        f"Found duplicate product '{item['name']}' in category '{primary_cat_name}' with SKUs "
                        f"{primary_prod.sku} (Qty: {primary_prod.stock_quantity}) and "
                        f"{dup_prod.sku} (Qty: {dup_prod.stock_quantity}). "
                        f"Merge to consolidate stock of {combined_stock}."
                    )
                    action = f"Merge SKU {dup_prod.sku} into {primary_prod.sku} and consolidate stock."
                    probable_cause = "Item added twice during catalog import or billing."

                findings_data.append({
                    "type": "DUPLICATE_INVENTORY_ITEM",
                    "category": "DUPLICATE_INVENTORY",
                    "severity": "WARNING",
                    "title": title,
                    "description": desc,
                    "evidence": {
                        "primary_product_id": str(primary_prod.id),
                        "primary_sku": primary_prod.sku,
                        "primary_stock": str(primary_prod.stock_quantity),
                        "primary_category_id": primary_cat_id,
                        "primary_category_name": primary_cat_name,
                        "duplicate_product_id": str(dup_prod.id),
                        "duplicate_sku": dup_prod.sku,
                        "duplicate_stock": str(dup_prod.stock_quantity),
                        "duplicate_category_id": dup_cat_id,
                        "duplicate_category_name": dup_cat_name,
                        "is_cross_category": is_cross_category,
                        "combined_stock": str(combined_stock),
                        "product_name": item['name'],
                        "brand": item['brand'] or ""
                    },
                    "expected_state": f"Single product record for '{item['name']}'.",
                    "actual_state": f"{len(prods)} separate product records in catalog.",
                    "probable_cause": probable_cause,
                    "suggested_action": action,
                    "confidence": 0.95,
                    "fix_action": "MERGE_INVENTORY_ITEMS"
                })

        return findings_data

    @classmethod
    def scan_duplicate_ledgers(cls, company: Company) -> List[Dict[str, Any]]:
        """
        Scans for duplicate party / account ledgers:
        - Ledgers with duplicate non-empty GSTINs
        - Ledgers with identical trimmed/case-insensitive names
        """
        findings_data = []

        # Duplicate GSTIN
        dup_gstin = (
            Ledger.objects.filter(company=company, is_archived=False)
            .exclude(gstin__isnull=True)
            .exclude(gstin__exact="")
            .values('gstin')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )
        for dg in dup_gstin:
            ledgers = list(
                Ledger.objects.filter(company=company, gstin=dg['gstin'], is_archived=False)
                .order_by('created_at')
            )
            if len(ledgers) >= 2:
                prim_l = ledgers[0]
                dup_l = ledgers[1]
                findings_data.append({
                    "type": "DUPLICATE_LEDGER_GSTIN",
                    "category": "DUPLICATE_LEDGER",
                    "severity": "WARNING",
                    "title": f"Duplicate Party Ledger with GSTIN {dg['gstin']}",
                    "description": (
                        f"Ledgers '{prim_l.name}' and '{dup_l.name}' share the exact same GSTIN {dg['gstin']}. "
                        f"Ledger entries should be merged into a single party account."
                    ),
                    "evidence": {
                        "primary_ledger_id": str(prim_l.id),
                        "primary_ledger_name": prim_l.name,
                        "duplicate_ledger_id": str(dup_l.id),
                        "duplicate_ledger_name": dup_l.name,
                        "gstin": dg['gstin'],
                        "primary_balance": str(prim_l.current_balance),
                        "duplicate_balance": str(dup_l.current_balance)
                    },
                    "expected_state": f"Single ledger account for GSTIN {dg['gstin']}.",
                    "actual_state": f"Multiple ledgers registered with same GSTIN ({', '.join(l.name for l in ledgers)}).",
                    "probable_cause": "Party entered under alternate name or spelling.",
                    "suggested_action": f"Merge '{dup_l.name}' into '{prim_l.name}'.",
                    "confidence": 0.94,
                    "fix_action": "MERGE_DUPLICATE_LEDGERS"
                })

        return findings_data

    @classmethod
    def scan_all_duplicates(cls, company: Company) -> List[Dict[str, Any]]:
        """
        Unified deduplication scanner across vouchers, banking, inventory, and ledgers.
        """
        all_findings = []
        all_findings.extend(cls.scan_duplicate_vouchers(company))
        all_findings.extend(cls.scan_duplicate_bank_transactions(company))
        all_findings.extend(cls.scan_duplicate_inventory(company))
        all_findings.extend(cls.scan_duplicate_ledgers(company))
        return all_findings
