import datetime
from typing import Dict, Any, Optional, List

# Indian Commercial & Gazetted Trading Calendar (2026 - 2027)
# Specifically tuned for Indian wholesale mandis, distributors, and industrial trade centers
INDIAN_TRADING_CALENDAR: Dict[str, Dict[str, Any]] = {
    # ---------------- 2026 ----------------
    "2026-01-26": {
        "name": "Republic Day",
        "impact": "CLOSED",
        "multiplier": 0.05,
        "type": "NATIONAL_HOLIDAY",
        "description": "National Gazetted Holiday - commercial markets & transport closed"
    },
    "2026-03-02": {
        "name": "Pre-Holi Restocking",
        "impact": "SURGE",
        "multiplier": 1.25,
        "type": "PRE_FESTIVAL_SURGE",
        "description": "Pre-festival inventory buffer build"
    },
    "2026-03-03": {
        "name": "Pre-Holi Trade Rush",
        "impact": "SURGE",
        "multiplier": 1.35,
        "type": "PRE_FESTIVAL_SURGE",
        "description": "Heavy commercial dispatch before market holidays"
    },
    "2026-03-04": {
        "name": "Holi (Dhulandi)",
        "impact": "CLOSED",
        "multiplier": 0.05,
        "type": "MAJOR_FESTIVAL",
        "description": "Major festival - commercial mandis closed"
    },
    "2026-03-20": {
        "name": "Eid al-Fitr",
        "impact": "LOW",
        "multiplier": 0.20,
        "type": "COMMERCIAL_HOLIDAY",
        "description": "Commercial trading holiday - partial market activity"
    },
    "2026-03-25": {
        "name": "Fiscal Year-End Closing Rush",
        "impact": "SURGE",
        "multiplier": 1.45,
        "type": "FISCAL_YEAR_END",
        "description": "Annual budget clearing & GST input tax credit utilization"
    },
    "2026-03-26": {
        "name": "Fiscal Year-End Closing Rush",
        "impact": "SURGE",
        "multiplier": 1.50,
        "type": "FISCAL_YEAR_END",
        "description": "Annual budget clearing & distributor target achievement"
    },
    "2026-03-27": {
        "name": "Fiscal Year-End Closing Rush",
        "impact": "SURGE",
        "multiplier": 1.55,
        "type": "FISCAL_YEAR_END",
        "description": "Heavy fiscal closing invoicing"
    },
    "2026-03-28": {
        "name": "Fiscal Year-End Closing Rush",
        "impact": "SURGE",
        "multiplier": 1.55,
        "type": "FISCAL_YEAR_END",
        "description": "Heavy fiscal closing invoicing"
    },
    "2026-03-30": {
        "name": "Fiscal Year-End Final Billing",
        "impact": "SURGE",
        "multiplier": 1.65,
        "type": "FISCAL_YEAR_END",
        "description": "Peak billing blitz to close FY books"
    },
    "2026-03-31": {
        "name": "Fiscal Year-End Final Invoicing",
        "impact": "SURGE",
        "multiplier": 1.70,
        "type": "FISCAL_YEAR_END",
        "description": "Last day of financial year - maximum billing records"
    },
    "2026-04-14": {
        "name": "Dr. Ambedkar Jayanti / Baisakhi",
        "impact": "LOW",
        "multiplier": 0.35,
        "type": "REGIONAL_HOLIDAY",
        "description": "Public holiday - reduced market operations"
    },
    "2026-05-01": {
        "name": "May Day / Labour Day",
        "impact": "LOW",
        "multiplier": 0.30,
        "type": "COMMERCIAL_HOLIDAY",
        "description": "Labour Day - factory loading and transport halted"
    },
    "2026-05-27": {
        "name": "Eid al-Adha (Bakrid)",
        "impact": "LOW",
        "multiplier": 0.20,
        "type": "COMMERCIAL_HOLIDAY",
        "description": "Commercial trading holiday - partial mandi operation"
    },
    "2026-06-26": {
        "name": "Muharram",
        "impact": "LOW",
        "multiplier": 0.25,
        "type": "COMMERCIAL_HOLIDAY",
        "description": "Commercial holiday"
    },
    "2026-08-15": {
        "name": "Independence Day",
        "impact": "CLOSED",
        "multiplier": 0.05,
        "type": "NATIONAL_HOLIDAY",
        "description": "National Gazetted Holiday - commercial markets closed"
    },
    "2026-08-28": {
        "name": "Raksha Bandhan",
        "impact": "LOW",
        "multiplier": 0.40,
        "type": "FESTIVAL",
        "description": "Festive observance - early market closing"
    },
    "2026-09-04": {
        "name": "Janmashtami",
        "impact": "LOW",
        "multiplier": 0.40,
        "type": "FESTIVAL",
        "description": "Festive observance - light trading"
    },
    "2026-09-17": {
        "name": "Vishwakarma Puja",
        "impact": "CLOSED",
        "multiplier": 0.15,
        "type": "INDUSTRIAL_FESTIVAL",
        "description": "Machinery & factory worship - industrial dispatch halted"
    },

    # --- Q3-Q4 2026 Peak Horizon ---
    "2026-10-02": {
        "name": "Mahatma Gandhi Jayanti",
        "impact": "CLOSED",
        "multiplier": 0.05,
        "type": "NATIONAL_HOLIDAY",
        "description": "National Gazetted Holiday - wholesale markets strictly closed"
    },
    "2026-10-17": {
        "name": "Pre-Dussehra Commercial Restocking",
        "impact": "SURGE",
        "multiplier": 1.30,
        "type": "PRE_FESTIVAL_SURGE",
        "description": "Pre-Dussehra commercial order rush"
    },
    "2026-10-18": {
        "name": "Maha Ashtami / Navratri Rush",
        "impact": "SURGE",
        "multiplier": 1.25,
        "type": "PRE_FESTIVAL_SURGE",
        "description": "Festive market ramp-up"
    },
    "2026-10-19": {
        "name": "Maha Navami",
        "impact": "LOW",
        "multiplier": 0.30,
        "type": "FESTIVAL",
        "description": "Puja observance - partial commercial operations"
    },
    "2026-10-20": {
        "name": "Vijayadashami / Dussehra",
        "impact": "CLOSED",
        "multiplier": 0.05,
        "type": "MAJOR_FESTIVAL",
        "description": "Major festival - trading mandis & warehouses closed"
    },
    "2026-11-04": {
        "name": "Pre-Diwali Factory Stocking",
        "impact": "SURGE",
        "multiplier": 1.35,
        "type": "PRE_FESTIVAL_SURGE",
        "description": "Industrial buyers stock up before multi-day Diwali shutdown"
    },
    "2026-11-05": {
        "name": "Pre-Diwali Commercial Dispatch",
        "impact": "SURGE",
        "multiplier": 1.45,
        "type": "PRE_FESTIVAL_SURGE",
        "description": "Peak dispatch before transport halts"
    },
    "2026-11-06": {
        "name": "Dhanteras (Peak Procurement)",
        "impact": "SURGE",
        "multiplier": 1.55,
        "type": "COMMERCIAL_PEAK",
        "description": "Auspicious commercial buying for industrial tools & materials"
    },
    "2026-11-07": {
        "name": "Chhoti Diwali / Roop Chaudas",
        "impact": "LOW",
        "multiplier": 0.35,
        "type": "FESTIVAL",
        "description": "Early market closing"
    },
    "2026-11-08": {
        "name": "Deepavali / Lakshmi Puja",
        "impact": "CLOSED",
        "multiplier": 0.10,
        "type": "MAJOR_FESTIVAL",
        "description": "Diwali - Muhurat trading sessions only, bulk dispatch closed"
    },
    "2026-11-09": {
        "name": "Govardhan Puja / Annakut",
        "impact": "CLOSED",
        "multiplier": 0.05,
        "type": "MAJOR_FESTIVAL",
        "description": "Mandis & trade associations completely closed"
    },
    "2026-11-10": {
        "name": "Bhai Dooj",
        "impact": "CLOSED",
        "multiplier": 0.10,
        "type": "MAJOR_FESTIVAL",
        "description": "Commercial holidays continue"
    },
    "2026-11-14": {
        "name": "Pre-Chhath Market Preparation",
        "impact": "SURGE",
        "multiplier": 1.20,
        "type": "PRE_FESTIVAL_SURGE",
        "description": "Pre-festival procurement rush"
    },
    "2026-11-15": {
        "name": "Chhath Puja (Evening Arghya)",
        "impact": "LOW",
        "multiplier": 0.20,
        "type": "REGIONAL_HOLIDAY",
        "description": "Major regional festival - partial operations"
    },
    "2026-11-16": {
        "name": "Chhath Puja (Morning Arghya)",
        "impact": "LOW",
        "multiplier": 0.25,
        "type": "REGIONAL_HOLIDAY",
        "description": "Festive observance - morning operations halted"
    },
    "2026-11-24": {
        "name": "Guru Nanak Jayanti",
        "impact": "LOW",
        "multiplier": 0.25,
        "type": "COMMERCIAL_HOLIDAY",
        "description": "Commercial holiday"
    },
    "2026-12-25": {
        "name": "Christmas Day",
        "impact": "LOW",
        "multiplier": 0.35,
        "type": "COMMERCIAL_HOLIDAY",
        "description": "Commercial holiday"
    },
    "2026-12-30": {
        "name": "Q3 Target Closing Rush",
        "impact": "SURGE",
        "multiplier": 1.35,
        "type": "QUARTER_END_RUSH",
        "description": "Quarterly sales target push"
    },
    "2026-12-31": {
        "name": "Calendar Year-End Reconciliation",
        "impact": "SURGE",
        "multiplier": 1.40,
        "type": "QUARTER_END_RUSH",
        "description": "Year-end commercial settlements"
    },

    # ---------------- 2027 ----------------
    "2027-01-01": {
        "name": "New Year's Day",
        "impact": "LOW",
        "multiplier": 0.40,
        "type": "COMMERCIAL_HOLIDAY",
        "description": "Commercial holiday - light dispatch"
    },
    "2027-01-14": {
        "name": "Makar Sankranti / Pongal",
        "impact": "LOW",
        "multiplier": 0.30,
        "type": "FESTIVAL",
        "description": "Harvest festival - partial operations"
    },
    "2027-01-26": {
        "name": "Republic Day",
        "impact": "CLOSED",
        "multiplier": 0.05,
        "type": "NATIONAL_HOLIDAY",
        "description": "National Gazetted Holiday - commercial markets closed"
    },
    "2027-02-15": {
        "name": "Maha Shivratri",
        "impact": "LOW",
        "multiplier": 0.40,
        "type": "FESTIVAL",
        "description": "Festive observance"
    },
    "2027-03-21": {
        "name": "Pre-Holi Trade Surge",
        "impact": "SURGE",
        "multiplier": 1.30,
        "type": "PRE_FESTIVAL_SURGE",
        "description": "Pre-Holi commercial order surge"
    },
    "2027-03-22": {
        "name": "Holi (Dhulandi)",
        "impact": "CLOSED",
        "multiplier": 0.05,
        "type": "MAJOR_FESTIVAL",
        "description": "Major festival - mandis closed"
    },
    "2027-03-25": {
        "name": "Fiscal Year-End Closing Rush",
        "impact": "SURGE",
        "multiplier": 1.45,
        "type": "FISCAL_YEAR_END",
        "description": "Fiscal year-end closing billing rush"
    },
    "2027-03-26": {
        "name": "Fiscal Year-End Closing Rush",
        "impact": "SURGE",
        "multiplier": 1.50,
        "type": "FISCAL_YEAR_END",
        "description": "Fiscal year-end closing billing rush"
    },
    "2027-03-27": {
        "name": "Fiscal Year-End Closing Rush",
        "impact": "SURGE",
        "multiplier": 1.55,
        "type": "FISCAL_YEAR_END",
        "description": "Fiscal year-end closing billing rush"
    },
    "2027-03-29": {
        "name": "Fiscal Year-End Final Invoicing",
        "impact": "SURGE",
        "multiplier": 1.65,
        "type": "FISCAL_YEAR_END",
        "description": "Fiscal year-end billing rush"
    },
    "2027-03-30": {
        "name": "Fiscal Year-End Final Invoicing",
        "impact": "SURGE",
        "multiplier": 1.65,
        "type": "FISCAL_YEAR_END",
        "description": "Fiscal year-end billing rush"
    },
    "2027-03-31": {
        "name": "Fiscal Year-End Final Closing",
        "impact": "SURGE",
        "multiplier": 1.70,
        "type": "FISCAL_YEAR_END",
        "description": "Final day of financial year"
    }
}

# Indian B2B Industrial Wholesale Monthly Structural Seasonality
# Models real-world Indian commercial business seasons:
# - Monsoon slump (July-August): mining, transport, construction slows down
# - Post-monsoon agro & festive manufacturing ramp (September-November): peak demand
# - Financial year-end blitz (February-March): budget exhaustion, tax planning, target closing
B2B_SEASONAL_INDICES: Dict[int, float] = {
    1: 1.05,  # Jan: Post-holiday recovery, steady procurement
    2: 1.15,  # Feb: Pre-fiscal ramp, corporate procurement approvals
    3: 1.50,  # Mar: FISCAL YEAR END CLOSING (Peak billing, budget exhaustion, annual targets)
    4: 1.10,  # Apr: New FY kickoff, annual maintenance contracts
    5: 1.12,  # May: Pre-monsoon factory production peak
    6: 1.00,  # Jun: Normal steady state
    7: 0.78,  # Jul: MONSOON SLUMP (Heavy rains, transport slow, construction/mining halt)
    8: 0.82,  # Aug: Monsoon continuation, transition to festive prep
    9: 1.25,  # Sep: POST-MONSOON RECOVERY & PRE-FESTIVE SURGE (Agro & factory maintenance)
    10: 1.35, # Oct: PEAK FESTIVE PRODUCTION & DISPATCH (Navratri, Dussehra, Diwali stocking)
    11: 1.10, # Nov: Diwali market closures followed by restock replenishment
    12: 1.08, # Dec: Q3 fiscal & calendar year-end procurement
}

SEASON_DESCRIPTIONS: Dict[int, str] = {
    1: "Post-Holiday Steady Procurement",
    2: "Pre-Fiscal Budget Invoicing",
    3: "Fiscal Year-End Billing Blitz (Peak Annual Rush)",
    4: "Financial Year Kickoff & Annual Contracts",
    5: "Pre-Monsoon Peak Manufacturing",
    6: "Standard Summer Operations",
    7: "Monsoon Slump (Transport Slowdown & Civil Works Halt)",
    8: "Monsoon Recovery & Festive Planning",
    9: "Post-Monsoon Industrial Surge & Machine Maintenance",
    10: "Peak Festive Manufacturing & Wholesale Dispatch",
    11: "Diwali Trade Week & Restocking Replenishment",
    12: "Q3 Fiscal Closing & Year-End Procurement"
}


def get_calendar_event(date_obj: datetime.date) -> Optional[Dict[str, Any]]:
    """Returns trading calendar event metadata if this date is a holiday or surge date."""
    d_str = date_obj.strftime('%Y-%m-%d')
    return INDIAN_TRADING_CALENDAR.get(d_str)


def get_seasonal_factor(month: int, has_yoy_history: bool = False, empirical_indices: Optional[Dict[int, float]] = None) -> float:
    """
    Returns monthly seasonal multiplier.
    If historical past-year data exists, blends 60% empirical with 40% domain structural.
    Otherwise uses calibrated B2B domain index.
    """
    domain_mult = B2B_SEASONAL_INDICES.get(month, 1.0)
    if has_yoy_history and empirical_indices and month in empirical_indices:
        emp_mult = empirical_indices[month]
        return round(0.60 * emp_mult + 0.40 * domain_mult, 3)
    return domain_mult


def get_holidays_in_horizon(start_date: datetime.date, days: int) -> List[Dict[str, Any]]:
    """Lists all trading calendar events falling within the forecast window."""
    events = []
    for i in range(1, days + 1):
        target_d = start_date + datetime.timedelta(days=i)
        ev = get_calendar_event(target_d)
        if ev:
            events.append({
                "date": target_d.strftime('%Y-%m-%d'),
                "name": ev["name"],
                "impact": ev["impact"],
                "type": ev["type"],
                "multiplier": ev["multiplier"],
                "description": ev["description"]
            })
    return events
