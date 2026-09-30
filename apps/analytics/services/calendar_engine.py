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


SEASON_DRIVERS: Dict[int, str] = {
    1: "Post-holiday winter resumption; corporate capital budgets unlocked for Q4 execution.",
    2: "Pre-fiscal budget reviews and advance order placements ahead of March rush.",
    3: "Maximum annual billing peak across Indian wholesale mandis; budget exhaustion, tax planning, and depreciation claims before March 31.",
    4: "New financial year kickoff; annual rate contracts take effect with fresh capital allocations.",
    5: "Pre-monsoon manufacturing peak; industrial factories build inventory of belting and spares before rains disrupt supply chains.",
    6: "Standard summer production; initial monsoon arrival in Southern and Eastern states.",
    7: "Peak monsoon slowdown; flooded logistics corridors, mining halts, and outdoor civil works suspension cause the sharpest annual slump.",
    8: "Monsoon continuation; transition towards pre-festive machinery servicing and dealer replenishment.",
    9: "Vishwakarma Puja industrial servicing surge; factories and workshops overhaul plant machinery before the festival quarter.",
    10: "Peak festive production and dispatch; wholesale dealers and retailers stock up for Navratri, Dussehra, and Diwali.",
    11: "Diwali trade week; brief market closures followed by heavy post-festive restock orders.",
    12: "Q3 fiscal closing and calendar year-end target achievement rush."
}


def build_multi_year_seasonal_mapping(df, anchor_date: datetime.date) -> Dict[str, Any]:
    """
    Builds a season-wise sales mapping across all available years in the dataset.
    Identifies in which month of the year sales surged or dropped due to seasonal patterns.
    If multiple years exist, blends them with recency weighting.
    If only current/partial history exists, gracefully maps available months and supplements
    the remaining months with domain B2B industrial benchmarks.
    """
    import pandas as pd
    
    distinct_years = sorted(df.index.year.unique()) if (df is not None and len(df) > 0) else []
    yearly_breakdown: Dict[str, Any] = {}
    empirical_monthly_indices: Dict[int, float] = {}
    historical_sales_matrix: Dict[int, Dict[str, float]] = {m: {} for m in range(1, 13)}
    
    # Month names in Indian Financial Year order (Apr to Mar)
    fy_month_order = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
    month_names = {
        1: ("January", "Jan"), 2: ("February", "Feb"), 3: ("March", "Mar"),
        4: ("April", "Apr"), 5: ("May", "May"), 6: ("June", "Jun"),
        7: ("July", "Jul"), 8: ("August", "Aug"), 9: ("September", "Sep"),
        10: ("October", "Oct"), 11: ("November", "Nov"), 12: ("December", "Dec")
    }

    if df is not None and len(df) > 0 and df['daily_sales'].sum() > 0:
        year_overall_means = {}
        year_month_means: Dict[int, Dict[int, float]] = {}

        for yr in distinct_years:
            yr_df = df[df.index.year == yr]
            yr_total = float(yr_df['daily_sales'].sum())
            yr_days = len(yr_df)
            yr_mean = yr_df['daily_sales'].mean() or 1.0

            if yr_total > 0 and yr_days >= 7:
                year_overall_means[yr] = yr_mean
                year_month_means[yr] = {}
                m_details = {}

                for m in range(1, 13):
                    m_df = yr_df[yr_df.index.month == m]
                    m_total = float(m_df['daily_sales'].sum()) if len(m_df) > 0 else 0.0
                    m_active_days = int((m_df['daily_sales'] > 0).sum()) if len(m_df) > 0 else 0
                    m_mean = float(m_df['daily_sales'].mean()) if len(m_df) > 0 else 0.0

                    if len(m_df) >= 3 and m_total > 0:
                        year_month_means[yr][m] = m_mean
                        historical_sales_matrix[m][str(yr)] = round(m_total, 2)
                        
                        # Calculate surge percentage relative to that year's daily mean
                        surge_pct = round(((m_mean - yr_mean) / yr_mean) * 100.0, 1)
                        m_status = "SURGE" if surge_pct >= 15.0 else ("LOW" if surge_pct <= -15.0 else "STEADY")

                        m_details[str(m)] = {
                            "month": m,
                            "month_name": month_names[m][0],
                            "total_sales": round(m_total, 2),
                            "daily_mean": round(m_mean, 2),
                            "surge_pct": surge_pct,
                            "status": m_status,
                            "active_days": m_active_days
                        }

                yearly_breakdown[str(yr)] = {
                    "year": int(yr),
                    "total_sales": round(yr_total, 2),
                    "daily_mean": round(yr_mean, 2),
                    "recorded_days": yr_days,
                    "months": m_details
                }

        # Multi-year cross-year aggregation with recency weighting
        usable_years = sorted(year_overall_means.keys())
        for m in range(1, 13):
            weighted_sum = 0.0
            weight_total = 0.0
            for rank, yr in enumerate(usable_years):
                if m in year_month_means.get(yr, {}):
                    yr_mean = year_overall_means[yr]
                    if yr_mean > 0:
                        idx = year_month_means[yr][m] / yr_mean
                        weight = 1.0 + 0.6 * rank  # Later years get more weight
                        weighted_sum += idx * weight
                        weight_total += weight
            if weight_total > 0:
                empirical_monthly_indices[m] = round(min(max(weighted_sum / weight_total, 0.45), 2.20), 3)

    # Build the complete 12-month season-wise mapping calendar (April to March)
    season_calendar = []
    surge_months_list = []
    slump_months_list = []

    for rank, m in enumerate(fy_month_order, start=1):
        domain_mult = B2B_SEASONAL_INDICES.get(m, 1.0)
        has_empirical = m in empirical_monthly_indices
        
        if has_empirical and len(yearly_breakdown) >= 1:
            emp_mult = empirical_monthly_indices[m]
            # Blend empirical data with structural domain index
            effective_mult = round(0.65 * emp_mult + 0.35 * domain_mult, 3)
        else:
            effective_mult = domain_mult

        pct_diff = round((effective_mult - 1.0) * 100.0, 1)
        pct_label = f"+{pct_diff}%" if pct_diff > 0 else f"{pct_diff}%"

        if effective_mult >= 1.15:
            m_status = "SURGE"
            surge_months_list.append(f"{month_names[m][0]} ({pct_label})")
        elif effective_mult <= 0.85:
            m_status = "LOW"
            slump_months_list.append(f"{month_names[m][0]} ({pct_label})")
        else:
            m_status = "STEADY"

        season_calendar.append({
            "month_num": m,
            "fy_order": rank,
            "month_name": month_names[m][0],
            "short_name": month_names[m][1],
            "multiplier": effective_mult,
            "status": m_status,
            "surge_pct_label": pct_label,
            "surge_pct_value": pct_diff,
            "season_name": SEASON_DESCRIPTIONS.get(m, "Standard Operations"),
            "driver": SEASON_DRIVERS.get(m, "Regular wholesale business flow."),
            "historical_sales_by_year": historical_sales_matrix.get(m, {}),
            "is_empirical": has_empirical
        })

    has_multi_year = len(yearly_breakdown) >= 2
    years_list = sorted([int(y) for y in yearly_breakdown.keys()])

    if has_multi_year:
        data_note = f"Season-wise demand curves synthesized from {len(years_list)} historical years ({', '.join(str(y) for y in years_list)}) with recency-weighted multi-year blending."
    elif len(years_list) == 1:
        data_note = f"Season-wise demand calibrated from available {years_list[0]} historical transactions and enriched with Indian B2B wholesale seasonal benchmarks."
    else:
        data_note = "Season-wise demand mapped using Indian B2B wholesale industrial benchmark calendar."

    return {
        "has_multi_year": has_multi_year,
        "years_analyzed": years_list,
        "yearly_breakdown": yearly_breakdown,
        "season_calendar": season_calendar,
        "top_surge_months": surge_months_list,
        "top_slump_months": slump_months_list,
        "empirical_indices": empirical_monthly_indices,
        "data_status_description": data_note
    }


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

