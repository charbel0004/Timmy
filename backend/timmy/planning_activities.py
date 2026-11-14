"""Planning is the only application source of new activity identities.

Registration establishes identity/provenance, not planning approval or payability.
The caller must hold a write transaction; ambiguous/corrected plans fail closed.
"""
import copy
import re
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select, insert, update

from .audit import audit
from .models import activities, projects, activity_planning_sources, ExternalReportVersion, PlanningCodeContract


def valid_activity_code(contract, code):
    """Bounded source-approved format; no arbitrary or nested regex execution."""
    if contract is None or not code or len(code)>88 or any(ord(c)<33 for c in code):return False
    pattern=contract.code_pattern
    token=r'(?:[A-Za-z0-9_/-]|\[(?:A-Z|a-z|0-9|A-Za-z|A-Za-z0-9)\])(?:\{[1-9][0-9]?(?:,[1-9][0-9]?)?\})?'
    if not pattern or len(pattern)>128 or re.fullmatch(f'(?:{token})+',pattern) is None:
        raise HTTPException(409,'PLANNING_CODE_CONTRACT_INVALID: use a reviewed bounded source format')
    try:return re.fullmatch(pattern,code) is not None
    except re.error:raise HTTPException(409,'PLANNING_CODE_CONTRACT_INVALID') from None


def registry(db, project_ids):
    rows=db.execute(select(activities,projects.c.project_code).join(projects).where(
        activities.c.project_id.in_(project_ids),activities.c.activity_code.is_not(None),activities.c.code_authority=='source_supplied')).mappings()
    return {(r['project_id'],r['project_code'],r['activity_code']):dict(r) for r in rows}


def register_planning(db, principal, documents, sheets, mapping_id):
    selections={(s['file_id'],s['sheet_index']):s for s in sheets}
    entries=[]
    project_rows={}
    for file,record in documents:
        principal.require('projects:manage')
        principal.require('timesheets.view',file.project_id)
        project=db.execute(select(projects).where(projects.c.id==file.project_id)).mappings().one()
        project_rows[file.project_id]=project
        if project['status']!='active' or not project['project_code']:
            raise HTTPException(409,'Planning registration requires an active project with a code prefix')
        contract=db.get(PlanningCodeContract,file.project_id)
        for index,sheet in enumerate(record.sheets):
            if selections[file.id,index]['kind']!='planning':continue
            headers=sheet['rows'][0]['values']
            for source in sheet['rows'][1:]:
                row=dict(zip(headers,(str(v or '').strip() for v in source['values'])))
                label=f"Planning file {file.id}, row {source['row']}"
                if row.get('project_code')!=project['project_code']:
                    raise HTTPException(422,f'{label}: PROJECT_CODE_MISMATCH; expected {project["project_code"]}')
                try:
                    start=date.fromisoformat(row['approved_start_date']);end=date.fromisoformat(row['approved_end_date'])
                    if len(row['approved_start_date'])!=10 or len(row['approved_end_date'])!=10 or start>end:raise ValueError()
                except (ValueError,KeyError):
                    raise HTTPException(422,f'{label}: INVALID_PLANNING_WINDOW; use ISO dates and start <= end') from None
                code=row.get('activity_code','')
                if not code:
                    raise HTTPException(422,f'{label}: MISSING_ACTIVITY_CODE (ACTIVITY-CODE-001); obtain it from the authoritative planning spreadsheet; Timmy never generates codes')
                if contract is None:
                    raise HTTPException(409,'PLANNING_CODE_CONTRACT_REQUIRED: approved source format is not configured for this project')
                if not valid_activity_code(contract,code):
                    raise HTTPException(422,f'{label}: ACTIVITY_CODE_FORMAT does not match the approved source contract')
                owner=db.execute(select(activities.c.project_id,activities.c.code_authority).where(activities.c.activity_code==code)).first()
                if owner and owner.project_id!=file.project_id:
                    raise HTTPException(409,'ACTIVITY_CODE_PROJECT_CONFLICT: source code already belongs to another project')
                if owner and owner.code_authority!='source_supplied':
                    raise HTTPException(409,'LEGACY_ACTIVITY_CODE_REVIEW_REQUIRED: historical identity must be reconciled separately')
                name=row.get('activity_name','')
                if len(name)>160:
                    raise HTTPException(422,f'{label}: ACTIVITY_NAME_TOO_LONG (maximum 160 characters)')
                entries.append(dict(file=file,sheet=index,row=source['row'],code=code,name=name,
                                    start=start.isoformat(),end=end.isoformat(),contract=contract.version))
    seen_codes=set()
    for entry in entries:
        if entry['code'] in seen_codes:
            raise HTTPException(409,'DUPLICATE_ACTIVITY_CODE: source rows repeat an activity code; explicit review is required')
        seen_codes.add(entry['code'])
    assigned={};receipts=[]
    for entry in entries:
        file=entry['file'];pid=file.project_id
        source_key=(pid,file.sha256,entry['sheet'],entry['row'])
        link=db.execute(select(activity_planning_sources.c.activity_id).where(
            activity_planning_sources.c.project_id==pid,activity_planning_sources.c.source_sha256==file.sha256,
            activity_planning_sources.c.sheet_index==entry['sheet'],activity_planning_sources.c.source_row==entry['row'])).scalar()
        existing=db.execute(select(activities).where(activities.c.id==link)).mappings().one() if link else None
        code=entry['code']
        if existing:
            if code and code!=existing['activity_code']:
                raise HTTPException(409,'Planning source already identifies a different permanent activity code')
            code=existing['activity_code']
        elif code:
            existing=db.execute(select(activities).where(activities.c.project_id==pid,activities.c.activity_code==code)).mappings().one_or_none()
        if existing:
            if (existing['planned_start']!=entry['start'] or existing['planned_end']!=entry['end']
                    or (entry['name'] and entry['name']!=existing['name'])):
                raise HTTPException(409,'PLANNING_ACTIVITY_CONFLICT: code already has different name or dates; explicit review is required')
            identifier=existing['id']
        else:
            identifier=db.execute(insert(activities).values(project_id=pid,name=entry['name'] or code,
                activity_code=code,planned_start=entry['start'],planned_end=entry['end'],code_authority='source_supplied',planning_contract_version=entry['contract'])).inserted_primary_key[0]
            audit(db,'planning_activity_registered',principal.user.id,resource_type='activity',resource_id=str(identifier),outcome='identity_registered_not_approved')
        if not link:
            db.execute(insert(activity_planning_sources).values(activity_id=identifier,project_id=pid,file_id=file.id,
                source_sha256=file.sha256,sheet_index=entry['sheet'],source_row=entry['row'],mapping_id=selections[file.id,entry['sheet']].get('verified_format_ref') or mapping_id))
        # Binding existing exact-code evidence does not alter its authority/cutoff.
        db.execute(update(ExternalReportVersion).where(ExternalReportVersion.project_id==pid,
            ExternalReportVersion.activity_code==code,ExternalReportVersion.activity_id.is_(None)).values(activity_id=identifier))
        assigned[file.id,entry['sheet'],entry['row']]=code
        receipts.append(dict(activity_id=identifier,activity_code=code,project_id=pid,source_file_id=file.id,
                             sheet_index=entry['sheet'],source_row=entry['row']))
    normalized=[]
    for file,record in documents:
        copied=copy.deepcopy(record.sheets)
        for index,sheet in enumerate(copied):
            if selections[file.id,index]['kind']!='planning':continue
            headers=sheet['rows'][0]['values']
            if 'activity_code' not in headers:headers.append('activity_code')
            column=headers.index('activity_code')
            for source in sheet['rows'][1:]:
                while len(source['values'])<=column:source['values'].append(None)
                source['values'][column]=assigned[file.id,index,source['row']]
        normalized.append((file,SimpleNamespace(sheets=copied,row_count=record.row_count)))
    return normalized,receipts
