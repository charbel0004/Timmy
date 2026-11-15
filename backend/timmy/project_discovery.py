"""Read-only, coordinator-global project discovery from untrusted spreadsheets.

This module never creates activity codes, accepts payments, certifies external
reports, or invokes a workflow. Project identity is resolved per SOURCE ROW,
not from a browser-selected project. Unknown/conflicting evidence is flagged.
"""
from collections import Counter
from sqlalchemy import select

from .column_mappings import ALIASES, normalize_header
from .models import activities, projects

MAX_ISSUE_REFERENCES = 20


def _column(headers, field):
    aliases = ALIASES.get(field, set())
    columns = [index for index, header in enumerate(headers)
               if normalize_header(header) in aliases]
    return columns[0] if len(columns) == 1 else None


def discover_projects(db, principal, documents):
    """Return a safe summary, never leaked row contents or unverified identity."""
    permitted = sorted(project_id for project_id, permissions in principal.project_permissions.items()
                       if 'timesheets.view' in permissions and 'projects:read' in permissions)
    project_rows = db.execute(select(
        projects.c.id, projects.c.project_code, projects.c.name, projects.c.policy_family
    ).where(projects.c.id.in_(permitted), projects.c.status == 'active')).all()
    by_id = {p.id: p for p in project_rows}
    code_map = {p.project_code: p.id for p in project_rows if p.project_code}
    names = {}
    for p in project_rows:
        names.setdefault(normalize_header(p.name), set()).add(p.id)
    activity_map = dict(db.execute(select(activities.c.activity_code, activities.c.project_id)
        .where(activities.c.project_id.in_(by_id), activities.c.code_authority == 'source_supplied',
               activities.c.activity_code.is_not(None))).all())

    counts = Counter()
    issue_codes = Counter()
    examples = []
    references = 0
    total = 0
    for file, record in documents:
        for sheet_index, sheet in enumerate(record.sheets):
            rows = sheet.get('rows', [])
            if not rows:
                continue
            headers = rows[0]['values']
            indices = {key: _column(headers, key) for key in ('project_code','project_name','activity_code')}
            if all(index is None for index in indices.values()):
                references += max(0, len(rows) - 1)  # E.g. coordinator-global staff directory.
                continue
            for source in rows[1:]:
                total += 1
                values = source['values']
                def value(field):
                    col = indices[field]
                    return str(values[col] or '').strip() if col is not None and col < len(values) else ''
                candidates = set()
                issues = set()
                project_code = value('project_code')
                project_name = value('project_name')
                activity_code = value('activity_code')
                if project_code:
                    pid = code_map.get(project_code)
                    if pid is None:
                        issues.add('UNKNOWN_PROJECT_CODE')
                    else:
                        candidates.add(pid)
                if project_name:
                    matches = names.get(normalize_header(project_name), set())
                    if len(matches) != 1:
                        issues.add('UNKNOWN_OR_AMBIGUOUS_PROJECT_NAME')
                    else:
                        candidates.update(matches)
                if activity_code and activity_code in activity_map:
                    candidates.add(activity_map[activity_code])
                # A historical file.project_id is a storage/permission association,
                # NOT evidence that every row belongs to that project. One workbook
                # can legitimately contain records for multiple projects.
                if len(candidates) > 1:
                    issues.add('CONFLICTING_PROJECT_EVIDENCE')
                if not candidates:
                    issues.add('PROJECT_IDENTITY_UNRESOLVED')
                if project_code and indices['project_code'] is None:
                    issues.add('UNRECOGNIZED_PROJECT_COLUMN')
                if issues:
                    for issue in issues:
                        issue_codes[issue] += 1
                    if len(examples) < MAX_ISSUE_REFERENCES:
                        examples.append({'file_id': file.id, 'sheet': sheet_index + 1,
                                         'row': source['row'], 'issues': sorted(issues)})
                else:
                    counts[next(iter(candidates))] += 1

    return {
        'files': len(documents),
        'data_rows_with_project_fields': total,
        'global_reference_rows': references,
        'projects': [{'project_id': p.id, 'project_code': p.project_code,
                      'project_name': p.name, 'policy_family': p.policy_family,
                      'matched_rows': counts[p.id]}
                     for p in sorted(project_rows, key=lambda p: p.id)],
        'issue_counts': dict(sorted(issue_codes.items())),
        'issue_references': examples,
    }


def render_project_discovery(result, *, processing_requested=False, workflow_receipts=False):
    lines = [
        f"Global spreadsheet intake: {result['files']} file(s), "
        f"{result['data_rows_with_project_fields']} project-bearing source rows, "
        f"{result['global_reference_rows']} global-reference rows.",
        "Project identities are matched from source project codes/names or previously approved "
        "activity identities, not from a chat-level project selector.",
    ]
    for row in result['projects']:
        lines.append(f"- {row['project_name']} ({row['project_code'] or 'no approved code'}): "
                     f"{row['matched_rows']} unambiguous source rows; "
                     f"fixed {row['policy_family'] or 'unassigned'} policy family.")
    if result['issue_counts']:
        lines.append("Project mapping issues (review required):")
        for issue, count in result['issue_counts'].items():
            lines.append(f"- {issue}: {count} affected source rows.")
        for item in result['issue_references']:
            lines.append(f"  Evidence: file {item['file_id']}, sheet {item['sheet']}, "
                         f"row {item['row']}: {', '.join(item['issues'])}.")
    else:
        lines.append("No project-identity conflicts identified in the recognized columns.")
    lines.append("Source-code matching is structural only. File uploads are not planning "
                 "approval, staff verification, external-report validation or payment authority.")
    if workflow_receipts:
        lines.append("Separate guarded per-project workflow receipts follow. "
                     "Only intake/routing is verified; planning, reports, staff and money "
                     "remain outside the current multi-project authority adapters.")
    elif processing_requested:
        lines.append("MULTI_PROJECT_EXECUTION_ADAPTER_REQUIRED: The current workflow runner "
                     "still requires one verified project per run. No financial or planning "
                     "writes were attempted. Multi-project source splitting and separate "
                     "audited project runs must be integrated before processing.")
    else:
        lines.append("No per-project validation or financial workflow was executed. "
                     "Request processing when the project-routing adapter is available.")
    return '\n'.join(lines)
