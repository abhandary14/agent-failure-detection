"""Shared input-validation helpers used by every tool."""

from datetime import date, datetime


def parse_date(value: str) -> date | None:
    """Parse an ISO 'YYYY-MM-DD' date string. Returns None if malformed."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def validate_date_range(start_date: str, end_date: str) -> str | None:
    """Return an error message if the date range is invalid, else None."""
    start = parse_date(start_date)
    end = parse_date(end_date)
    if start is None:
        return f"Invalid start_date: '{start_date}'. Expected format YYYY-MM-DD."
    if end is None:
        return f"Invalid end_date: '{end_date}'. Expected format YYYY-MM-DD."
    if start > end:
        return f"start_date ({start_date}) is after end_date ({end_date})."
    return None