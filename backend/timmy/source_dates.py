"""Strict date candidates; raw imported values are never rewritten."""
import re
from datetime import date, datetime


def source_date(value):
    if isinstance(value, datetime):
        return value.date() if value.time().isoformat() == '00:00:00' else None
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}[ T]00:00:00(?:\.0+)?', text):
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None  # Nonmidnight/timezone-bearing evidence needs an explicit mapping.
