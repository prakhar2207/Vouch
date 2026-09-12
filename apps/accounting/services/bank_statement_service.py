import io
import re
import csv
import uuid
import datetime
import hashlib
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from pydantic import BaseModel, Field
from apps.accounting.models import BankStatementImport, BankTransaction
from apps.companies.models import Company
from apps.ledgers.models import Ledger


class BankTransactionSchema(BaseModel):
    date: str = Field(description="Transaction date in YYYY-MM-DD format")
    value_date: Optional[str] = Field(default="", description="Value date in YYYY-MM-DD format if present")
    description: str = Field(description="Complete cleaned narration or particulars of the transaction")
    reference: Optional[str] = Field(default="", description="Cheque number, UTR, or bank reference number")
    debit: float = Field(default=0.0, description="Withdrawal / debit / money out amount as positive number (0.0 if deposit). Narration starting with 'TO' or listed under Withdrawals/Dr column.")
    credit: float = Field(default=0.0, description="Deposit / credit / money in amount as positive number (0.0 if withdrawal). Narration starting with 'BY' or listed under Deposits/Cr column.")
    balance: Optional[float] = Field(default=None, description="Closing balance after transaction")


class BankStatementExtractionSchema(BaseModel):
    opening_balance: Optional[float] = Field(default=None, description="Opening balance if stated")
    closing_balance: Optional[float] = Field(default=None, description="Closing balance if stated")
    transactions: List[BankTransactionSchema] = Field(default_factory=list, description="Extracted bank transactions")


class BankStatementService:
    """
    Forensic-grade multi-format bank statement parser & normalizer.
    Supports CSV, Excel (XLSX/XLS), Native PDF, Scanned PDF, and Images (PNG/JPG).
    
    Architectural Invariants:
    1. Deterministic parser where reliable + OCR where necessary + AI vision fallback.
    2. Mandatory balance chain validation: opening + sum(credits) - sum(debits) == closing.
    3. Multi-line narration stitching preserving references, UPI IDs, and GSTINs.
    4. Deterministic transaction fingerprinting (SHA-256) & file hash deduplication.
    5. Amount and date OCR confusion safety.
    """

    BOILERPLATE_REGEX = re.compile(
        r'('
        r'\bpage\s+\d+(\s+of\s+\d+)?\b|'
        r'\bclosing\s+balance\b|\bopening\s+balance\b|\bbrought\s+forward\b|\bcarried\s+forward\b|\bb\/f\b|\bc\/f\b|'
        r'\bend\s+of\s+statement\b|\bstatement\s+summary\b|\bstatement\s+of\s+account\b|'
        r'\bdisclaimer\b|\bunless\s+the\s+constituent\b|\bif\s+any\s+discrepancy\s+found\b|'
        r'\bconstituent\b|\bdetails\s+of\s+(?:banking\s+)?ombudsman\b|\bbanking\s+ombudsman\b|\bombudsman\b|'
        r'\bdo\s+not\s+share\s+atm\b|\bnever\s+share\s+(?:your\s+)?(?:otp|cvv|pin|password)\b|'
        r'\bcode\s+or\s+could\s+be\s+an\s+attempt\b|\balways\s+login\s+through\b|'
        r'\bplease\s*beware\b|\bbeware\s+of\b|\bfake\s+website\b|'
        r'\bphishing\b|\bvishing\b|\bsmishing\b|\bphish\b|\bsteal\s+your\s+personal\b|'
        r'\bchange\s+in\s+(?:the\s+)?address\b|\bare\s+you\s+a\s+merchant\b|\buse\s+digital\s+payment\b|'
        r'\bimb\s+users\b|\bcyber\s+crime\b|\btoll\s+free\b|\bcustomer\s+care\b|\bhelpline\b|\bcontact\s+branch\b|'
        r'\bcomputer\s+(?:generated|output)\b|\bdoes\s+not\s+require\s+(?:any\s+)?signature\b|'
        r'\bdate\s+particulars\b|\baccount\s+balance\s+as\s+on\b|\bcurrent\s+balance\b|'
        r'\btotal\s+withdrawals\b|\btotal\s+deposits\b'
        r')',
        re.IGNORECASE
    )

    IS_CREDIT_REGEX = re.compile(
        r'(^BY\b|'
        r'\bBY\s+(?:CLG|CLEARING|TRANSFER|TRF|CASH|CHEQUE|CHQ|NEFT|RTGS|IMPS|UPI|DEP|DEPOSIT)\b|'
        r'\b(?:CR|DEPOSIT|DEPOSITS)\b|'
        r'\b(?:NEFT\s+CR|RTGS\s+CR|IMPS\s+CR|UPI\/CR|\/CR\/|CR\-)\b|'
        r'\b(?:CASH\s+DEPOSIT|SALARY|DIVIDEND|REFUND|INTEREST\s+CREDIT)\b)',
        re.IGNORECASE
    )

    IS_DEBIT_REGEX = re.compile(
        r'(^TO\b|'
        r'\bTO\s+(?:CLG|CLEARING|TRANSFER|TRF|CASH|CHEQUE|CHQ|NEFT|RTGS|IMPS|UPI)\b|'
        r'\b(?:DR|WITHDRAWAL|WITHDRAWALS)\b|'
        r'\b(?:NEFT\s+DR|RTGS\s+DR|IMPS\s+DR|UPI\/DR|\/DR\/|DR\-)\b|'
        r'\b(?:TRANSFER\s+TO|TO\s+TRANSFER|PAID\s+TO|PAYMENT\s+TO)\b|'
        r'\b(?:CASA\s+DEBIT|DEBIT\s+INTEREST|SERVICE\s+CHARGE|CHG|CHARGES|\bSC\b|COMMISSION|TAX|TDS|GST|SMS\s+CHARGES)\b)',
        re.IGNORECASE
    )

    DATE_PATTERNS = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y-%m-%d", "%Y/%m/%d",
        "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %b %y",
        "%d-%B-%Y", "%d %B %Y"
    ]

    @classmethod
    def clean_amount_str(cls, val: Any) -> Decimal:
        """
        Deterministic amount normalizer with OCR error safety.
        Cleans currency symbols, handles OCR digit confusions (O/o->0, l/I->1, B->8, S->5),
        Indian numbering formats, and negative signs.
        """
        if val is None:
            return Decimal('0.00')
        s = str(val).strip()
        if not s or s.lower() in ['nan', 'none', '-', '', 'null', 'nil', '.']:
            return Decimal('0.00')

        # Strip currency symbols and whitespace
        s = re.sub(r'[₹$€£\s]', '', s)

        # Handle negative brackets e.g. (1,250.00)
        is_negative = False
        if s.startswith('(') and s.endswith(')'):
            is_negative = True
            s = s[1:-1].strip()

        # Handle trailing/leading DR/CR
        s = re.sub(r'(?i)\bdr\b', '', s).strip()
        s = re.sub(r'(?i)\bcr\b', '', s).strip()

        # Check if digits are corrupted by common OCR letter substitutions
        if re.search(r'\d', s):
            s = re.sub(r'(?<=[0-9,.])[Oo](?=[0-9,.])|^[Oo](?=[0-9,.])|(?<=[0-9,.])[Oo]$', '0', s)
            s = re.sub(r'(?<=[0-9,.])[lI](?=[0-9,.])|^[lI](?=[0-9,.])|(?<=[0-9,.])[lI]$', '1', s)
            s = re.sub(r'(?<=[0-9,.])[B](?=[0-9,.])|^[B](?=[0-9,.])|(?<=[0-9,.])[B]$', '8', s)
            s = re.sub(r'(?<=[0-9,.])[Ss](?=[0-9,.])|^[Ss](?=[0-9,.])|(?<=[0-9,.])[Ss]$', '5', s)

        # Remove commas
        s = s.replace(',', '')

        try:
            val_dec = Decimal(s)
            return abs(val_dec)
        except Exception:
            return Decimal('0.00')

    @classmethod
    def parse_date_str(cls, val: Any, preferred_format: Optional[str] = None) -> Optional[datetime.date]:
        """
        Parses date string with boundary and calendar validity checks.
        Rejects impossible dates (month > 12, day > 31, leap year mismatches).
        """
        if not val:
            return None
        if isinstance(val, (datetime.date, datetime.datetime)):
            return val.date() if isinstance(val, datetime.datetime) else val
        s = str(val).strip()
        s = s.split(' ')[0].split('T')[0]

        patterns = [preferred_format] if preferred_format else []
        patterns += [p for p in cls.DATE_PATTERNS if p != preferred_format]

        for pattern in patterns:
            try:
                dt = datetime.datetime.strptime(s, pattern).date()
                if 1990 <= dt.year <= 2050:
                    return dt
            except (ValueError, TypeError):
                continue
        return None

    @classmethod
    def detect_batch_date_format(cls, date_strings: List[str]) -> str:
        """
        Disambiguates DD/MM/YYYY vs MM/DD/YYYY across the batch.
        If any date has the first component > 12 (e.g. 25/01/2026),
        the entire statement is unequivocally DD/MM/YYYY.
        """
        has_day_over_12 = False
        has_month_over_12 = False

        for raw in date_strings:
            m = re.match(r'^(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})', str(raw).strip())
            if m:
                c1 = int(m.group(1))
                c2 = int(m.group(2))
                if c1 > 12:
                    has_day_over_12 = True
                if c2 > 12:
                    has_month_over_12 = True

        if has_day_over_12:
            return "%d/%m/%Y"
        elif has_month_over_12:
            return "%m/%d/%Y"
        return "%d/%m/%Y"

    @classmethod
    def clean_boilerplate_from_narration(cls, text: str) -> str:
        """Strips guidelines, disclaimers, phishing warnings, and balance footers from narration."""
        if not text:
            return ""
        m = cls.BOILERPLATE_REGEX.search(text)
        if m:
            clean_part = text[:m.start()].strip()
            clean_part = re.sub(r'[\s\-\:\.\,\/\\\|]+$', '', clean_part).strip()
            return clean_part
        return text.strip()

    @classmethod
    def is_boilerplate_line(cls, text: str) -> bool:
        """Determines if a line is purely a disclaimer, guideline, footer, or balance line."""
        if not text:
            return True
        t_clean = text.strip()
        if cls.BOILERPLATE_REGEX.search(t_clean):
            cleaned = cls.BOILERPLATE_REGEX.sub("", t_clean)
            residual = re.sub(r'[\d\s\-\:\.\,\/\\\|\(\)\"\']+', '', cleaned)
            if len(residual) < 4:
                return True
            lower_t = t_clean.lower()
            if any(lower_t.startswith(prefix) for prefix in [
                'disclaimer', 'page ', '- page', 'details of', 'ombudsman',
                'closing balance', 'opening balance', 'brought forward',
                'carried forward', 'code or could', 'always login',
                'do not share', 'please beware', 'change in the address',
                'are you a merchant', 'imb users', 'end of statement'
            ]):
                return True
        return False

    @classmethod
    def normalize_narration(cls, text: str, max_length: int = 500) -> str:
        """
        Cleans bank narration, normalizes whitespace, strips boilerplate guidelines, and standardizes
        beneficiary identifiers for accurate matching. Safely truncates to max_length (default 500).
        """
        if not text:
            return ""
        s = cls.clean_boilerplate_from_narration(str(text))
        s = re.sub(r'\s+', ' ', s)
        res = s.strip()
        if max_length and len(res) > max_length:
            return res[:max_length]
        return res

    @classmethod
    def extract_upi_id(cls, text: str) -> Optional[str]:
        """Extracts UPI VPA handle from narration if present (e.g. 'UPI/rajesh@okhdfcbank/...')"""
        if not text:
            return None
        match = re.search(r'([a-zA-Z0-9._\-]+@[a-zA-Z0-9]+)', text)
        if match:
            return match.group(1).upper()
        return None

    @classmethod
    def extract_reference_number(cls, text: str, ref_col_val: Optional[str] = None) -> Optional[str]:
        """Extracts Cheque number, UTR, or transaction reference from dedicated column or narration."""
        blacklist = {
            'CLOSING', 'BALANCE', 'STATEMENT', 'DISCLAIMER', 'PAGE', 'TOTAL',
            'OPENING', 'CANARA', 'CUSTOMER', 'CHEQUE', 'ACCOUNT', 'PARTICULARS',
            'AMOUNT', 'DEPOSIT', 'WITHDRAWAL', 'CREDIT', 'DEBIT', 'SUMMARY', 'BRANCH'
        }
        if ref_col_val and str(ref_col_val).strip() and str(ref_col_val).strip().lower() not in ['nan', 'none', '-', '']:
            cand = str(ref_col_val).strip()[:100]
            if cand.upper() not in blacklist and not re.match(r'^(?:0+|nan|none|-+)$', cand, re.IGNORECASE):
                return cand
        if not text:
            return None
        utr_match = re.search(r'(?:UTR|REF|NO|CHQ|NEFT|RTGS|IMPS)[/:\s\-]+([A-Za-z0-9]{6,22})', text, re.IGNORECASE)
        if utr_match:
            val = utr_match.group(1).upper()[:100]
            if val not in blacklist:
                return val
        rrn_match = re.search(r'\b(\d{12})\b', text)
        if rrn_match:
            val = rrn_match.group(1)[:100]
            if val not in blacklist:
                return val
        return None

    @classmethod
    def compute_transaction_fingerprint(
        cls,
        company_id: Any,
        bank_ledger_id: Any,
        tx_date: Any,
        debit: Decimal,
        credit: Decimal,
        identifier: str
    ) -> str:
        """
        Deterministic SHA-256 fingerprint ensuring strict bank transaction idempotency.
        """
        raw_key = f"{company_id}:{bank_ledger_id}:{tx_date}:{debit:.2f}:{credit:.2f}:{(identifier or '').strip().upper()}"
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    @classmethod
    def detect_columns(cls, header_row: List[str]) -> Dict[str, int]:
        """
        Identifies column indices for Date, Value Date, Description, Reference,
        Debit, Credit, Amount, Balance, and Type based on Indian bank formats
        (SBI, HDFC, ICICI, Axis, Kotak, PNB, etc.).
        """
        mapping = {}
        cleaned = [str(col).strip().lower() for col in header_row if col is not None]

        date_aliases = ['txn date', 'transaction date', 'trans date', 'date', 'posting date', 'value dt', 'txndate', 'tran date']
        val_date_aliases = ['value date', 'val date', 'value dt', 'v.date']
        desc_aliases = ['narration', 'description', 'particulars', 'remarks', 'transaction remarks', 'details', 'trans details', 'statement details']
        ref_aliases = ['chq/ref no', 'chq / ref no', 'ref no', 'ref', 'reference', 'cheque no', 'chq no', 'utr', 'tran id', 'txn id', 'reference number', 'cheque / ref. no.', 'chqno', 'cheque number']
        dr_aliases = ['debit', 'withdrawal', 'dr', 'dr amount', 'withdrawals', 'debit amount', 'withdrawal (dr)', 'withdrawal amt.', 'withdrawal amount (inr )']
        cr_aliases = ['credit', 'deposit', 'cr', 'cr amount', 'deposits', 'credit amount', 'deposit (cr)', 'deposit amt.', 'deposit amount (inr )']
        amount_aliases = ['amount', 'txn amount', 'transaction amount', 'net amount']
        bal_aliases = ['balance', 'closing balance', 'running balance', 'bal', 'closing bal', 'balance (inr)', 'balance (inr )', 'closing balance (inr )']
        type_aliases = ['dr/cr', 'type', 'cr/dr', 'indicator', 'txn type']

        for idx, col in enumerate(cleaned):
            if any(alias == col or alias in col for alias in type_aliases) and 'type' not in mapping:
                mapping['type'] = idx
            elif 'val' in col and any(alias in col for alias in val_date_aliases) and 'value_date' not in mapping:
                mapping['value_date'] = idx
            elif any(alias == col or col.startswith(alias) for alias in date_aliases) and 'date' not in mapping:
                mapping['date'] = idx
            elif any(alias in col for alias in desc_aliases) and 'desc' not in mapping:
                mapping['desc'] = idx
            elif any(alias in col for alias in ref_aliases) and 'ref' not in mapping:
                mapping['ref'] = idx
            elif any(alias == col or alias in col for alias in dr_aliases) and 'debit' not in mapping and 'cr' not in col:
                mapping['debit'] = idx
            elif any(alias == col or alias in col for alias in cr_aliases) and 'credit' not in mapping and 'dr' not in col:
                mapping['credit'] = idx
            elif any(alias in col for alias in amount_aliases) and 'amount' not in mapping:
                mapping['amount'] = idx
            elif any(alias in col for alias in bal_aliases) and 'balance' not in mapping:
                mapping['balance'] = idx

        if 'date' not in mapping:
            for idx, col in enumerate(cleaned):
                if 'date' in col:
                    mapping['date'] = idx
                    break

        return mapping

    @classmethod
    def validate_balance_chain(
        cls,
        rows: List[Dict[str, Any]],
        explicit_opening: Optional[Decimal] = None,
        explicit_closing: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Mandatory Phase 4 balance chain validator:
        1. Line-by-line running balance verification:
           balance_{i} == balance_{i-1} + credit_{i} - debit_{i}
        2. Statement-level verification:
           opening_balance + total_credits - total_debits == closing_balance
        3. Surfaces broken rows and discrepancy amounts without silently corrupting books.
        """
        if not rows:
            return {
                "valid": True,
                "opening_balance": explicit_opening or Decimal('0.00'),
                "closing_balance": explicit_closing or Decimal('0.00'),
                "calculated_closing_balance": explicit_opening or Decimal('0.00'),
                "total_credits": Decimal('0.00'),
                "total_debits": Decimal('0.00'),
                "discrepancy_amount": Decimal('0.00'),
                "discrepancy_rows": []
            }

        total_credits = sum((r.get("credit") or Decimal('0.00')) for r in rows)
        total_debits = sum((r.get("debit") or Decimal('0.00')) for r in rows)

        # Infer opening balance if not explicitly provided
        opening_balance = explicit_opening
        first_row = rows[0]
        if opening_balance is None and first_row.get("balance") is not None:
            b1 = first_row["balance"]
            c1 = first_row.get("credit") or Decimal('0.00')
            d1 = first_row.get("debit") or Decimal('0.00')
            opening_balance = b1 - c1 + d1

        # Infer closing balance if not explicitly provided
        closing_balance = explicit_closing
        last_row = rows[-1]
        if closing_balance is None and last_row.get("balance") is not None:
            closing_balance = last_row["balance"]

        discrepancy_rows = []
        prev_balance = opening_balance

        for idx, r in enumerate(rows):
            cur_balance = r.get("balance")
            deb = r.get("debit") or Decimal('0.00')
            cred = r.get("credit") or Decimal('0.00')

            if prev_balance is not None and cur_balance is not None:
                expected_cur = prev_balance + cred - deb
                diff = abs(cur_balance - expected_cur)
                if diff > Decimal('0.05'):
                    discrepancy_rows.append({
                        "row_index": idx + 1,
                        "date": str(r.get("date")),
                        "description": r.get("description", "")[:40],
                        "debit": float(deb),
                        "credit": float(cred),
                        "previous_balance": float(prev_balance),
                        "expected_balance": float(expected_cur),
                        "statement_balance": float(cur_balance),
                        "difference": float(diff)
                    })
            if cur_balance is not None:
                prev_balance = cur_balance
            elif prev_balance is not None:
                prev_balance = prev_balance + cred - deb

        calculated_closing = (opening_balance or Decimal('0.00')) + total_credits - total_debits
        statement_discrepancy = Decimal('0.00')
        if closing_balance is not None and opening_balance is not None:
            statement_discrepancy = abs(calculated_closing - closing_balance)

        is_valid = (statement_discrepancy <= Decimal('0.05')) and (len(discrepancy_rows) == 0)

        return {
            "valid": is_valid,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "calculated_closing_balance": calculated_closing,
            "total_credits": total_credits,
            "total_debits": total_debits,
            "discrepancy_amount": statement_discrepancy,
            "discrepancy_rows": discrepancy_rows
        }

    @classmethod
    def parse_csv(cls, file_content: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parses CSV statement into normalized transactions with partial error survival."""
        text = None
        for enc in ['utf-8-sig', 'utf-8', 'latin1', 'cp1252']:
            try:
                text = file_content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            raise ValidationError("Unable to decode CSV file with supported encodings.")

        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return [], []

        header_idx = 0
        for i, line in enumerate(lines[:20]):
            l_lower = line.lower()
            if 'date' in l_lower and any(kw in l_lower for kw in ['debit', 'credit', 'particulars', 'narration', 'amount', 'withdrawal', 'deposit']):
                header_idx = i
                break

        reader = csv.reader(lines[header_idx:])
        rows = list(reader)
        if not rows:
            return [], []

        header = rows[0]
        col_map = cls.detect_columns(header)
        if 'date' not in col_map or ('desc' not in col_map and 'ref' not in col_map):
            if len(header) >= 4:
                col_map = {'date': 0, 'desc': 1, 'debit': 2, 'credit': 3}
                if len(header) >= 5:
                    col_map['balance'] = 4
            else:
                raise ValidationError("CSV columns could not be mapped to bank transaction format.")

        # Batch date format detection
        sample_dates = [r[col_map['date']] for r in rows[1:30] if len(r) > col_map['date']]
        batch_date_fmt = cls.detect_batch_date_format(sample_dates)

        valid_rows = []
        errors = []
        prev_balance = None

        for row_num, row in enumerate(rows[1:], start=header_idx + 2):
            if not row or all(not str(c).strip() for c in row):
                continue
            try:
                d_idx = col_map.get('date')
                if d_idx is None or d_idx >= len(row):
                    continue
                date_val = cls.parse_date_str(row[d_idx], preferred_format=batch_date_fmt)
                if not date_val:
                    errors.append({"row": row_num, "error": f"Invalid date: '{row[d_idx]}'", "raw": ",".join(row[:6])})
                    continue

                val_date = cls.parse_date_str(row[col_map['value_date']], preferred_format=batch_date_fmt) if 'value_date' in col_map and col_map['value_date'] < len(row) else None
                desc = row[col_map['desc']].strip() if 'desc' in col_map and col_map['desc'] < len(row) else ""
                if cls.is_boilerplate_line(desc):
                    continue
                desc = cls.clean_boilerplate_from_narration(desc)
                if not desc or cls.is_boilerplate_line(desc):
                    continue
                ref = row[col_map['ref']].strip() if 'ref' in col_map and col_map['ref'] < len(row) else ""

                debit = Decimal('0.00')
                credit = Decimal('0.00')

                if 'debit' in col_map and col_map['debit'] < len(row):
                    debit = cls.clean_amount_str(row[col_map['debit']])
                if 'credit' in col_map and col_map['credit'] < len(row):
                    credit = cls.clean_amount_str(row[col_map['credit']])

                bal = cls.clean_amount_str(row[col_map['balance']]) if 'balance' in col_map and col_map['balance'] < len(row) and str(row[col_map['balance']]).strip() else None

                # Directional check via running balance delta if both balances are known
                if prev_balance is not None and bal is not None:
                    delta = bal - prev_balance
                    if delta > Decimal('0.01') and debit > 0 and credit == 0 and abs(delta - debit) < Decimal('0.05'):
                        credit = debit
                        debit = Decimal('0.00')
                    elif delta < -Decimal('0.01') and credit > 0 and debit == 0 and abs(abs(delta) - credit) < Decimal('0.05'):
                        debit = credit
                        credit = Decimal('0.00')

                # Handle single amount column with Type indicator or balance delta
                if debit == 0 and credit == 0 and 'amount' in col_map and col_map['amount'] < len(row):
                    amt = cls.clean_amount_str(row[col_map['amount']])
                    typ = str(row[col_map['type']]).strip().upper() if 'type' in col_map and col_map['type'] < len(row) else ""
                    raw_amt_str = str(row[col_map['amount']]).upper()
                    if 'DR' in typ or '-' in raw_amt_str or 'DR' in raw_amt_str:
                        debit = amt
                    elif 'CR' in typ or 'CR' in raw_amt_str:
                        credit = amt
                    elif prev_balance is not None and bal is not None:
                        delta = bal - prev_balance
                        if delta < 0:
                            debit = abs(delta)
                        else:
                            credit = delta
                    else:
                        credit = amt

                if bal is not None:
                    prev_balance = bal

                if debit == 0 and credit == 0:
                    errors.append({"row": row_num, "error": "Both Debit and Credit are zero", "raw": ",".join(row[:6])})
                    continue

                valid_rows.append({
                    "date": date_val,
                    "value_date": val_date or date_val,
                    "description": desc,
                    "reference": cls.extract_reference_number(desc, ref),
                    "debit": debit,
                    "credit": credit,
                    "balance": bal,
                    "confidence": 1.0,
                    "source_page": 1
                })
            except Exception as ex:
                errors.append({"row": row_num, "error": str(ex), "raw": ",".join(str(c) for c in row[:6])})

        return valid_rows, errors

    @classmethod
    def parse_excel(cls, file_content: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parses XLSX/XLS statement using openpyxl."""
        import openpyxl
        wb = openpyxl.load_workbook(filename=io.BytesIO(file_content), read_only=True, data_only=True)
        sheet = wb.active
        rows = list(sheet.iter_rows(values_only=True))
        wb.close()
        if not rows:
            return [], []

        header_idx = 0
        for i, row in enumerate(rows[:25]):
            r_str = " ".join(str(c).lower() for c in row if c is not None)
            if 'date' in r_str and any(kw in r_str for kw in ['debit', 'credit', 'particulars', 'narration', 'amount', 'withdrawal', 'deposit']):
                header_idx = i
                break

        header = [str(c or '') for c in rows[header_idx]]
        col_map = cls.detect_columns(header)
        if 'date' not in col_map or ('desc' not in col_map and 'ref' not in col_map):
            if len(header) >= 4:
                col_map = {'date': 0, 'desc': 1, 'debit': 2, 'credit': 3}
            else:
                raise ValidationError("Excel statement columns could not be mapped automatically.")

        sample_dates = [str(r[col_map['date']]) for r in rows[header_idx + 1:header_idx + 30] if len(r) > col_map['date'] and r[col_map['date']] is not None]
        batch_date_fmt = cls.detect_batch_date_format(sample_dates)

        valid_rows = []
        errors = []
        prev_balance = None

        for row_num, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            if not row or all(c is None or str(c).strip() == '' for c in row):
                continue
            try:
                d_idx = col_map.get('date')
                if d_idx is None or d_idx >= len(row):
                    continue
                date_val = cls.parse_date_str(row[d_idx], preferred_format=batch_date_fmt)
                if not date_val:
                    errors.append({"row": row_num, "error": f"Invalid date: '{row[d_idx]}'", "raw": str(row[:5])})
                    continue

                val_date = cls.parse_date_str(row[col_map['value_date']], preferred_format=batch_date_fmt) if 'value_date' in col_map and col_map['value_date'] < len(row) else None
                desc = str(row[col_map['desc']]).strip() if 'desc' in col_map and col_map['desc'] < len(row) and row[col_map['desc']] is not None else ""
                if cls.is_boilerplate_line(desc):
                    continue
                desc = cls.clean_boilerplate_from_narration(desc)
                if not desc or cls.is_boilerplate_line(desc):
                    continue
                ref = str(row[col_map['ref']]).strip() if 'ref' in col_map and col_map['ref'] < len(row) and row[col_map['ref']] is not None else ""

                debit = cls.clean_amount_str(row[col_map['debit']]) if 'debit' in col_map and col_map['debit'] < len(row) else Decimal('0.00')
                credit = cls.clean_amount_str(row[col_map['credit']]) if 'credit' in col_map and col_map['credit'] < len(row) else Decimal('0.00')
                bal = cls.clean_amount_str(row[col_map['balance']]) if 'balance' in col_map and col_map['balance'] < len(row) and row[col_map['balance']] is not None and str(row[col_map['balance']]).strip() else None

                # Directional check via running balance delta if both balances are known
                if prev_balance is not None and bal is not None:
                    delta = bal - prev_balance
                    if delta > Decimal('0.01') and debit > 0 and credit == 0 and abs(delta - debit) < Decimal('0.05'):
                        credit = debit
                        debit = Decimal('0.00')
                    elif delta < -Decimal('0.01') and credit > 0 and debit == 0 and abs(abs(delta) - credit) < Decimal('0.05'):
                        debit = credit
                        credit = Decimal('0.00')

                if debit == 0 and credit == 0 and 'amount' in col_map and col_map['amount'] < len(row):
                    amt = cls.clean_amount_str(row[col_map['amount']])
                    typ = str(row[col_map['type']]).strip().upper() if 'type' in col_map and col_map['type'] < len(row) else ""
                    raw_str = str(row[col_map['amount']]).upper()
                    if 'DR' in typ or '-' in raw_str or 'DR' in raw_str:
                        debit = amt
                    elif 'CR' in typ or 'CR' in raw_str:
                        credit = amt
                    elif prev_balance is not None and bal is not None:
                        delta = bal - prev_balance
                        if delta < 0:
                            debit = abs(delta)
                        else:
                            credit = delta
                    else:
                        credit = amt

                if bal is not None:
                    prev_balance = bal

                if debit == 0 and credit == 0:
                    errors.append({"row": row_num, "error": "Both Debit and Credit are zero", "raw": str(row[:5])})
                    continue

                valid_rows.append({
                    "date": date_val,
                    "value_date": val_date or date_val,
                    "description": desc,
                    "reference": cls.extract_reference_number(desc, ref),
                    "debit": debit,
                    "credit": credit,
                    "balance": bal,
                    "confidence": 1.0,
                    "source_page": 1
                })
            except Exception as ex:
                errors.append({"row": row_num, "error": str(ex), "raw": str(row[:5])})

        return valid_rows, errors

    @classmethod
    def parse_pdf(cls, file_content: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extracts tabular transactions from digital vector PDF with:
        1. PyMuPDF structured table extraction where available.
        2. Multi-line narration stitching for SBI, HDFC, ICICI, Axis, Kotak.
        3. Deterministic balance delta direction resolution.
        """
        valid_rows = []
        errors = []

        doc = None
        has_pymupdf = False
        try:
            import pymupdf
            doc = pymupdf.open(stream=file_content, filetype="pdf")
            has_pymupdf = True
        except ImportError:
            doc = None
            has_pymupdf = False

        pages_text = []

        if has_pymupdf and doc is not None:
            # Check total extracted text to determine if digital vector PDF or scanned
            total_text_chars = sum(len(page.get_text("text").strip()) for page in doc)
            if total_text_chars < 80:
                return [], [{"row": 0, "error": "Scanned or image-only PDF detected. Initiating Vision OCR.", "raw": ""}]

            # Strategy A: Try pymupdf find_tables()
            prev_balance = None
            for page_idx, page in enumerate(doc):
                try:
                    tables = page.find_tables()
                    for table in tables:
                        extracted = table.extract()
                        if not extracted or len(extracted) < 2:
                            continue
                        header = [str(c or '').strip() for c in extracted[0]]
                        col_map = cls.detect_columns(header)
                        if 'date' in col_map and ('debit' in col_map or 'credit' in col_map or 'amount' in col_map):
                            for r_idx, row in enumerate(extracted[1:]):
                                if not row or all(not str(c).strip() for c in row):
                                    continue
                                try:
                                    d_str = str(row[col_map['date']]).strip()
                                    dt = cls.parse_date_str(d_str)
                                    if not dt:
                                        continue
                                    desc = str(row[col_map['desc']]).strip() if 'desc' in col_map and col_map['desc'] < len(row) else ""
                                    if cls.is_boilerplate_line(desc):
                                        continue
                                    desc = cls.clean_boilerplate_from_narration(desc)
                                    if not desc or cls.is_boilerplate_line(desc):
                                        continue
                                    ref = str(row[col_map['ref']]).strip() if 'ref' in col_map and col_map['ref'] < len(row) else ""
                                    deb = cls.clean_amount_str(row[col_map['debit']]) if 'debit' in col_map and col_map['debit'] < len(row) else Decimal('0.00')
                                    cred = cls.clean_amount_str(row[col_map['credit']]) if 'credit' in col_map and col_map['credit'] < len(row) else Decimal('0.00')
                                    bal = cls.clean_amount_str(row[col_map['balance']]) if 'balance' in col_map and col_map['balance'] < len(row) and str(row[col_map['balance']]).strip() else None

                                    # Running balance delta direction correction
                                    if prev_balance is not None and bal is not None:
                                        delta = bal - prev_balance
                                        if delta > Decimal('0.01') and deb > 0 and cred == 0 and abs(delta - deb) < Decimal('0.05'):
                                            cred = deb
                                            deb = Decimal('0.00')
                                        elif delta < -Decimal('0.01') and cred > 0 and deb == 0 and abs(abs(delta) - cred) < Decimal('0.05'):
                                            deb = cred
                                            cred = Decimal('0.00')
                                    if bal is not None:
                                        prev_balance = bal

                                    if deb > 0 or cred > 0:
                                        valid_rows.append({
                                            "date": dt,
                                            "value_date": dt,
                                            "description": desc,
                                            "reference": cls.extract_reference_number(desc, ref),
                                            "debit": deb,
                                            "credit": cred,
                                            "balance": bal,
                                            "confidence": 0.98,
                                            "source_page": page_idx + 1
                                        })
                                except Exception:
                                    continue
                except Exception:
                    pass

            if len(valid_rows) > 0:
                return valid_rows, errors

            # Gather text for Strategy B
            for page_idx, page in enumerate(doc):
                txt = page.get_text("text") or ""
                pages_text.append((page_idx + 1, txt))
        else:
            # Fallback to pypdf for text extraction when PyMuPDF is not installed
            try:
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_content))
                total_text_chars = 0
                for p_idx, page in enumerate(reader.pages):
                    txt = page.extract_text() or ""
                    total_text_chars += len(txt.strip())
                    pages_text.append((p_idx + 1, txt))

                if total_text_chars < 80:
                    return [], [{"row": 0, "error": "Scanned or image-only PDF detected. Initiating Vision OCR.", "raw": ""}]
            except Exception as e:
                return [], [{"row": 0, "error": f"PDF reading failed: {str(e)}", "raw": ""}]

        # Strategy B: Multi-line narration stitching line tokenizer
        date_start_re = re.compile(
            r'^(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{1,2}[\s\-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-]\d{2,4})',
            re.IGNORECASE
        )
        amt_finder_re = re.compile(r'(\b\d{1,3}(?:,\d{2,3})*\.\d{2}\b|\b\d+\.\d{2}\b)')

        boilerplate_re = cls.BOILERPLATE_REGEX
        is_credit_re = cls.IS_CREDIT_REGEX
        is_debit_re = cls.IS_DEBIT_REGEX

        # Detect column order: Does 'Deposit' appear before 'Withdrawal' in any table header?
        deposit_col_first = False
        for page_idx, txt in pages_text:
            for line in txt.splitlines():
                l_lower = line.lower()
                if ('deposit' in l_lower or 'credit' in l_lower) and ('withdrawal' in l_lower or 'debit' in l_lower):
                    dep_pos = min(l_lower.find('deposit') if 'deposit' in l_lower else 9999, l_lower.find('credit') if 'credit' in l_lower else 9999)
                    wdr_pos = min(l_lower.find('withdrawal') if 'withdrawal' in l_lower else 9999, l_lower.find('debit') if 'debit' in l_lower else 9999)
                    if dep_pos < wdr_pos:
                        deposit_col_first = True
                        break
                    elif wdr_pos < dep_pos:
                        deposit_col_first = False
                        break
            if deposit_col_first:
                break

        all_lines = []
        for page_idx, txt in pages_text:
            for line in txt.splitlines():
                l_str = line.strip()
                if not l_str:
                    continue
                # If standalone boilerplate line (e.g. disclaimer or closing balance line), ignore
                if cls.is_boilerplate_line(l_str) and not date_start_re.match(l_str):
                    continue
                # If transaction line contains closing balance / footer at end, strip it
                if date_start_re.match(l_str):
                    if cls.is_boilerplate_line(l_str):
                        continue
                    cutoff = cls.BOILERPLATE_REGEX.search(l_str)
                    if cutoff:
                        l_str = l_str[:cutoff.start()].strip()
                        if cls.is_boilerplate_line(l_str):
                            continue
                all_lines.append((page_idx, l_str))

        pending_blocks = []
        current_block = None

        for page_no, l_str in all_lines:
            m = date_start_re.match(l_str)
            if m:
                if cls.is_boilerplate_line(l_str):
                    if current_block:
                        pending_blocks.append(current_block)
                        current_block = None
                    continue
                cutoff = cls.BOILERPLATE_REGEX.search(l_str)
                if cutoff:
                    before_c = l_str[:cutoff.start()].strip()
                    if cls.is_boilerplate_line(before_c):
                        if current_block:
                            pending_blocks.append(current_block)
                            current_block = None
                        continue
                    l_str = before_c

                if current_block:
                    pending_blocks.append(current_block)
                current_block = {
                    "date_str": m.group(1),
                    "page": page_no,
                    "lines": [l_str]
                }
            elif current_block:
                if cls.is_boilerplate_line(l_str):
                    continue
                cutoff = cls.BOILERPLATE_REGEX.search(l_str)
                if cutoff:
                    clean_part = l_str[:cutoff.start()].strip()
                    if clean_part and not cls.is_boilerplate_line(clean_part):
                        current_block["lines"].append(clean_part)
                    continue
                current_block["lines"].append(l_str)

        if current_block:
            pending_blocks.append(current_block)

        prev_balance = None
        for block in pending_blocks:
            dt = cls.parse_date_str(block["date_str"])
            if not dt:
                continue

            full_block_text = " ".join(block["lines"])
            full_block_text = cls.clean_boilerplate_from_narration(full_block_text)
            if not full_block_text or cls.is_boilerplate_line(full_block_text):
                continue

            amts = amt_finder_re.findall(full_block_text)
            if not amts:
                continue

            cleaned_narration = full_block_text
            for a in amts:
                cleaned_narration = cleaned_narration.replace(a, " ")
            cleaned_narration = date_start_re.sub("", cleaned_narration).strip()
            norm_desc = cls.normalize_narration(cleaned_narration)
            if not norm_desc or cls.is_boilerplate_line(norm_desc):
                continue

            ref_no = cls.extract_reference_number(full_block_text)

            debit = Decimal('0.00')
            credit = Decimal('0.00')
            bal = None

            upper_block = full_block_text.upper()
            has_credit = bool(is_credit_re.search(upper_block))
            has_debit = bool(is_debit_re.search(upper_block))

            if len(amts) >= 3:
                if deposit_col_first:
                    credit = cls.clean_amount_str(amts[0])
                    debit = cls.clean_amount_str(amts[1])
                else:
                    debit = cls.clean_amount_str(amts[0])
                    credit = cls.clean_amount_str(amts[1])
                bal = cls.clean_amount_str(amts[2])
            elif len(amts) == 2:
                amt_val = cls.clean_amount_str(amts[0])
                bal = cls.clean_amount_str(amts[1])

                if prev_balance is not None and bal is not None:
                    delta = bal - prev_balance
                    if abs(delta - amt_val) <= Decimal('0.05') or delta > Decimal('0.01'):
                        credit = amt_val
                    elif abs(delta - (-amt_val)) <= Decimal('0.05') or delta < -Decimal('0.01'):
                        debit = amt_val
                    elif has_credit and not has_debit:
                        credit = amt_val
                    elif has_debit and not has_credit:
                        debit = amt_val
                    elif deposit_col_first:
                        credit = amt_val
                    else:
                        debit = amt_val
                elif has_credit and not has_debit:
                    credit = amt_val
                elif has_debit and not has_credit:
                    debit = amt_val
                elif deposit_col_first:
                    credit = amt_val
                else:
                    debit = amt_val
            elif len(amts) == 1:
                amt_val = cls.clean_amount_str(amts[0])
                if prev_balance is not None and abs(amt_val - prev_balance) <= Decimal('0.05') and cls.BOILERPLATE_REGEX.search(full_block_text):
                    continue
                if has_debit and not has_credit:
                    debit = amt_val
                else:
                    credit = amt_val

            if bal is not None:
                prev_balance = bal

            if debit > 0 or credit > 0:
                valid_rows.append({
                    "date": dt,
                    "value_date": dt,
                    "description": norm_desc,
                    "reference": ref_no,
                    "debit": debit,
                    "credit": credit,
                    "balance": bal,
                    "confidence": 0.95,
                    "source_page": block["page"]
                })

        return valid_rows, errors

    @classmethod
    def parse_scanned_pdf_or_image(
        cls,
        file_bytes: bytes,
        filename: str,
        mime_type: str = "image/png",
        custom_api_key: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Processes scanned PDFs or document photos using Pillow image preprocessing
        and Google Gemini Vision AI. Returns normalized transactions.
        """
        import os
        import json
        from PIL import Image

        valid_rows = []
        errors = []

        is_pdf = "pdf" in mime_type.lower() or file_bytes[:4] == b'%PDF'
        pages_to_process = []

        if is_pdf:
            try:
                import pymupdf
                doc = pymupdf.open(stream=file_bytes, filetype="pdf")
                max_pages = min(5, len(doc))
                for p_idx in range(max_pages):
                    pix = doc[p_idx].get_pixmap(dpi=200)
                    pages_to_process.append((p_idx + 1, pix.tobytes("png"), "image/png"))
            except (ImportError, Exception):
                # If pymupdf is not available, pass the PDF directly to Gemini Vision
                pages_to_process.append((1, file_bytes, "application/pdf"))
        else:
            pages_to_process.append((1, file_bytes, mime_type))

        active_key = (custom_api_key or "").strip() or os.environ.get("GEMINI_API_KEY")
        if not active_key:
            errors.append({
                "row": 0,
                "error": "Scanned document detected. Configure a Gemini Vision API Key in Settings or pass X-Gemini-Key to extract.",
                "raw": ""
            })
            return [], errors

        prompt = (
            "You are an expert Indian banking OCR and forensic accounting assistant.\n"
            "Extract every transaction from this bank statement page image into strict JSON adhering to the schema.\n\n"
            "CRITICAL RULES FOR INDIAN BANK STATEMENTS:\n"
            "1. COLUMN HEADERS & ORDER (CRITICAL):\n"
            "   - Carefully inspect table column headers on the page. In many Indian banks (such as Canara Bank, Punjab National Bank, Central Bank), "
            "     the DEPOSITS (Credit) column appears BEFORE the WITHDRAWALS (Debit) column (e.g., Date | Narration | Chq | Deposits | Withdrawals | Balance).\n"
            "   - In other banks (SBI, HDFC, ICICI, Axis), Withdrawals appears before Deposits.\n"
            "   - NEVER assume the column order. Map amounts strictly according to the column header text.\n\n"
            "2. INDIAN BANKING DOUBLE-ENTRY CONVENTIONS (BY vs TO):\n"
            "   - NARRATIONS STARTING WITH 'BY' (e.g. 'BY CLG', 'BY TRF', 'BY CASH', 'BY CLEARING', 'NEFT CR', 'RTGS CR', 'UPI/CR', 'IMPS CR', 'CASH DEPOSIT'): "
            "     These are ALWAYS DEPOSITS / CREDITS (Money In / Receipts). For these, set credit > 0 and debit = 0.0.\n"
            "   - NARRATIONS STARTING WITH 'TO' (e.g. 'TO CLG', 'TO TRF', 'TO CLEARING', 'TO TRANSFER', 'CHQ PAID', 'NEFT DR', 'RTGS DR', 'UPI/DR', 'CASA DEBIT', 'SERVICE CHARGE', 'SMS CHARGES'): "
            "     These are ALWAYS WITHDRAWALS / DEBITS (Money Out / Payments). For these, set debit > 0 and credit = 0.0.\n\n"
            "3. DO NOT EXTRACT SUMMARY, BALANCE, GUIDELINES, OR DISCLAIMERS AS TRANSACTIONS:\n"
            "   - NEVER extract general guidelines, constituent disclaimers, phishing notices, cyber security tips, or ombudsman contact details as transactions!\n"
            "   - Ignore text such as 'DISCLAIMER UNLESS THE CONSTITUENT...', 'CODE OR COULD BE AN ATTEMPT TO PHISH', 'ALWAYS LOGIN THROUGH...', 'DO NOT SHARE ATM PIN', 'Details of Banking Ombudsman', 'ARE YOU A MERCHANT', 'IMB USERS'.\n"
            "   - NEVER extract statement summary rows, closing balance rows (e.g. 'Closing Balance as on...', 'Current Account Balance', 'Brought Forward', 'Carried Forward', 'Total Debits', 'Total Credits') as a transaction!\n"
            "   - Only extract legitimate financial transaction line items that occurred on specific dates.\n\n"
            "4. For each transaction extract:\n"
            "   - date: YYYY-MM-DD\n"
            "   - value_date: YYYY-MM-DD (if present, else empty)\n"
            "   - description: full narration including party name, cheque number, or UPI handle\n"
            "   - reference: cheque number, UTR number, or transaction ID\n"
            "   - debit: withdrawal / money out amount as positive float (0.0 if deposit)\n"
            "   - credit: deposit / money in amount as positive float (0.0 if withdrawal)\n"
            "   - balance: running balance after transaction if visible\n\n"
            "Also extract opening_balance and closing_balance if present in page header or footer."
        )

        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=active_key)

            for page_no, img_bytes, img_mime in pages_to_process:
                try:
                    pil_img = Image.open(io.BytesIO(img_bytes))
                    if pil_img.mode in ("RGBA", "P"):
                        pil_img = pil_img.convert("RGB")
                    if max(pil_img.size) > 2000:
                        pil_img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                    out_buf = io.BytesIO()
                    pil_img.save(out_buf, format="JPEG", quality=85)
                    proc_bytes = out_buf.getvalue()
                    proc_mime = "image/jpeg"
                except Exception:
                    proc_bytes = img_bytes
                    proc_mime = img_mime

                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=[
                        types.Part.from_bytes(data=proc_bytes, mime_type=proc_mime),
                        prompt
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=BankStatementExtractionSchema,
                        temperature=0.1
                    )
                )
                res_dict = json.loads(response.text)
                txs = res_dict.get("transactions", [])
                for t in txs:
                    raw_desc = (t.get("description") or "").strip()
                    if not raw_desc:
                        continue

                    # 1. Reject summary, footer, guidelines, or closing balance rows
                    if cls.is_boilerplate_line(raw_desc):
                        continue
                    cleaned_desc = cls.clean_boilerplate_from_narration(raw_desc)
                    if not cleaned_desc or cls.is_boilerplate_line(cleaned_desc):
                        continue
                    raw_desc = cleaned_desc

                    dt = cls.parse_date_str(t.get("date"))
                    if not dt:
                        continue
                    deb = Decimal(str(t.get("debit", 0.0) or 0.0))
                    cred = Decimal(str(t.get("credit", 0.0) or 0.0))
                    bal_val = t.get("balance")
                    bal = Decimal(str(bal_val)) if bal_val is not None else None

                    # 2. Deterministic Indian banking direction safety guardrails
                    norm_desc = cls.normalize_narration(raw_desc)
                    has_credit = bool(cls.IS_CREDIT_REGEX.search(norm_desc))
                    has_debit = bool(cls.IS_DEBIT_REGEX.search(norm_desc))

                    if has_credit and not has_debit:
                        if deb > 0 and cred == 0:
                            cred = deb
                            deb = Decimal('0.00')
                    elif has_debit and not has_credit:
                        if cred > 0 and deb == 0:
                            deb = cred
                            cred = Decimal('0.00')

                    if deb > 0 or cred > 0:
                        valid_rows.append({
                            "date": dt,
                            "value_date": cls.parse_date_str(t.get("value_date")) or dt,
                            "description": norm_desc,
                            "reference": t.get("reference") or None,
                            "debit": deb,
                            "credit": cred,
                            "balance": bal,
                            "confidence": 0.95,
                            "source_page": page_no
                        })
        except Exception as e:
            errors.append({"row": 0, "error": f"AI Vision OCR error: {str(e)}", "raw": ""})

        # Cross-row balance progression verification
        for i in range(1, len(valid_rows)):
            prev_row = valid_rows[i - 1]
            curr_row = valid_rows[i]
            prev_bal = prev_row.get("balance")
            curr_bal = curr_row.get("balance")
            if prev_bal is not None and curr_bal is not None:
                diff = curr_bal - prev_bal
                c_deb = curr_row["debit"]
                c_cred = curr_row["credit"]
                # Balance increased by approximately transaction amount -> must be credit (deposit)
                if diff > 0 and c_deb > 0 and c_cred == 0 and abs(diff - c_deb) < Decimal('0.05'):
                    curr_row["credit"] = c_deb
                    curr_row["debit"] = Decimal('0.00')
                # Balance decreased by approximately transaction amount -> must be debit (withdrawal)
                elif diff < 0 and c_cred > 0 and c_deb == 0 and abs(abs(diff) - c_cred) < Decimal('0.05'):
                    curr_row["debit"] = c_cred
                    curr_row["credit"] = Decimal('0.00')

        return valid_rows, errors

    @classmethod
    def parse_statement(
        cls,
        company: Company,
        bank_ledger: Ledger,
        file_bytes: bytes,
        filename: str,
        user=None,
        custom_api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Primary entry point for bank statement ingestion.
        1. Computes SHA-256 file_hash to prevent duplicate uploads immediately.
        2. Routes to appropriate engine (CSV, Excel, Native PDF, or Scanned Vision OCR).
        3. Executes mandatory balance chain validation.
        4. Deduplicates overlapping statements via deterministic SHA-256 transaction fingerprints.
        5. Matches party intelligence and persists BankStatementImport and BankTransaction.
        """
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        existing_import = BankStatementImport.objects.filter(
            company=company,
            bank_ledger=bank_ledger,
            file_hash=file_hash,
            status__in=['COMPLETED', 'PARTIAL']
        ).first()

        if existing_import:
            return {
                "import_id": str(existing_import.id),
                "source_file": existing_import.source_file_name,
                "file_format": existing_import.file_format,
                "file_hash": file_hash,
                "status": existing_import.status,
                "is_duplicate_file": True,
                "message": f"This exact statement was already imported on {existing_import.created_at.strftime('%d-%b-%Y %H:%M')}.",
                "total_detected": existing_import.total_rows,
                "successful_rows": existing_import.successful_rows,
                "imported_count": 0,
                "auto_matched_count": 0,
                "suggested_count": 0,
                "needs_review_count": 0,
                "unresolved_rows": 0,
                "failed_rows": existing_import.failed_rows,
                "duplicates_detected": existing_import.successful_rows,
                "balance_chain_valid": existing_import.balance_chain_valid,
                "discrepancy_amount": float(existing_import.discrepancy_amount),
                "errors": existing_import.error_summary[:10]
            }

        filename_lower = filename.lower()
        file_format = 'CSV'
        valid_rows = []
        errors = []

        if filename_lower.endswith('.csv'):
            file_format = 'CSV'
            valid_rows, errors = cls.parse_csv(file_bytes)
        elif filename_lower.endswith('.xlsx'):
            file_format = 'XLSX'
            valid_rows, errors = cls.parse_excel(file_bytes)
        elif filename_lower.endswith('.xls'):
            file_format = 'XLS'
            valid_rows, errors = cls.parse_excel(file_bytes)
        elif filename_lower.endswith('.pdf'):
            file_format = 'PDF'
            valid_rows, errors = cls.parse_pdf(file_bytes)
            if len(valid_rows) == 0:
                scanned_rows, scanned_errs = cls.parse_scanned_pdf_or_image(
                    file_bytes, filename, mime_type="application/pdf", custom_api_key=custom_api_key
                )
                if len(scanned_rows) > 0:
                    valid_rows = scanned_rows
                    errors = scanned_errs
                else:
                    errors += scanned_errs
        else:
            file_format = 'IMAGE'
            mime = "image/png"
            if filename_lower.endswith(('.jpg', '.jpeg')):
                mime = "image/jpeg"
            elif filename_lower.endswith('.webp'):
                mime = "image/webp"
            valid_rows, errors = cls.parse_scanned_pdf_or_image(
                file_bytes, filename, mime_type=mime, custom_api_key=custom_api_key
            )

        # Filter out boilerplate / guideline rows and strip trailing disclaimers
        filtered_rows = []
        for r in valid_rows:
            raw_d = str(r.get('description', '') or '')
            if cls.is_boilerplate_line(raw_d):
                continue
            cleaned_d = cls.clean_boilerplate_from_narration(raw_d)
            if not cleaned_d or cls.is_boilerplate_line(cleaned_d):
                continue
            r['description'] = cleaned_d
            filtered_rows.append(r)
        valid_rows = filtered_rows

        valid_rows.sort(key=lambda r: r.get("date") or datetime.date.min)

        # Cross-row balance progression verification for ALL statement formats (PDF, CSV, Excel, Image):
        for i in range(1, len(valid_rows)):
            prev_row = valid_rows[i - 1]
            curr_row = valid_rows[i]
            prev_bal = prev_row.get("balance")
            curr_bal = curr_row.get("balance")
            if prev_bal is not None and curr_bal is not None:
                diff = curr_bal - prev_bal
                c_deb = curr_row.get("debit") or Decimal('0.00')
                c_cred = curr_row.get("credit") or Decimal('0.00')
                # Balance increased by approximately transaction amount -> must be credit (deposit / receipt)
                if diff > Decimal('0.01') and c_deb > 0 and c_cred == 0 and abs(diff - c_deb) < Decimal('0.05'):
                    curr_row["credit"] = c_deb
                    curr_row["debit"] = Decimal('0.00')
                # Balance decreased by approximately transaction amount -> must be debit (withdrawal / payment)
                elif diff < -Decimal('0.01') and c_cred > 0 and c_deb == 0 and abs(abs(diff) - c_cred) < Decimal('0.05'):
                    curr_row["debit"] = c_cred
                    curr_row["credit"] = Decimal('0.00')

        chain_report = cls.validate_balance_chain(valid_rows)
        balance_valid = chain_report["valid"]
        discrepancy_amt = chain_report["discrepancy_amount"]

        if not balance_valid:
            errors.append({
                "row": 0,
                "error": f"Balance chain discrepancy detected: Statement difference of ₹{discrepancy_amt:.2f}.",
                "details": chain_report["discrepancy_rows"][:5]
            })

        total_detected = len(valid_rows) + len(errors)
        status = 'COMPLETED'
        if not balance_valid or (len(errors) > 0 and len(valid_rows) > 0):
            status = 'PARTIAL'
        elif len(valid_rows) == 0 and len(errors) > 0:
            status = 'FAILED'

        from apps.accounting.services.party_intelligence_service import PartyIntelligenceService

        with transaction.atomic():
            import_record = BankStatementImport.objects.create(
                company=company,
                bank_ledger=bank_ledger,
                source_file_name=str(filename or "")[:255],
                file_hash=str(file_hash or "")[:64],
                file_format=str(file_format or "")[:20],
                status=str(status or "")[:20],
                total_rows=total_detected,
                successful_rows=len(valid_rows),
                failed_rows=len(errors),
                error_summary=errors[:50],
                opening_balance=chain_report["opening_balance"],
                closing_balance=chain_report["closing_balance"],
                calculated_closing_balance=chain_report["calculated_closing_balance"],
                balance_chain_valid=balance_valid,
                discrepancy_amount=discrepancy_amt,
                created_by=user
            )

            created_transactions = []
            duplicate_count = 0
            auto_matched_count = 0
            suggested_count = 0

            for row in valid_rows:
                raw_desc = str(row.get('description', '') or '')
                norm_desc = cls.normalize_narration(raw_desc, max_length=500)[:500]
                ref_no = cls.extract_reference_number(raw_desc, row.get('reference'))
                if ref_no:
                    ref_no = str(ref_no).strip()[:100]
                deb_amt = row.get('debit', Decimal('0.00'))
                cred_amt = row.get('credit', Decimal('0.00'))
                tx_date = row.get('date')

                # Directional integrity check prior to party matching:
                # In Indian banking, narrations starting with 'BY' (BY CLG, BY TRF, BY CASH, etc.) are strictly Deposits.
                # Narrations starting with 'TO' (TO CLG, TO TRF, CHQ PAID, etc.) are strictly Withdrawals.
                if cls.IS_CREDIT_REGEX.search(norm_desc) and not cls.IS_DEBIT_REGEX.search(norm_desc):
                    if deb_amt > 0 and cred_amt == 0:
                        cred_amt = deb_amt
                        deb_amt = Decimal('0.00')
                elif cls.IS_DEBIT_REGEX.search(norm_desc) and not cls.IS_CREDIT_REGEX.search(norm_desc):
                    if cred_amt > 0 and deb_amt == 0:
                        deb_amt = cred_amt
                        cred_amt = Decimal('0.00')

                primary_id = ref_no if ref_no else norm_desc
                fprint = cls.compute_transaction_fingerprint(company.id, bank_ledger.id, tx_date, deb_amt, cred_amt, primary_id)
                if fprint:
                    fprint = str(fprint)[:64]

                dup_qs = BankTransaction.objects.filter(
                    company=company,
                    bank_ledger=bank_ledger
                ).filter(
                    Q(fingerprint=fprint) |
                    (Q(transaction_date=tx_date, debit_amount=deb_amt, credit_amount=cred_amt) & (Q(reference_number=ref_no) if ref_no else Q(normalized_narration=norm_desc)))
                )

                if dup_qs.exists():
                    duplicate_count += 1
                    continue

                match_res = PartyIntelligenceService.match_transaction(
                    company=company,
                    narration=norm_desc,
                    debit_amount=deb_amt,
                    credit_amount=cred_amt,
                    reference_number=ref_no,
                    tx_date=tx_date
                )

                # Accounting integrity guardrail:
                # A customer paying by cheque / clearing is a Deposit (Credit), NOT a Payment.
                mp = match_res.get('matched_party')
                if mp and mp.ledger_type == 'CUSTOMER':
                    if deb_amt > 0 and cred_amt == 0:
                        if not re.search(r'\bREFUND\b', norm_desc, re.IGNORECASE):
                            cred_amt = deb_amt
                            deb_amt = Decimal('0.00')
                            match_res.setdefault('signals', []).append(
                                "Reclassified to Deposit (Credit) for Customer party"
                            )
                elif mp and mp.ledger_type == 'SUPPLIER':
                    if cred_amt > 0 and deb_amt == 0:
                        if not re.search(r'\bREFUND\b', norm_desc, re.IGNORECASE):
                            deb_amt = cred_amt
                            cred_amt = Decimal('0.00')
                            match_res.setdefault('signals', []).append(
                                "Reclassified to Withdrawal (Debit) for Supplier party"
                            )

                initial_status = 'UNRESOLVED'
                if match_res['confidence'] >= 0.95:
                    initial_status = 'MATCHED_AUTO'
                    auto_matched_count += 1
                elif match_res['confidence'] >= 0.75:
                    initial_status = 'MATCHED_SUGGESTED'
                    suggested_count += 1

                tx = BankTransaction.objects.create(
                    company=company,
                    statement_import=import_record,
                    bank_ledger=bank_ledger,
                    transaction_date=tx_date,
                    value_date=row.get('value_date') or tx_date,
                    description=raw_desc,
                    normalized_narration=norm_desc[:500],
                    reference_number=ref_no[:100] if ref_no else None,
                    fingerprint=fprint[:64] if fprint else None,
                    debit_amount=deb_amt,
                    credit_amount=cred_amt,
                    balance=row.get('balance'),
                    source_file=str(filename or "")[:255],
                    source_page=row.get('source_page', 1),
                    extraction_confidence=row.get('confidence', 1.0),
                    status=initial_status,
                    matched_party=match_res.get('matched_party'),
                    matched_invoice=match_res.get('matched_invoice'),
                    match_confidence=match_res.get('confidence', 0.0),
                    match_notes={
                        "is_duplicate": False,
                        "signals": match_res.get('signals', []),
                        "suggested_matches": match_res.get('suggested_matches', [])
                    }
                )

                # Auto-reconcile cash deposit as cash invoice receipt
                if match_res.get('is_cash_deposit') and cred_amt > Decimal('0.00') and match_res.get('matched_party'):
                    from apps.accounting.services.bank_reconciliation_service import BankReconciliationService
                    try:
                        BankReconciliationService.resolve_transaction(
                            bank_tx=tx,
                            action_type='RECORD_PAYMENT',
                            payload={
                                'party_id': str(match_res['matched_party'].id),
                                'narration': f"Cash Deposit: {norm_desc}"
                            },
                            user=user
                        )
                        auto_matched_count += 1
                    except Exception as ex:
                        logger.warning(f"Auto-reconciliation for cash deposit {tx.id} skipped: {ex}")

                created_transactions.append(tx)

            unresolved_count = len(created_transactions) - auto_matched_count - suggested_count

            return {
                "import_id": str(import_record.id),
                "source_file": filename,
                "file_hash": file_hash,
                "file_format": file_format,
                "status": status,
                "total_detected": total_detected,
                "successful_rows": len(valid_rows),
                "imported_count": len(created_transactions),
                "auto_matched_count": auto_matched_count,
                "suggested_count": suggested_count,
                "needs_review_count": suggested_count + max(0, unresolved_count),
                "unresolved_rows": max(0, unresolved_count),
                "failed_rows": len(errors),
                "duplicates_detected": duplicate_count,
                "balance_chain_valid": balance_valid,
                "opening_balance": float(chain_report["opening_balance"]) if chain_report["opening_balance"] is not None else None,
                "closing_balance": float(chain_report["closing_balance"]) if chain_report["closing_balance"] is not None else None,
                "calculated_closing_balance": float(chain_report["calculated_closing_balance"]),
                "discrepancy_amount": float(discrepancy_amt),
                "discrepancy_rows": chain_report["discrepancy_rows"][:5],
                "errors": errors[:10]
            }
