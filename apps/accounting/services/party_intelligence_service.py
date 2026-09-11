import re
import difflib
import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional
from apps.companies.models import Company
from apps.ledgers.models import Ledger
from apps.accounting.models import Voucher, PartyMapping
from apps.accounting.services.allocation_service import PaymentAllocationService

class PartyIntelligenceService:
    """
    Multi-signal party identification and confidence scoring engine.
    Integrates UPI IDs, bank accounts, GSTINs, phone numbers, exact/normalized names,
    learned company-specific mappings, and outstanding invoice amounts.
    """

    CLEANUP_SUFFIXES = [
        r'\bpvt\.?\s*ltd\.?\b', r'\bprivate\s+limited\b', r'\bltd\.?\b', r'\blimited\b',
        r'\btraders\b', r'\btrading\b', r'\benterprises\b', r'\bagencies\b',
        r'\bstores\b', r'\bcorporation\b', r'\bcorp\.?\b', r'\bco\.?\b', r'\b&\s*co\.?\b',
        r'\bllp\b', r'\binc\.?\b'
    ]

    @classmethod
    def normalize_entity_name(cls, name: str) -> str:
        """Removes legal suffixes and punctuation for flexible entity matching."""
        if not name:
            return ""
        s = name.upper().strip()
        for pat in cls.CLEANUP_SUFFIXES:
            s = re.sub(pat, '', s, flags=re.IGNORECASE)
        # Remove non-alphanumeric characters except spaces
        s = re.sub(r'[^A-Z0-9\s]', ' ', s)
        s = re.sub(r'\s+', ' ', s)
        return s.strip()

    @classmethod
    def extract_upi_id(cls, text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r'([a-zA-Z0-9._\-]+@[a-zA-Z0-9]+)', text)
        return match.group(1).upper() if match else None

    @classmethod
    def extract_gstin(cls, text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r'\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})\b', text.upper())
        return match.group(1) if match else None

    @classmethod
    def extract_phone(cls, text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r'\b([6-9]\d{9})\b', text)
        return match.group(1) if match else None

    @classmethod
    def extract_account_number(cls, text: str) -> Optional[str]:
        if not text:
            return None
        # Indian bank account numbers typically 9 to 18 digits
        match = re.search(r'\b(\d{9,18})\b', text)
        return match.group(1) if match else None

    @classmethod
    def match_transaction(
        cls,
        company: Company,
        narration: str,
        debit_amount: Decimal = Decimal('0.00'),
        credit_amount: Decimal = Decimal('0.00'),
        reference_number: Optional[str] = None,
        tx_date: Optional[datetime.date] = None
    ) -> Dict[str, Any]:
        """
        Evaluates 10 distinct signals in descending priority order to identify the associated party.
        Enforces strict company isolation.
        """
        from apps.accounting.services.allocation_service import PaymentAllocationService

        norm_narration = narration.upper().strip() if narration else ""
        amount = credit_amount if credit_amount > Decimal('0.00') else debit_amount
        has_credit_cues = bool(re.search(r'(^BY\b|\bBY\s+(?:CLG|CLEARING|TRF|TRANSFER|CASH|CHEQUE|CHQ|NEFT|RTGS|IMPS|UPI)|\bCR\b|\bDEPOSIT)', norm_narration))
        is_receipt = (credit_amount > Decimal('0.00')) or has_credit_cues
        target_role = 'CUSTOMER' if is_receipt else 'SUPPLIER'
        
        signals_triggered = []
        candidates: List[Dict[str, Any]] = []

        # 1. Historical confirmed PartyMapping (highest confidence, company-isolated)
        upi_id = cls.extract_upi_id(norm_narration)
        if upi_id:
            learned_upi = PartyMapping.objects.filter(
                company=company,
                mapping_type='UPI',
                normalized_pattern=upi_id
            ).select_related('party').first()
            if learned_upi:
                signals_triggered.append(f"Confirmed learned UPI mapping: {upi_id}")
                return {
                    "matched_party": learned_upi.party,
                    "matched_invoice": None,
                    "confidence": 1.0,
                    "signals": signals_triggered,
                    "suggested_matches": []
                }

        # Check narration keywords in PartyMapping
        learned_narration = PartyMapping.objects.filter(
            company=company,
            mapping_type='NARRATION'
        ).select_related('party')
        for l_map in learned_narration:
            if l_map.normalized_pattern in norm_narration:
                signals_triggered.append(f"Confirmed learned narration pattern: '{l_map.pattern}'")
                return {
                    "matched_party": l_map.party,
                    "matched_invoice": None,
                    "confidence": min(1.0, l_map.confidence),
                    "signals": signals_triggered,
                    "suggested_matches": []
                }

        # Check for Cash Deposit / Cash Invoices Settlement
        is_cash_deposit = bool(re.search(
            r'\b(CASH\s*DEP(?:OSIT)?|BY\s+CASH|CDM\s+CASH|CDM/|SELF\s+DEPOSIT|CASH\s+MACHINE|CASH\s+REC(?:EIPT)?)\b',
            norm_narration
        ))
        if is_cash_deposit and (credit_amount > Decimal('0.00') or has_credit_cues):
            cash_ledger = Ledger.objects.filter(
                company=company,
                ledger_type='CASH',
                is_archived=False
            ).first()
            if not cash_ledger:
                cash_ledger = Ledger.objects.filter(
                    company=company,
                    name__iexact='Cash',
                    is_archived=False
                ).first()
            if cash_ledger:
                signals_triggered.append("Detected Cash Deposit / Self Cash deposit into bank")
                from apps.accounting.services.allocation_service import PaymentAllocationService
                try:
                    unpaid_cash = PaymentAllocationService.get_unpaid_invoices_for_party(company, cash_ledger)
                    if unpaid_cash:
                        signals_triggered.append(f"Auto-settles against {len(unpaid_cash)} open cash sales invoices")
                except Exception:
                    pass

                return {
                    "matched_party": cash_ledger,
                    "matched_invoice": None,
                    "confidence": 0.98,
                    "signals": signals_triggered,
                    "suggested_matches": [],
                    "is_cash_deposit": True
                }

        # Fetch active party ledgers for the company
        parties = list(Ledger.objects.filter(
            company=company,
            ledger_type__in=['CUSTOMER', 'SUPPLIER', 'GENERAL'],
            is_archived=False
        ))

        gstin_in_text = cls.extract_gstin(norm_narration)
        phone_in_text = cls.extract_phone(norm_narration)
        acc_in_text = cls.extract_account_number(norm_narration)
        clearing_match = re.search(r'BY\s+CLG:[^,]+,\s*([^,]+?)(?:\s+Chq|\s*$)', norm_narration, re.IGNORECASE)
        clearing_entity = clearing_match.group(1).strip().upper() if clearing_match else ""

        # Iterate through parties and score
        for party in parties:
            p_name = party.name.upper()
            p_norm_name = cls.normalize_entity_name(p_name)
            p_gstin = (party.gstin or "").upper().strip()
            p_phone = (party.phone or "").strip()
            p_acc = (party.bank_account_number or "").strip()

            score = 0.0
            reasons = []

            # 2. UPI ID exact match against party's known upi
            if upi_id and hasattr(party, 'upi_id') and party.upi_id and upi_id == party.upi_id.upper():
                score = max(score, 0.98)
                reasons.append(f"Exact UPI handle match ({upi_id})")

            # 3. Bank Account / IFSC match
            if p_acc and acc_in_text and p_acc in norm_narration:
                score = max(score, 0.98)
                reasons.append(f"Bank account match ({p_acc})")

            # 4. GSTIN match
            if p_gstin and gstin_in_text and p_gstin == gstin_in_text:
                score = max(score, 0.97)
                reasons.append(f"GSTIN match ({p_gstin})")

            # 5. Exact Party Name in narration
            if len(p_name) >= 3 and (f" {p_name} " in f" {norm_narration} " or norm_narration.startswith(p_name)):
                score = max(score, 0.95)
                reasons.append(f"Exact party name '{party.name}' found in narration")

            # 6. Normalized Party Name match (stripped of PVT LTD, etc.)
            elif len(p_norm_name) >= 4 and p_norm_name in norm_narration:
                score = max(score, 0.90)
                reasons.append(f"Normalized entity name '{p_norm_name}' found in narration")

            # 6b. Inward Clearing Drawer match (e.g. BY CLG:DEL ACCTS-..., DRAWER Chq: ...)
            elif clearing_entity and len(clearing_entity) >= 3:
                if (clearing_entity in p_name or p_name.startswith(clearing_entity) or
                    clearing_entity in p_norm_name or p_norm_name.startswith(clearing_entity) or
                    difflib.SequenceMatcher(None, clearing_entity, p_norm_name.split()[0] if p_norm_name.split() else p_norm_name).ratio() >= 0.80):
                    score = max(score, 0.95)
                    reasons.append(f"Inward clearing drawer '{clearing_entity}' matched party '{party.name}'")

            # 6c. Primary token word match (e.g. KHAWAJA in 'Khawaja Eng. Works')
            if score < 0.90:
                p_tokens = [w for w in p_norm_name.split() if len(w) >= 4 and w not in ('ENTERPRISES', 'INDUSTRIES', 'TRADERS', 'COMPANY', 'CORP', 'LIMITED', 'WORKS', 'PRODUCTS', 'STORE', 'AGENCY')]
                for tok in p_tokens:
                    if re.search(r'\b' + re.escape(tok) + r'\b', norm_narration):
                        score = max(score, 0.90)
                        reasons.append(f"Entity keyword '{tok}' found in narration")
                        break
                    elif clearing_entity and (difflib.SequenceMatcher(None, clearing_entity, tok).ratio() >= 0.80 or tok.startswith(clearing_entity)):
                        score = max(score, 0.92)
                        reasons.append(f"Clearing token '{clearing_entity}' matched '{tok}' for '{party.name}'")
                        break

            # 7. Phone number match
            if p_phone and phone_in_text and p_phone == phone_in_text:
                score = max(score, 0.90)
                reasons.append(f"Phone number match ({p_phone})")

            # 8. Fuzzy name similarity across tokens
            if score < 0.75:
                for text_word in norm_narration.split():
                    if len(text_word) >= 4:
                        sim = difflib.SequenceMatcher(None, p_norm_name.split()[0] if p_norm_name.split() else p_norm_name, text_word).ratio()
                        if sim >= 0.80:
                            score = max(score, 0.80)
                            reasons.append(f"High token similarity ({text_word} ~ {party.name})")
                            break

            if score > 0.0:
                if party.ledger_type == target_role:
                    score = min(1.0, score + 0.05)
                candidates.append({
                    "party": party,
                    "score": score,
                    "reasons": reasons
                })

        # Check outstanding invoices/bills for amount matching
        best_party = None
        best_score = 0.0
        best_invoice = None

        if candidates:
            # Sort by candidate score
            candidates.sort(key=lambda x: x['score'], reverse=True)
            top_cand = candidates[0]
            best_party = top_cand['party']
            best_score = top_cand['score']
            signals_triggered.extend(top_cand['reasons'])

        # Check if amount matches an outstanding invoice of best party or any candidate
        if best_party and amount > Decimal('0.00'):
            unpaid_invoices = PaymentAllocationService.get_unpaid_invoices_for_party(company, best_party)
            for inv in unpaid_invoices:
                rem_amt = Decimal(inv['remaining_amount'])
                if rem_amt == amount:
                    best_score = min(1.0, best_score + 0.10)
                    signals_triggered.append(f"Exact outstanding invoice amount match (Invoice #{inv['voucher_number']}, ₹{amount})")
                    try:
                        best_invoice = Voucher.objects.get(id=inv['voucher_id'])
                    except Voucher.DoesNotExist:
                        pass
                    break

        # If no party found yet, attempt amount match across all parties with unpaid invoices
        if not best_party and amount > Decimal('0.00'):
            # Look for unpaid invoices across company with exact amount
            matching_invoices = Voucher.objects.filter(
                company=company,
                voucher_type='SALES' if is_receipt else 'PURCHASE',
                status='POSTED',
                total_amount=amount
            ).select_related('party_ledger')
            
            if matching_invoices.count() == 1:
                inv = matching_invoices.first()
                if inv.party_ledger:
                    best_party = inv.party_ledger
                    best_invoice = inv
                    best_score = 0.80  # Medium confidence
                    signals_triggered.append(f"Unique matching unpaid invoice #{inv.voucher_number} for ₹{amount}")
                    candidates.append({
                        "party": best_party,
                        "score": best_score,
                        "reasons": [f"Matching invoice #{inv.voucher_number}"]
                    })

        suggested_list = []
        for cand in candidates[:3]:
            p = cand['party']
            suggested_list.append({
                "party_id": str(p.id),
                "party_name": p.name,
                "confidence": round(cand['score'] * 100, 1),
                "outstanding": str(p.current_balance),
                "rationale": "; ".join(cand['reasons'])
            })

        return {
            "matched_party": best_party,
            "matched_invoice": best_invoice,
            "confidence": round(best_score, 2),
            "signals": signals_triggered,
            "suggested_matches": suggested_list
        }

    @classmethod
    def learn_mapping(
        cls,
        company: Company,
        pattern: str,
        party: Ledger,
        mapping_type: str = 'NARRATION',
        confirmed_by_user: bool = True
    ) -> PartyMapping:
        """
        Stores or updates confirmed party association for this company.
        Increments usage count and refreshes last_used timestamp.
        """
        norm_pattern = (cls.normalize_entity_name(pattern) if mapping_type == 'NARRATION' else pattern.upper().strip())[:255]
        
        mapping, created = PartyMapping.objects.get_or_create(
            company=company,
            normalized_pattern=norm_pattern,
            mapping_type=mapping_type,
            defaults={
                "pattern": pattern.strip()[:255],
                "party": party,
                "confirmed_by_user": confirmed_by_user,
                "confidence": 1.0,
                "usage_count": 1
            }
        )
        if not created:
            mapping.party = party
            mapping.usage_count += 1
            mapping.confirmed_by_user = confirmed_by_user
            mapping.confidence = 1.0
            mapping.save(update_fields=['party', 'usage_count', 'confirmed_by_user', 'confidence', 'last_used'])

        return mapping
