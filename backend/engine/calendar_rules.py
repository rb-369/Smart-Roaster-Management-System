"""
Demand Calendar Operating Day and Minimum Staffing Resolver.
PURE DETERMINISTIC LOGIC - NO FASTAPI OR DATABASE CALLS.
"""
from datetime import date
from typing import Dict, Any


def is_operating_day(calendar_type: str, date_obj: date, is_ph: bool) -> bool:
    """
    Determine if a brand-process operates on a specific date.
    
    Weekday convention: 0=Monday through 6=Sunday.
    - 365_DAYS: Always operating (365 days a year).
    - DAILY_EXCEPT_PH: Operates every day except public holidays.
    - MON_SAT_EXCEPT_PH: Operates Monday through Saturday, closed on Sundays and public holidays.
    """
    is_sunday = (date_obj.weekday() == 6)
    
    if calendar_type == "365_DAYS":
        return True
    elif calendar_type == "DAILY_EXCEPT_PH":
        return not is_ph
    elif calendar_type == "MON_SAT_EXCEPT_PH":
        return (not is_sunday) and (not is_ph)
    else:
        # Default fallback
        return not is_ph


def get_required_staffing(
    calendar_type: str,
    date_obj: date,
    is_ph: bool,
    base_min_staffing: int,
    day_min_staffing_overrides: Dict[str, int] | None = None
) -> int:
    """
    Returns required employee headcount for the brand-process on date_obj.
    If the brand-process does not operate on date_obj, required headcount is 0.
    Otherwise returns day_min_staffing_overrides.get(str(weekday), base_min_staffing).
    """
    if not is_operating_day(calendar_type, date_obj, is_ph):
        return 0
    
    overrides = day_min_staffing_overrides or {}
    weekday_str = str(date_obj.weekday())
    return int(overrides.get(weekday_str, base_min_staffing))
