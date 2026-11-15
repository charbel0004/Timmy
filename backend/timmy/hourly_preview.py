"""Deterministic, nonauthoritative HOURS source diagnostics, preserving coordinates."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from .column_mappings import propose_sheet, mapped_documents
from .fixed_hours_policy import HourlyShift, monthly_candidates, HoursPolicyError
from .source_dates import source_date


def preview_hours(documents, project_code, *, snapshot=None):
    shifts, issues = [], []
    for file, record in documents:
        for index, sheet in enumerate(record.sheets):
            selection = propose_sheet(file, sheet, index)
            if selection['kind'] != 'hours':
                continue
            required = {'project_code','activity_code','staff_id','role','work_date','clock_in','clock_out'}
            if not required <= selection['columns'].keys() or selection['conflicts']:
                issues.append(f'{file.id} / sheet {index+1}: HOURS_MAPPING_REVIEW_REQUIRED')
                continue
            for row in sheet['rows'][1:]:
                values = row['values']
                def value(key):
                    column = selection['columns'][key]
                    return str(values[column] or '').strip() if column < len(values) else ''
                ref = f'{file.id}:{index}:{row["row"]}'
                try:
                    day = source_date(value('work_date'))
                    if day is None:
                        raise ValueError('DATE_MAPPING_REQUIRED')
                    def clock(field):
                        raw = value(field)
                        parsed = datetime.fromisoformat(raw) if ' ' in raw or 'T' in raw else datetime.combine(day, time.fromisoformat(raw))
                        if parsed.tzinfo is not None:
                            raise ValueError('EXPLICIT_TIMEZONE_REVIEW_REQUIRED')
                        zone = ZoneInfo('Asia/Beirut')
                        if parsed.replace(tzinfo=zone, fold=0).utcoffset() != parsed.replace(tzinfo=zone, fold=1).utcoffset():
                            raise ValueError('AMBIGUOUS_LOCAL_TIME')
                        return parsed.replace(tzinfo=zone)
                    start, end = clock('clock_in'), clock('clock_out')
                    if end <= start and ':' in value('clock_out') and '-' not in value('clock_out'):
                        end += timedelta(days=1)
                    shifts.append(HourlyShift(value('staff_id'), value('project_code'), value('activity_code'),
                                              value('role'), start, end, ref))
                except (ValueError, HoursPolicyError):
                    issues.append(f'{ref}: INVALID_OR_AMBIGUOUS_SHIFT; review original date and clock evidence')
    lines = ['### HOURS source preview',
             'Provisional deterministic arithmetic only. These are unverified source claims, not payment entitlements or an approved payment request.']
    if snapshot is not None:
        snapshot['hourly_candidates']=[]
        snapshot['hourly_shifts']=[dict(staff_id=s.staff_id,project_code=s.project_code,activity_code=s.activity_code,role=s.role,start=s.start.isoformat(),end=s.end.isoformat(),source_id=s.source_id) for s in shifts]
    if shifts:
        for candidate in monthly_candidates(shifts):
            if candidate.project_code != project_code:
                continue
            if snapshot is not None:
                from dataclasses import asdict
                values=asdict(candidate);values['amount_usd']=str(candidate.amount_usd) if candidate.amount_usd is not None else None
                snapshot['hourly_candidates'].append(values)
            lines.append(f'- {candidate.staff_id} / {candidate.year}-{candidate.month:02}: '
                         f'{candidate.actual_unique_minutes} unique minutes; {candidate.rounded_minutes} rounded minutes; '
                         f'candidate USD {candidate.amount_usd if candidate.amount_usd is not None else "Unavailable"}; '
                         f'issues: {", ".join(candidate.blockers) or "none in arithmetic"}.')
    else:
        lines.append('No interpretable hourly claims; review the hourly column mapping.')
    if snapshot is not None:
        snapshot['hourly_parse_issues']=issues
    lines.extend(f'- {issue}' for issue in issues)
    lines.append('Next: confirm source mapping; verify staff, planning and reports before authoritative eligibility, exact batch approval and export.')
    return '\n'.join(lines)
