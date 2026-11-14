"""Deterministic header proposals; candidates acquire no authority until reviewed."""
from types import SimpleNamespace

SCHEMA_VERSION = 1
REQUIRED = {
    'claims': {'project_code','activity_code','staff_id','role','session_number','work_date','timesheet_submitted_date'},
    'planning': {'project_code','activity_code','approved_start_date','approved_end_date'},
    'directory': {'staff_id','status'},
    'projects': {'project_code','project_name'},
}
ALIASES = {
    'project_code': {'project code'}, 'project_name': {'project name'},
    'activity_code': {'activity code','رمز النشاط'},
    'staff_id': {'staff id','volunteer id','staff identifier','رقم المتطوع','معرف الموظف'},
    'role': {'role','الدور'}, 'session_number': {'session number','session','رقم الجلسة'},
    'work_date': {'work date','activity date','date','تاريخ العمل','التاريخ'},
    'timesheet_submitted_date': {'timesheet submitted date','submission date','تاريخ التقديم'},
    'approved_start_date': {'approved start date'}, 'approved_end_date': {'approved end date'},
    'status': {'status'},
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
    if {'session_number', 'work_date', 'role'} & fields.keys():
        kind = 'claims'
    elif {'approved_start_date', 'approved_end_date'} & fields.keys():
        kind = 'planning'
    elif 'project_name' in fields:
        kind = 'projects'
    else:
        kind = max(scores, key=scores.get) if fields else 'unsupported'
    if kind != 'unsupported':
        fields = {k:v for k,v in fields.items() if k in REQUIRED[kind]}
    return {'file_id':file.id, 'filename':file.original_filename, 'sheet_index':index,
            'sheet_name':sheet['name'], 'kind':kind, 'header_row':rows[0]['row'] if rows else None,
            'headers':headers, 'columns':fields, 'conflicts':conflicts,
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
        if set(sheet['columns'])-required:
            errors.append(f'{label}: unexpected canonical fields for this document category.')
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
            for row in source[1:]:
                rows.append({'row':row['row'],'values':[row['values'][selection['columns'][field]]
                             if selection['columns'][field]<len(row['values']) else None for field in ordered]})
            normalized.append({'name':sheet['name'],'rows':rows})
        result.append((file,SimpleNamespace(sheets=normalized,row_count=record.row_count)))
    return result
