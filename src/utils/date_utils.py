"""Date utility helpers."""

from datetime import date, timedelta


def week_range(year: int, week: int) -> tuple[date, date]:
    """Return (Monday, Sunday) for a given ISO year and week number."""
    jan4 = date(year, 1, 4)
    start_of_week1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = start_of_week1 + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def days_in_year(year: int) -> int:
    """Return the number of days in a given year."""
    return 366 if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0) else 365


def first_day_of_year(year: int) -> date:
    return date(year, 1, 1)


def last_day_of_year(year: int) -> date:
    return date(year, 12, 31)
