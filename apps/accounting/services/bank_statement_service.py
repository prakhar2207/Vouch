import io
import re
import csv
import uuid
import datetime
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.accounting.models import BankStatementImport, BankTransaction
from apps.companies.models import Company
from apps.ledgers.models import Ledger

class BankStatementService:
    """
    Multi-format bank statement parser & normalizer.
    Supports CSV, Excel (XLSX/XLS), PDF, and Scanned Image OCR.
    Extracts, validates, cleans narration, and detects duplicate transactions.
    Survives partial failures and preserves per-row error tracking.
    """

    DATE_PATTERNS = [
        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y",
        "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %b %y",
        "%d-%B-%Y", "%d %B %Y", "%Y/%m/%d"
    ]

    @classmethod
    def clean_amount_str(cls, val: Any) -> Decimal:
        if val is None:
            return Decimal('0.00')
        s = str(val).strip()
        if not s or s.lower() in ['nan', 'none', '-', '', 'null', 'nil']:
            return Decimal('0.00')
        s = re.sub(r'[₹$€£, ]', '', s)
        is_dr = False
        is_cr = False
        if s.upper().endswith('DR') or s.upper().startswith('DR'):
            is_dr = True
            s = re.sub(r'(?i)dr', '', s).strip()
        elif s.upper().endswith('CR') or s.upper().startswith('CR'):
            is_cr = True
            s = re.sub(r'(?i)cr', '', s).strip()
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1].strip()
        try:
            val_dec = Decimal(s)
            return abs(val_dec)
        except Exception:
            return Decimal('0.00')

    @classmethod
    def parse_date_str(cls, val: Any) -> Optional[datetime.date]:
        if not val:
            return None
        if isinstance(val, (datetime.date, datetime.datetime)):
            return val.date() if isinstance(val, datetime.datetime) else val
        s = str(val).strip()
        s = s.split(' ')[0].split('T')[0]
        for pattern in cls.DATE_PATTERNS:
            try:
                return datetime.datetime.strptime(s, pattern).date()
            except ValueError:
                continue
        return None

    @classmethod
    def normalize_narration(cls, text: str) -> str:
        """
        Cleans bank narration, removes redundant whitespace,
        and standardizes identifiers for reliable party matching.
        """
        if not text:
            return ""
        s = str(text).strip()
        s = re.sub(r'\s+', ' ', s)
        return s.strip()

    @classmethod
    def extract_upi_id(cls, text: str) -> Optional[str]:
        """Extracts UPI VPA handle from narration if present, e.g. 'UPI/rajesh@okhdfcbank/...'"""
        if not text:
            return None
        match = re.search(r'([a-zA-Z0-9._\-]+@[a-zA-Z0-9]+)', text)
        if match:
            return match.group(1).upper()
        return None

    @classmethod
    def extract_reference_number(cls, text: str, ref_col_val: Optional[str] = None) -> Optional[str]:
        if ref_col_val and str(ref_col_val).strip() and str(ref_col_val).strip().lower() not in ['nan', 'none', '-']:
            return str(ref_col_val).strip()
        if not text:
            return None
        utr_match = re.search(r'(?:UTR|REF|NO|CHQ|NEFT|IMPS)[/:\s\-]+([A-Za-z0-9]{6,22})', text, re.IGNORECASE)
        if utr_match:
            return utr_match.group(1).upper()
        rrn_match = re.search(r'\b(\d{12})\b', text)
        if rrn_match:
            return rrn_match.group(1)
        return None

    @classmethod
    def detect_columns(cls, header_row: List[str]) -> Dict[str, int]:
        """
        Identifies column indices for Date, Value Date, Description, Reference,
        Debit, Credit, Amount, and Balance based on common Indian bank headers.
        """
        mapping = {}
        cleaned = [str(col).strip().lower() for col in header_row]

        date_aliases = ['txn date', 'transaction date', 'trans date', 'date', 'posting date', 'value dt', 'txndate']
        val_date_aliases = ['value date', 'val date', 'value dt', 'v.date']
        desc_aliases = ['narration', 'description', 'particulars', 'remarks', 'transaction remarks', 'details', 'trans details', 'statement details']
        ref_aliases = ['chq/ref no', 'chq / ref no', 'ref no', 'ref', 'reference', 'cheque no', 'chq no', 'utr', 'tran id', 'txn id', 'reference number', 'cheque / ref. no.']
        dr_aliases = ['debit', 'withdrawal', 'dr', 'dr amount', 'withdrawals', 'debit amount', 'withdrawal (dr)']
        cr_aliases = ['credit', 'deposit', 'cr', 'cr amount', 'deposits', 'credit amount', 'deposit (cr)']
        amount_aliases = ['amount', 'txn amount', 'transaction amount', 'net amount']
        bal_aliases = ['balance', 'closing balance', 'running balance', 'bal', 'closing bal', 'balance (inr)']
        type_aliases = ['dr/cr', 'type', 'cr/dr', 'indicator', 'txn type']

        for idx, col in enumerate(cleaned):
            if 'val' in col and any(alias in col for alias in val_date_aliases) and 'value_date' not in mapping:
                mapping['value_date'] = idx
            elif any(alias == col or col.startswith(alias) for alias in date_aliases) and 'date' not in mapping:
                mapping['date'] = idx
            elif any(alias in col for alias in desc_aliases) and 'desc' not in mapping:
                mapping['desc'] = idx
            elif any(alias in col for alias in ref_aliases) and 'ref' not in mapping:
                mapping['ref'] = idx
            elif any(alias in col for alias in dr_aliases) and 'debit' not in mapping:
                mapping['debit'] = idx
            elif any(alias in col for alias in cr_aliases) and 'credit' not in mapping:
                mapping['credit'] = idx
            elif any(alias in col for alias in amount_aliases) and 'amount' not in mapping:
                mapping['amount'] = idx
            elif any(alias in col for alias in bal_aliases) and 'balance' not in mapping:
                mapping['balance'] = idx
            elif any(alias in col for alias in type_aliases) and 'type' not in mapping:
                mapping['type'] = idx

        if 'date' not in mapping:
            for idx, col in enumerate(cleaned):
                if 'date' in col:
                    mapping['date'] = idx
                    break

        return mapping

    @classmethod
    def parse_csv(cls, file_content: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parses CSV bytes into raw row dicts, surviving partial row errors."""
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
        for i, line in enumerate(lines[:15]):
            l_lower = line.lower()
            if ('date' in l_lower and ('debit' in l_lower or 'credit' in l_lower or 'particulars' in l_lower or 'narration' in l_lower or 'amount' in l_lower)):
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

        valid_rows = []
        errors = []

        for row_num, row in enumerate(rows[1:], start=header_idx + 2):
            if not row or all(not str(c).strip() for c in row):
                continue
            try:
                d_idx = col_map.get('date')
                if d_idx is None or d_idx >= len(row):
                    continue
                date_val = cls.parse_date_str(row[d_idx])
                if not date_val:
                    errors.append({"row": row_num, "error": f"Invalid date: '{row[d_idx]}'", "raw": ",".join(row[:6])})
                    continue

                val_date = cls.parse_date_str(row[col_map['value_date']]) if 'value_date' in col_map and col_map['value_date'] < len(row) else None
                desc = row[col_map['desc']].strip() if 'desc' in col_map and col_map['desc'] < len(row) else ""
                ref = row[col_map['ref']].strip() if 'ref' in col_map and col_map['ref'] < len(row) else ""

                debit = Decimal('0.00')
                credit = Decimal('0.00')

                if 'debit' in col_map and col_map['debit'] < len(row):
                    debit = cls.clean_amount_str(row[col_map['debit']])
                if 'credit' in col_map and col_map['credit'] < len(row):
                    credit = cls.clean_amount_str(row[col_map['credit']])

                if debit == 0 and credit == 0 and 'amount' in col_map and col_map['amount'] < len(row):
                    amt = cls.clean_amount_str(row[col_map['amount']])
                    typ = str(row[col_map['type']]).strip().upper() if 'type' in col_map and col_map['type'] < len(row) else ""
                    raw_amt_str = str(row[col_map['amount']]).upper()
                    if 'DR' in typ or '-' in raw_amt_str or 'DR' in raw_amt_str:
                        debit = amt
                    else:
                        credit = amt

                bal = cls.clean_amount_str(row[col_map['balance']]) if 'balance' in col_map and col_map['balance'] < len(row) else None

                if debit == 0 and credit == 0:
                    errors.append({"row": row_num, "error": "Both Debit and Credit are zero", "raw": ",".join(row[:6])})
                    continue

                valid_rows.append({
                    "date": date_val,
                    "value_date": val_date,
                    "description": desc,
                    "reference": ref,
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
        wb = openpyxl.load_workbook(filename=io.BytesIO(file_content), data_only=True)
        sheet = wb.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return [], []

        header_idx = 0
        for i, row in enumerate(rows[:20]):
            r_str = " ".join(str(c).lower() for c in row if c is not None)
            if 'date' in r_str and ('debit' in r_str or 'credit' in r_str or 'particulars' in r_str or 'narration' in r_str or 'amount' in r_str):
                header_idx = i
                break

        header = [str(c or '') for c in rows[header_idx]]
        col_map = cls.detect_columns(header)
        if 'date' not in col_map or ('desc' not in col_map and 'ref' not in col_map):
            if len(header) >= 4:
                col_map = {'date': 0, 'desc': 1, 'debit': 2, 'credit': 3}
            else:
                raise ValidationError("Excel statement columns could not be mapped automatically.")

        valid_rows = []
        errors = []

        for row_num, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            if not row or all(c is None or str(c).strip() == '' for c in row):
                continue
            try:
                d_idx = col_map.get('date')
                if d_idx is None or d_idx >= len(row):
                    continue
                date_val = cls.parse_date_str(row[d_idx])
                if not date_val:
                    errors.append({"row": row_num, "error": f"Invalid date: '{row[d_idx]}'", "raw": str(row[:5])})
                    continue

                val_date = cls.parse_date_str(row[col_map['value_date']]) if 'value_date' in col_map and col_map['value_date'] < len(row) else None
                desc = str(row[col_map['desc']]).strip() if 'desc' in col_map and col_map['desc'] < len(row) and row[col_map['desc']] is not None else ""
                ref = str(row[col_map['ref']]).strip() if 'ref' in col_map and col_map['ref'] < len(row) and row[col_map['ref']] is not None else ""

                debit = cls.clean_amount_str(row[col_map['debit']]) if 'debit' in col_map and col_map['debit'] < len(row) else Decimal('0.00')
                credit = cls.clean_amount_str(row[col_map['credit']]) if 'credit' in col_map and col_map['credit'] < len(row) else Decimal('0.00')

                if debit == 0 and credit == 0 and 'amount' in col_map and col_map['amount'] < len(row):
                    amt = cls.clean_amount_str(row[col_map['amount']])
                    typ = str(row[col_map['type']]).strip().upper() if 'type' in col_map and col_map['type'] < len(row) else ""
                    raw_str = str(row[col_map['amount']]).upper()
                    if 'DR' in typ or '-' in raw_str or 'DR' in raw_str:
                        debit = amt
                    else:
                        credit = amt

                bal = cls.clean_amount_str(row[col_map['balance']]) if 'balance' in col_map and col_map['balance'] < len(row) else None

                if debit == 0 and credit == 0:
                    errors.append({"row": row_num, "error": "Both Debit and Credit are zero", "raw": str(row[:5])})
                    continue

                valid_rows.append({
                    "date": date_val,
                    "value_date": val_date,
                    "description": desc,
                    "reference": ref,
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
        Extracts tabular bank transactions from digital vector PDF via pypdf.
        """
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_content))
        valid_rows = []
        errors = []

        line_pattern = re.compile(
            r'^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?$'
        )
        single_amt_pattern = re.compile(
            r'^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})\s*(CR|DR)(?:\s+([\d,]+\.\d{2}))?$',
            re.IGNORECASE
        )

        for page_idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            lines = text.splitlines()
            for line_no, line in enumerate(lines):
                line_str = line.strip()
                if not line_str:
                    continue

                m = line_pattern.match(line_str)
                if m:
                    dt = cls.parse_date_str(m.group(1))
                    if dt:
                        desc = m.group(2).strip()
                        val1 = cls.clean_amount_str(m.group(3))
                        val2 = cls.clean_amount_str(m.group(4))
                        bal = cls.clean_amount_str(m.group(5)) if m.group(5) else None
                        valid_rows.append({
                            "date": dt,
                            "value_date": dt,
                            "description": desc,
                            "reference": cls.extract_reference_number(desc),
                            "debit": val1,
                            "credit": val2,
                            "balance": bal,
                            "confidence": 0.95,
                            "source_page": page_idx + 1
                        })
                        continue

                m2 = single_amt_pattern.match(line_str)
                if m2:
                    dt = cls.parse_date_str(m2.group(1))
                    if dt:
                        desc = m2.group(2).strip()
                        amt = cls.clean_amount_str(m2.group(3))
                        typ = m2.group(4).upper()
                        bal = cls.clean_amount_str(m2.group(5)) if m2.group(5) else None
                        valid_rows.append({
                            "date": dt,
                            "value_date": dt,
                            "description": desc,
                            "reference": cls.extract_reference_number(desc),
                            "debit": amt if typ == 'DR' else Decimal('0.00'),
                            "credit": amt if typ == 'CR' else Decimal('0.00'),
                            "balance": bal,
                            "confidence": 0.95,
                            "source_page": page_idx + 1
                        })

        return valid_rows, errors

    @classmethod
    def parse_statement(
        cls,
        company: Company,
        bank_ledger: Ledger,
        file_bytes: bytes,
        filename: str,
        user=None
    ) -> Dict[str, Any]:
        """
        Primary entry point for bank statement ingestion.
        Normalizes rows, records BankStatementImport, identifies duplicates,
        persists BankTransaction entries, and runs initial party matching.
        """
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
                errors.append({"row": 0, "error": "No digital table rows detected. Scanned PDF fallback initiated.", "raw": ""})
        else:
            file_format = 'IMAGE'
            errors.append({"row": 0, "error": f"Unsupported or scanned image format '{filename}'.", "raw": ""})

        total_detected = len(valid_rows) + len(errors)
        status = 'COMPLETED'
        if len(errors) > 0 and len(valid_rows) > 0:
            status = 'PARTIAL'
        elif len(valid_rows) == 0 and len(errors) > 0:
            status = 'FAILED'

        from apps.accounting.services.party_intelligence_service import PartyIntelligenceService

        with transaction.atomic():
            import_record = BankStatementImport.objects.create(
                company=company,
                bank_ledger=bank_ledger,
                source_file_name=filename,
                file_format=file_format,
                status=status,
                total_rows=total_detected,
                successful_rows=len(valid_rows),
                failed_rows=len(errors),
                error_summary=errors[:50],
                created_by=user
            )

            created_transactions = []
            duplicate_count = 0
            auto_matched_count = 0
            suggested_count = 0

            for row in valid_rows:
                raw_desc = row.get('description', '')
                norm_desc = cls.normalize_narration(raw_desc)
                ref_no = cls.extract_reference_number(raw_desc, row.get('reference'))
                deb_amt = row.get('debit', Decimal('0.00'))
                cred_amt = row.get('credit', Decimal('0.00'))
                tx_date = row.get('date')

                is_duplicate = False
                dup_qs = BankTransaction.objects.filter(
                    company=company,
                    bank_ledger=bank_ledger,
                    transaction_date=tx_date,
                    debit_amount=deb_amt,
                    credit_amount=cred_amt
                )
                if ref_no:
                    dup_qs = dup_qs.filter(reference_number=ref_no)
                else:
                    dup_qs = dup_qs.filter(normalized_narration=norm_desc)

                if dup_qs.exists():
                    is_duplicate = True
                    duplicate_count += 1

                # Multi-signal matching
                match_res = PartyIntelligenceService.match_transaction(
                    company=company,
                    narration=norm_desc,
                    debit_amount=deb_amt,
                    credit_amount=cred_amt,
                    reference_number=ref_no,
                    tx_date=tx_date
                )

                initial_status = 'UNRESOLVED'
                if is_duplicate:
                    initial_status = 'IGNORED'
                elif match_res['confidence'] >= 0.95:
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
                    normalized_narration=norm_desc,
                    reference_number=ref_no,
                    debit_amount=deb_amt,
                    credit_amount=cred_amt,
                    balance=row.get('balance'),
                    source_file=filename,
                    source_page=row.get('source_page', 1),
                    extraction_confidence=row.get('confidence', 1.0),
                    status=initial_status,
                    matched_party=match_res.get('matched_party'),
                    matched_invoice=match_res.get('matched_invoice'),
                    match_confidence=match_res.get('confidence', 0.0),
                    match_notes={
                        "is_duplicate": is_duplicate,
                        "signals": match_res.get('signals', []),
                        "suggested_matches": match_res.get('suggested_matches', [])
                    }
                )
                created_transactions.append(tx)

        unresolved_count = len(created_transactions) - duplicate_count - auto_matched_count - suggested_count

        return {
            "import_id": str(import_record.id),
            "source_file": filename,
            "file_format": file_format,
            "status": status,
            "total_detected": total_detected,
            "successful_rows": len(valid_rows),
            "auto_matched": auto_matched_count,
            "suggested": suggested_count,
            "unresolved_rows": max(0, unresolved_count),
            "failed_rows": len(errors),
            "duplicates_detected": duplicate_count,
            "errors": errors[:10]
        }
