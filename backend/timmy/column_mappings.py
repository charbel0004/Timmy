"""Deterministic header proposals; candidates acquire no authority until reviewed."""
from types import SimpleNamespace

SCHEMA_VERSION = 1
REQUIRED = {
    'hours': {'project_code','activity_code','staff_id','role','work_date','clock_in','clock_out','timesheet_submitted_date'},
    'reports': {'project_code','activity_code','report_id','report_version','submitted_at','validation_status','validated_at','evidence_ref'},
    'claims': {'project_code','activity_code','staff_id','role','session_number','work_date','timesheet_submitted_date'},
    'planning': {'project_code','activity_code','approved_start_date','approved_end_date'},
    'directory': {'staff_id','status'},
    'projects': {'project_code','project_name'},
}
OPTIONAL = {'planning': {'activity_name','approval_status'}}
# Columns that identify a document type on their own; the completeness ratios are
# only a fallback for sheets whose required headers happen to describe one type.
DISTINCTIVE = {
    'hours': {'clock_in','clock_out'}, 'reports': {'report_id','validated_at','validation_status'},
    'claims': {'session_number','work_date','role'}, 'planning': {'approved_start_date','approved_end_date'},
    'projects': {'project_name'}, 'directory': set(),
}
ALIASES = {
    'project_code': {'project code'}, 'project_name': {'project name'},
    'activity_code': {'activity code','رمز النشاط'},
    'activity_name': {'activity name','اسم النشاط'},
    'staff_id': {'staff id','volunteer id','staff identifier','رقم المتطوع','معرف الموظف'},
    'role': {'role','الدور'}, 'session_number': {'session number','session','رقم الجلسة'},
    'work_date': {'work date','activity date','date','تاريخ العمل','التاريخ'},
    'timesheet_submitted_date': {'timesheet submitted date','submission date','تاريخ التقديم'},
    'approved_start_date': {'approved start date'}, 'approved_end_date': {'approved end date'},
    'status': {'status'}, 'approval_status': {'approval status','planning status'},
    'clock_in': {'clock in','ساعة الدخول'}, 'clock_out': {'clock out','ساعة الخروج'},
    'report_id': {'external report reference','report id'}, 'report_version': {'version','report version'},
    'submitted_at': {'submitted at'}, 'validation_status': {'validation status'},
    'validated_at': {'validated at'}, 'evidence_ref': {'source evidence','evidence ref'},
}


def normalize_header(value):
    return ' '.join(str(value or '').casefold().replace('_',' ').split())


def propose_sheet(file, sheet, index):
    rows = sheet['rows']
    headers = [str(v or '') for v in rows[0]['values']] if rows else []
    fields = {}
    conflicts = []
    for column, header in enumerate(headers):
        for canonical, aliases in ALIASES.items():
            if normalize_header(header) in aliases:
                if canonical in fields:
                    conflicts.append(canonical)
                else:
                    fields[canonical] = column
    scores = {kind: len(required & fields.keys()) / len(required) for kind,required in REQUIRED.items()}
    # Distinctive columns beat completeness ratios: a partial timesheet must
    # not become a directory merely because staff_id is one of its two fields.
    basis = 'distinctive_headers'
    distinctive = next((kind for kind, markers in DISTINCTIVE.items()
                        if markers & fields.keys()), None)
    if distinctive:
        kind = distinctive
    elif fields:
        complete = [kind for kind, value in scores.items() if value == 1.0]
        kind = max(scores, key=scores.get)
        basis = 'complete_exact_headers' if complete == [kind] else 'partial_coverage'
    else:
        kind, basis = 'unsupported', 'no_recognized_headers'
    if kind != 'unsupported':
        fields = {k:v for k,v in fields.items() if k in REQUIRED[kind] | OPTIONAL.get(kind,set())}
    # High confidence means: the document type was identified by its own
    # signature (or an exact, unique required-header fit), every required
    # column was recognized exactly once, and no field matched twice. Only then
    # may the mapping be applied without asking a human.
    confident = bool(kind in REQUIRED and not conflicts
                     and REQUIRED[kind] <= fields.keys()
                     and basis in {'distinctive_headers', 'complete_exact_headers'})
    return {'file_id':file.id, 'filename':file.original_filename, 'sheet_index':index,
            'sheet_name':sheet['name'], 'kind':kind, 'header_row':rows[0]['row'] if rows else None,
            'headers':headers, 'columns':fields, 'conflicts':conflicts,
            'confidence': 'high' if confident else 'review_required', 'confidence_basis': basis,
            'source_rows':len(rows)}


def mapping_errors(sheets):
    errors=[]
    for sheet in sheets:
        label=f"{sheet['filename']} / sheet {sheet['sheet_index']+1}"
        if sheet['kind'] not in REQUIRED:
            errors.append(f'{label}: unsupported schema; select a supported document category and its source columns.')
            continue
        required=REQUIRED[sheet['kind']]
        missing=required-sheet['columns'].keys()
        if missing:
            errors.append(f"{label}: missing required field(s): {', '.join(sorted(missing))}.")
        if sheet.get('conflicts'):
            errors.append(f"{label}: ambiguous duplicate field(s): {', '.join(sheet['conflicts'])}.")
        if set(sheet['columns'])-required-OPTIONAL.get(sheet['kind'],set()):
            errors.append(f'{label}: unexpected canonical fields for this document category.')
        if sheet['kind']=='planning':
            status_columns=[i for i,h in enumerate(sheet['headers']) if normalize_header(h) in ALIASES['approval_status']]
            if len(status_columns)==1 and sheet['columns'].get('approval_status')!=status_columns[0]:
                errors.append(f'{label}: retain the recognized planning approval-status column; it cannot be discarded or reassigned.')
        columns=list(sheet['columns'].values())
        if (len(columns)!=len(set(columns)) or any(type(c) is not int or c<0 or c>=len(sheet['headers']) for c in columns)):
            errors.append(f'{label}: source column indices must be distinct and within the proposed header.')
    return errors


def mapped_documents(documents, sheets):
    """Return a view for validation; original parsed/source evidence is never changed."""
    selections={(s['file_id'],s['sheet_index']):s for s in sheets}
    result=[]
    for file,record in documents:
        normalized=[]
        for index,sheet in enumerate(record.sheets):
            selection=selections[file.id,index]
            ordered=list(sorted(selection['columns']))
            source=sheet['rows']
            rows=[{'row':source[0]['row'],'values':ordered}]
            from .source_dates import source_date
            for row in source[1:]:
                rows.append({'row':row['row'],'values':[row['values'][selection['columns'][field]]
                             if selection['columns'][field]<len(row['values']) else None for field in ordered]})
            for row in rows[1:]:
                for i, field in enumerate(ordered):
                    if field in {'work_date','timesheet_submitted_date','approved_start_date','approved_end_date'}:
                        candidate = source_date(row['values'][i])
                        if candidate is not None:
                            row['values'][i] = candidate.isoformat()
            normalized.append({'name':sheet['name'],'rows':rows,'source_sheet_index':index})
        result.append((file,SimpleNamespace(sheets=normalized,row_count=record.row_count)))
    return result


def reuse_approved_formats(db, actor_id, project_id, sheets):
    """Reuse exact reviewed headers in this actor/project; ambiguity requires review."""
    import copy
    import json
    from sqlalchemy import select
    from .models import MappingProposal
    confirmed=db.scalars(select(MappingProposal).where(MappingProposal.actor_id==actor_id,
        MappingProposal.project_id==project_id,MappingProposal.status=='confirmed')
        .order_by(MappingProposal.created_at.desc()).limit(100)).all()
    reused=[]
    for sheet in sheets:
        matches={}
        for previous in confirmed:
            for accepted in previous.sheets:
                if accepted['headers']==sheet['headers']:
                    signature=json.dumps([accepted['kind'],accepted['columns']],sort_keys=True)
                    matches.setdefault(signature,(previous.id,accepted))
        if len(matches)!=1:return []
        origin,accepted=next(iter(matches.values()))
        candidate=copy.deepcopy(sheet)
        candidate.update(kind=accepted['kind'],columns=accepted['columns'],conflicts=[],verified_format_ref=origin)
        reused.append(candidate)
    return reused if not mapping_errors(reused) else []
