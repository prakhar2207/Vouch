"""
Canonical Return Period Normalization and Range Resolution Service.
Provides strict parsing, validation, financial year derivation, and range expansion
for Indian GST return periods (GSTR-1, GSTR-2B, GSTR-3B).
"""
import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple, Union, Any, Dict
from rest_framework.exceptions import ValidationError

MONTH_NAMES = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April',
    5: 'May', 6: 'June', 7: 'July', 8: 'August',
    9: 'September', 10: 'October', 11: 'November', 12: 'December'
}

MIN_SUPPORTED_YEAR = 2017  # GST introduced in India July 2017
MAX_SUPPORTED_YEAR = 2040


@dataclass(frozen=True)
class StatementPeriodResolution:
    invoice_period: str                  # e.g. "042026" (MMYYYY)
    financial_year: str                  # e.g. "2026-27"
    recipient_filing_frequency: str      # 'MONTHLY', 'QRMP', 'UNKNOWN'
    expected_statement_period: Optional[str] # e.g. "062026" for QRMP Apr-Jun, "042026" for monthly, None if UNKNOWN
    statement_generation_period: Optional[str] # e.g. "062026"
    actual_statement_period: Optional[str] # Matched period from available statements
    period_resolution_status: str        # 'RESOLVED_MONTHLY', 'RESOLVED_QRMP', 'REVIEW_REQUIRED'
    evidence_source: str                 # 'REGISTRATION_FREQUENCY', 'FILING_FREQUENCY_PARAM', 'FILING_FREQUENCY_UNKNOWN'
    is_qrmp_quarter_end: bool            # True if expected period is quarter end
    quarter_label: str                   # 'Q1 (Apr–Jun)', 'Q2 (Jul–Sep)', 'Q3 (Oct–Dec)', 'Q4 (Jan–Mar)'
    reason: str                          # Explicit audit rationale for resolution


@dataclass(frozen=True)
class PeriodInfo:
    normalized_period: str      # e.g. "042026" (MMYYYY)
    month: str                  # e.g. "04"
    month_int: int              # e.g. 4
    year: str                   # e.g. "2026"
    year_int: int               # e.g. 2026
    financial_year: str         # e.g. "2026-27"
    period_label: str           # e.g. "April 2026"
    original_input: str         # e.g. "01042026" or "2026-04"

    def __str__(self) -> str:
        return self.normalized_period

    @property
    def start_date(self) -> date:
        return date(self.year_int, self.month_int, 1)

    @property
    def end_date(self) -> date:
        if self.month_int == 12:
            return date(self.year_int, 12, 31)
        next_month_start = date(self.year_int, self.month_int + 1, 1)
        from datetime import timedelta
        return next_month_start - timedelta(days=1)


class GSTPeriodService:
    """
    Centralized GST return period normalizer and validator.
    Strictly prohibits silent fallbacks to arbitrary months upon invalid input.
    """

    @classmethod
    def compute_financial_year(cls, year: int, month: int) -> str:
        """
        Derives Indian financial year string (e.g. month=4, year=2026 -> '2026-27').
        Months 1, 2, 3 belong to (year-1)-(year % 100).
        """
        if month >= 4:
            next_short = str(year + 1)[2:]
            return f"{year}-{next_short}"
        else:
            prev_year = year - 1
            cur_short = str(year)[2:]
            return f"{prev_year}-{cur_short}"

    @classmethod
    def parse_return_period(cls, raw_input: Any) -> PeriodInfo:
        """
        Parses and validates a single GST return period string.
        Supported formats:
        - MMYYYY (e.g. '042026')
        - DDMMYYYY (e.g. '01042026')
        - YYYY-MM (e.g. '2026-04')
        - MM-YYYY (e.g. '04-2026')
        - YYYYMM (e.g. '202604')
        - Slashed variants (e.g. '01/04/2026', '2026/04', '04/2026')
        """
        if raw_input is None:
            raise ValidationError("Return period is required and cannot be null.")

        s = str(raw_input).strip()
        if not s:
            raise ValidationError("Return period cannot be empty.")

        month_int: Optional[int] = None
        year_int: Optional[int] = None

        # Check for separated strings (with '-' or '/')
        if '-' in s or '/' in s:
            sep = '-' if '-' in s else '/'
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if len(parts) == 2:
                # Could be YYYY-MM or MM-YYYY
                p0, p1 = parts[0], parts[1]
                if not (p0.isdigit() and p1.isdigit()):
                    raise ValidationError(f"Invalid non-numeric return period format: '{s}'")
                if len(p0) == 4 and len(p1) <= 2:
                    # YYYY-MM
                    year_int = int(p0)
                    month_int = int(p1)
                elif len(p0) <= 2 and len(p1) == 4:
                    # MM-YYYY
                    month_int = int(p0)
                    year_int = int(p1)
                else:
                    raise ValidationError(f"Invalid return period format: '{s}'. Expected YYYY-MM or MM-YYYY.")
            elif len(parts) == 3:
                # Could be DD-MM-YYYY or YYYY-MM-DD
                p0, p1, p2 = parts[0], parts[1], parts[2]
                if not (p0.isdigit() and p1.isdigit() and p2.isdigit()):
                    raise ValidationError(f"Invalid non-numeric date format: '{s}'")
                if len(p0) <= 2 and len(p1) <= 2 and len(p2) == 4:
                    # DD-MM-YYYY
                    day_int = int(p0)
                    month_int = int(p1)
                    year_int = int(p2)
                    cls._validate_calendar_date(year_int, month_int, day_int, s)
                elif len(p0) == 4 and len(p1) <= 2 and len(p2) <= 2:
                    # YYYY-MM-DD
                    year_int = int(p0)
                    month_int = int(p1)
                    day_int = int(p2)
                    cls._validate_calendar_date(year_int, month_int, day_int, s)
                else:
                    raise ValidationError(f"Invalid 3-part date format: '{s}'. Expected DD-MM-YYYY or YYYY-MM-DD.")
            else:
                raise ValidationError(f"Invalid return period structure: '{s}'")
        else:
            # Unseparated strings
            if not s.isdigit():
                raise ValidationError(f"Return period '{s}' contains invalid non-numeric characters.")

            if len(s) == 6:
                # Could be MMYYYY (e.g. '042026') or YYYYMM (e.g. '202604')
                prefix4 = int(s[:4])
                suffix4 = int(s[2:])
                if prefix4 >= MIN_SUPPORTED_YEAR:
                    # YYYYMM
                    year_int = prefix4
                    month_int = int(s[4:])
                elif suffix4 >= MIN_SUPPORTED_YEAR:
                    # MMYYYY
                    month_int = int(s[:2])
                    year_int = suffix4
                else:
                    raise ValidationError(f"Year in period '{s}' is outside supported range ({MIN_SUPPORTED_YEAR}-{MAX_SUPPORTED_YEAR}).")
            elif len(s) == 8:
                # DDMMYYYY or YYYYMMDD
                prefix4 = int(s[:4])
                suffix4 = int(s[4:])
                if suffix4 >= MIN_SUPPORTED_YEAR:
                    # DDMMYYYY (e.g. '01042026')
                    day_int = int(s[:2])
                    month_int = int(s[2:4])
                    year_int = suffix4
                    cls._validate_calendar_date(year_int, month_int, day_int, s)
                elif prefix4 >= MIN_SUPPORTED_YEAR:
                    # YYYYMMDD
                    year_int = prefix4
                    month_int = int(s[4:6])
                    day_int = int(s[6:])
                    cls._validate_calendar_date(year_int, month_int, day_int, s)
                else:
                    raise ValidationError(f"Year in date '{s}' is outside supported range ({MIN_SUPPORTED_YEAR}-{MAX_SUPPORTED_YEAR}).")
            else:
                raise ValidationError(
                    f"Invalid return period length ({len(s)} digits) in '{s}'. Expected 6 digits (MMYYYY) or 8 digits (DDMMYYYY)."
                )

        # Validate month bounds
        if month_int is None or month_int < 1 or month_int > 12:
            raise ValidationError(f"Invalid month '{month_int}' in return period '{s}'. Month must be between 01 and 12.")

        # Validate year bounds
        if year_int is None or year_int < MIN_SUPPORTED_YEAR or year_int > MAX_SUPPORTED_YEAR:
            raise ValidationError(
                f"Invalid year '{year_int}' in return period '{s}'. Must be between {MIN_SUPPORTED_YEAR} and {MAX_SUPPORTED_YEAR}."
            )

        norm_month = str(month_int).zfill(2)
        norm_year = str(year_int)
        normalized_period = f"{norm_month}{norm_year}"
        fy = cls.compute_financial_year(year_int, month_int)
        label = f"{MONTH_NAMES[month_int]} {year_int}"

        return PeriodInfo(
            normalized_period=normalized_period,
            month=norm_month,
            month_int=month_int,
            year=norm_year,
            year_int=year_int,
            financial_year=fy,
            period_label=label,
            original_input=s
        )

    @classmethod
    def _validate_calendar_date(cls, year: int, month: int, day: int, raw_string: str) -> None:
        """Validates that a day/month/year constitutes a valid Gregorian calendar date."""
        try:
            date(year, month, day)
        except ValueError as err:
            raise ValidationError(f"Invalid calendar date '{raw_string}': {err}")

    @classmethod
    def generate_period_range(cls, from_period: Any, to_period: Any) -> List[str]:
        """Convenience helper returning list of normalized MMYYYY string periods."""
        return [p.normalized_period for p in cls.resolve_period_range(from_period=from_period, to_period=to_period)]

    @classmethod
    def resolve_period_range(
        cls,
        from_period: Optional[Any] = None,
        to_period: Optional[Any] = None,
        periods: Optional[List[Any]] = None
    ) -> List[PeriodInfo]:
        """
        Resolves and orders a list of return periods.
        If `periods` list is provided, validates each entry.
        If `from_period` and `to_period` are provided, generates all intermediate months inclusive.
        Rejects reversed ranges (from_period > to_period).
        """
        if periods and isinstance(periods, (list, tuple)):
            if not periods:
                raise ValidationError("Periods list cannot be empty.")
            results = []
            seen = set()
            for p in periods:
                parsed = cls.parse_return_period(p)
                if parsed.normalized_period not in seen:
                    seen.add(parsed.normalized_period)
                    results.append(parsed)
            # Sort chronologically by (year_int, month_int)
            results.sort(key=lambda x: (x.year_int, x.month_int))
            return results

        if from_period and to_period:
            parsed_from = cls.parse_return_period(from_period)
            parsed_to = cls.parse_return_period(to_period)

            # Check for reversed range
            if (parsed_from.year_int > parsed_to.year_int) or (
                parsed_from.year_int == parsed_to.year_int and parsed_from.month_int > parsed_to.month_int
            ):
                raise ValidationError(
                    f"Reversed period range: from_period '{parsed_from.period_label}' cannot be later than to_period '{parsed_to.period_label}'."
                )

            # Generate monthly sequence
            results = []
            cur_y = parsed_from.year_int
            cur_m = parsed_from.month_int
            end_y = parsed_to.year_int
            end_m = parsed_to.month_int

            while (cur_y < end_y) or (cur_y == end_y and cur_m <= end_m):
                m_str = str(cur_m).zfill(2)
                y_str = str(cur_y)
                p_norm = f"{m_str}{y_str}"
                fy = cls.compute_financial_year(cur_y, cur_m)
                label = f"{MONTH_NAMES[cur_m]} {cur_y}"
                results.append(PeriodInfo(
                    normalized_period=p_norm,
                    month=m_str,
                    month_int=cur_m,
                    year=y_str,
                    year_int=cur_y,
                    financial_year=fy,
                    period_label=label,
                    original_input=p_norm
                ))
                cur_m += 1
                if cur_m > 12:
                    cur_m = 1
                    cur_y += 1

            return results

        raise ValidationError("Either 'periods' list or both 'from_period' and 'to_period' must be specified.")

    @classmethod
    def get_quarter_info(cls, month_int: int, year_int: int) -> Tuple[int, int, str]:
        """
        Returns (quarter_num, quarter_end_month, quarter_label) for Indian Financial Year.
        Q1: Apr-Jun (end: month 6, year)
        Q2: Jul-Sep (end: month 9, year)
        Q3: Oct-Dec (end: month 12, year)
        Q4: Jan-Mar (end: month 3, year)
        """
        if month_int in [4, 5, 6]:
            return 1, 6, "Q1 (Apr–Jun)"
        elif month_int in [7, 8, 9]:
            return 2, 9, "Q2 (Jul–Sep)"
        elif month_int in [10, 11, 12]:
            return 3, 12, "Q3 (Oct–Dec)"
        else:  # 1, 2, 3
            return 4, 3, "Q4 (Jan–Mar)"

    @classmethod
    def is_period_qrmp_applicable(cls, period_input: Any) -> Tuple[bool, str]:
        """
        Checks whether a return period is an applicable GSTR-2B statement period under QRMP.
        In QRMP, GSTR-2B is generated quarterly (June, September, December, March).
        M1 and M2 months do NOT have GSTR-2B statements.
        Returns: (is_applicable, reason)
        """
        parsed = cls.parse_return_period(period_input)
        m = parsed.month_int
        if m in [6, 9, 12, 3]:
            _, _, q_label = cls.get_quarter_info(m, parsed.year_int)
            return True, f"Applicable quarter-end statement period ({q_label})."
        else:
            _, end_m, q_label = cls.get_quarter_info(m, parsed.year_int)
            end_period = f"{str(end_m).zfill(2)}{parsed.year}"
            return False, f"Month {m} is an interim month of {q_label}. Under QRMP, official GSTR-2B is generated on quarter-end ({end_period})."

    @classmethod
    def parse_financial_year(cls, fy_input: Any) -> Tuple[str, date, date]:
        """
        Validates an Indian Financial Year string (e.g. '2025-26' or '2026-27')
        and returns (normalized_fy, start_date, end_date).
        """
        if not fy_input:
            raise ValidationError("Financial year cannot be empty.")
        s = str(fy_input).strip()
        m = re.match(r'^(20\d{2})-(\d{2})$', s)
        if not m:
            raise ValidationError(f"Invalid financial year '{s}'. Expected YYYY-YY (e.g. '2025-26').")
        start_y = int(m.group(1))
        end_short = int(m.group(2))
        expected_short = (start_y + 1) % 100
        if end_short != expected_short:
            raise ValidationError(f"Invalid sequential financial year '{s}'. Expected '{start_y}-{str(expected_short).zfill(2)}'.")
        if start_y < MIN_SUPPORTED_YEAR or start_y > MAX_SUPPORTED_YEAR:
            raise ValidationError(f"Financial year '{s}' is outside supported GST range.")
        return s, date(start_y, 4, 1), date(start_y + 1, 3, 31)

    @classmethod
    def resolve_gstr2b_statement_period(
        cls,
        invoice_date: Union[date, str],
        recipient_registration: Optional[Any] = None,
        filing_frequency: Optional[str] = None,
        statement_metadata: Optional[Any] = None,
        verification_source: Optional[str] = None,
        verified_at: Optional[Any] = None,
        verified_by: Optional[Any] = None
    ) -> StatementPeriodResolution:
        """
        Central Return-Period Resolver with QRMP Intelligence (P0 / Round 2.4.2).
        Maps an invoice date to its statutory GSTR-2B statement period using VERIFIED configuration only.
        - Enforces canonical provenance: Registration-based frequency is usable ONLY after verification.
        - An explicit filing_frequency argument MUST NOT bypass registration verification.
        - Direct model field assignment without verified metadata resolves to UNKNOWN.
        - For verified QRMP recipients: Maps M1/M2/M3 of a quarter to quarter-end statement (06/09/12/03YYYY).
        - For verified MONTHLY recipients: Maps invoice month to the corresponding monthly statement (MMYYYY).
        - For UNKNOWN filing frequency: Returns REVIEW_REQUIRED with expected_statement_period=None.
        """
        if isinstance(invoice_date, str):
            from datetime import datetime
            raw_s = invoice_date.strip()
            try:
                dt = datetime.strptime(raw_s[:10], "%Y-%m-%d").date()
            except Exception:
                try:
                    dt = datetime.strptime(raw_s[:10], "%d-%m-%Y").date()
                except Exception:
                    p = cls.parse_return_period(raw_s)
                    dt = p.start_date
        elif isinstance(invoice_date, date):
            dt = invoice_date
        else:
            raise ValidationError(f"Invalid invoice_date for statement period resolution: '{invoice_date}'")

        m = dt.month
        y = dt.year
        inv_period = f"{str(m).zfill(2)}{y}"
        fy = cls.compute_financial_year(y, m)
        _, q_end_m, q_label = cls.get_quarter_info(m, y)
        qrmp_stmt_period = f"{str(q_end_m).zfill(2)}{y}"

        # Determine verified filing frequency strictly from verified registration provenance or verified context (P0 / Round 2.4.2)
        # Registration-based frequency is usable ONLY after canonical verification validation.
        # An explicit filing_frequency argument MUST NOT bypass registration verification.
        freq = 'UNKNOWN'
        evidence = 'FILING_FREQUENCY_UNKNOWN'

        if recipient_registration is not None:
            # Check canonical verification interface on registration (Round 2.4.3 P1)
            verified_f = 'UNKNOWN'
            if hasattr(recipient_registration, 'get_verified_filing_frequency'):
                verified_f = recipient_registration.get_verified_filing_frequency()
            elif hasattr(recipient_registration, 'is_frequency_verified') and recipient_registration.is_frequency_verified():
                verified_f = (getattr(recipient_registration, 'filing_frequency', None) or '').strip().upper()

            if verified_f in ['MONTHLY', 'QRMP']:
                freq = verified_f
                evidence = 'REGISTRATION_FREQUENCY_VERIFIED'
            else:
                # Unverified registration cannot be bypassed by an explicit filing_frequency argument
                freq = 'UNKNOWN'
                evidence = 'REGISTRATION_FREQUENCY_UNVERIFIED'
        elif filing_frequency:
            # When registration is not provided, explicit frequency argument is accepted ONLY if accompanied
            # by verified provenance (allowed verification_source and verified_at timestamp)
            cand_freq = (filing_frequency or '').strip().upper()
            cand_source = (verification_source or '').strip().upper()
            if (cand_freq in ['MONTHLY', 'QRMP'] and
                verified_at is not None and
                cand_source in ['GST_PORTAL_API', 'RETURN_STATUS_API', 'USER_MANUAL']):
                if cand_source != 'USER_MANUAL' or verified_by:
                    freq = cand_freq
                    evidence = 'VERIFIED_PARAM_PROVENANCE'
                else:
                    freq = 'UNKNOWN'
                    evidence = 'UNVERIFIED_PARAM_MISSING_USER'
            else:
                freq = 'UNKNOWN'
                evidence = 'UNVERIFIED_PARAM_PROVENANCE'

        available = set()
        if statement_metadata is not None:
            if isinstance(statement_metadata, (set, list, tuple)):
                available = set(statement_metadata)
            elif isinstance(statement_metadata, dict):
                available = set(statement_metadata.keys())

        # Strict no-guessing behavior when filing frequency is UNKNOWN
        if freq == 'UNKNOWN':
            return StatementPeriodResolution(
                invoice_period=inv_period,
                financial_year=fy,
                recipient_filing_frequency='UNKNOWN',
                expected_statement_period=None,
                statement_generation_period=None,
                actual_statement_period=None,
                period_resolution_status='REVIEW_REQUIRED',
                evidence_source=evidence,
                is_qrmp_quarter_end=False,
                quarter_label=q_label,
                reason="Recipient filing frequency is UNKNOWN; statement period cannot be assumed without verified MONTHLY or QRMP registration configuration."
            )

        if freq == 'QRMP':
            expected_period = qrmp_stmt_period
            res_status = 'RESOLVED_QRMP'
            is_qrmp_qe = True
            # Quarter-end statement covers all months in the quarter; interim IFF reflection is evidence-based only
            if expected_period in available:
                actual_period = expected_period
                reason = f"Verified QRMP recipient ({q_label}): mapped invoice period {inv_period} to processed quarter-end statement {expected_period}."
            elif inv_period != expected_period and inv_period in available:
                actual_period = inv_period
                reason = f"Verified QRMP recipient ({q_label}): quarter-end {expected_period} pending; interim statement {inv_period} available."
            else:
                actual_period = None
                reason = f"Verified QRMP recipient ({q_label}): mapped invoice period {inv_period} to expected quarter-end statement {expected_period}."
        else:
            expected_period = inv_period
            res_status = 'RESOLVED_MONTHLY'
            is_qrmp_qe = (m in [6, 9, 12, 3])
            actual_period = expected_period if expected_period in available else None
            reason = f"Verified MONTHLY recipient: mapped invoice period {inv_period} to monthly statement {expected_period}."

        return StatementPeriodResolution(
            invoice_period=inv_period,
            financial_year=fy,
            recipient_filing_frequency=freq,
            expected_statement_period=expected_period,
            statement_generation_period=expected_period,
            actual_statement_period=actual_period,
            period_resolution_status=res_status,
            evidence_source=evidence,
            is_qrmp_quarter_end=is_qrmp_qe,
            quarter_label=q_label,
            reason=reason
        )
