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
