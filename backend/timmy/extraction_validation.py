import re
from datetime import date
from decimal import Decimal
from typing import Literal

from .schemas import Extraction

FieldName = Literal["volunteer", "activity", "date", "hours", "sessions"]
COLUMN_NAMES: dict[FieldName, set[str]] = {
    "volunteer": {"volunteer", "volunteer name", "name", "اسم المتطوع", "المتطوع", "الاسم"},
    "activity": {"activity", "activity name", "النشاط", "اسم النشاط"},
    "date": {"date", "activity date", "التاريخ", "تاريخ النشاط"},
    "hours": {"hours", "total hours", "عدد الساعات", "الساعات"},
    "sessions": {"sessions", "session count", "عدد الجلسات", "الجلسات"},
}
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")


def normalize_date(value: str) -> str:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value).isoformat()

    match = re.fullmatch(r"([0-9]{1,2})([/.-])([0-9]{1,2})\2([0-9]{4})", value)
    if match is None:
        raise ValueError("unsupported_date")
    first, _, second, year = match.groups()
    day, month = int(first), int(second)
    if 1 <= day <= 12 and 1 <= month <= 12 and day != month:
        raise ValueError("ambiguous_date")
    if month > 12:
        day, month = month, day
    return date(int(year), month, day).isoformat()


def check_normalization(name: FieldName, source: str, proposed: str) -> str | None:
    if name in {"volunteer", "activity"}:
        return None if proposed == source.strip() else "normalization_mismatch"
    value = source.strip().translate(DIGITS)
    if name == "date":
        try:
            expected = normalize_date(value)
        except ValueError as error:
            return str(error) if str(error) in {"ambiguous_date", "unsupported_date"} else "invalid_date"
        return None if proposed == expected else "normalization_mismatch"

    pattern = r"[0-9]+" if name == "sessions" else r"[0-9]+(?:\.[0-9]+)?"
    if not re.fullmatch(pattern, value) or not re.fullmatch(pattern, proposed):
        return "invalid_quantity"
    return None if Decimal(value) == Decimal(proposed) else "normalization_mismatch"


def review_issues(extracted: Extraction, row: dict[str, str]) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {}
    for name, aliases in COLUMN_NAMES.items():
        field = getattr(extracted, name)
        recognized = [
            column for column, cell in row.items()
            if " ".join(column.casefold().split()) in aliases and cell.strip()
        ]
        field_issues: list[str] = []
        column, cell = field.source_column, field.source_text
        if column is not None or cell is not None:
            if column not in row or row[column] != cell:
                field_issues.append("source_mismatch")
        if len(recognized) > 1:
            field_issues.append("ambiguous_column")
        if field.status == "clear":
            if column not in recognized:
                field_issues.append("unverified_column")
            if not cell or not cell.strip() or not field.normalized_value:
                field_issues.append("incomplete_candidate")
            elif problem := check_normalization(name, cell, field.normalized_value):
                field_issues.append(problem)
        else:
            if field.normalized_value is not None:
                field_issues.append("unexpected_normalized_value")
            if field.status == "uncertain":
                field_issues.append("uncertain")
            elif name in {"volunteer", "activity", "date"} or recognized or (cell and cell.strip()):
                field_issues.append("missing")
        if field_issues:
            issues[name] = field_issues

    if all(getattr(extracted, name).status != "clear" or name in issues for name in ("hours", "sessions")):
        issues["duration"] = ["missing_verified_quantity"]
    return issues
