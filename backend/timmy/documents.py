"""Private spreadsheet intake and coordinator-global, permission-checked reads."""
from .observability import instrument, reference, span

import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, text
from starlette.concurrency import run_in_threadpool

from .audit import audit
from .auth import Authenticated, Database, require_csrf
from .models import DocumentImport, StoredFile, Conversation, projects

router = APIRouter(prefix="/api/documents")
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 100


class DocumentView(BaseModel):
    id: str
    project_id: int | None
    filename: str
    sha256: str
    rows: int
    status: str = "PARSED_MAPPING_REQUIRED"
    workflow_run_id: int | None = None
    data_rows: int | None = None
    conversation_id: str | None = None
    uploaded_at: str | None = None


@instrument("spreadsheet.ingest", "validation")
def parse(data: bytes, extension: str):
    def sheet(name, source):
        rows = []
        for i, row in enumerate(source, 1):
            if not row or all(value is None or value == "" for value in row):
                if i > MAX_ROWS:
                    raise ValueError("Too many source rows")
                continue
            if i > MAX_ROWS or len(row) > MAX_COLUMNS:
                raise ValueError("Spreadsheet exceeds row or column limits")
            values = [None if value is None else str(value) for value in row]
            if any(value and len(value) > 4096 for value in values):
                raise ValueError("Spreadsheet cell exceeds length limit")
            rows.append({"row": i, "values": values})
        return {"name": name, "rows": rows}

    if extension == ".csv":
        if b"\0" in data:
            raise ValueError("Expected a UTF-8 CSV")
        sheets = [sheet("CSV", csv.reader(StringIO(data.decode("utf-8-sig"), newline=""), strict=True))]
    elif extension == ".xlsx":
        from openpyxl import load_workbook

        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if (len(entries) > 128 or len(names) != len(entries)
                    or sum(entry.file_size for entry in entries) > 20 * 1024 * 1024
                    or "xl/workbook.xml" not in names
                    or any("vbaProject" in name or name.startswith("xl/externalLinks/") for name in names)):
                raise ValueError("Unsupported XLSX contents")
        book = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            if len(book.worksheets) > 12:
                raise ValueError("Too many worksheets")
            sheets = []
            for ws in book.worksheets:
                if (ws.max_row or 0) > MAX_ROWS or (ws.max_column or 0) > MAX_COLUMNS:
                    raise ValueError("Worksheet exceeds row or column limits")
                ws.reset_dimensions()
                sheets.append(sheet(ws.title, ws.values))
        finally:
            book.close()
    else:
        raise ValueError("Use UTF-8 CSV or XLSX")
    count = sum(len(item["rows"]) for item in sheets)
    if not 0 < count <= MAX_ROWS:
        raise ValueError("Spreadsheet is empty or exceeds the document row limit")
    return sheets, count


def describe(file, record, *, workflow_run_id=None):
    return DocumentView(
        id=file.id, project_id=file.project_id, filename=file.original_filename,
        sha256=file.sha256, rows=record.row_count,
        status=('PAYMENT_RETURN_RECEIVED_UNVERIFIED' if file.purpose == 'payment_return'
                else 'PARSED_MAPPING_REQUIRED'),
        workflow_run_id=workflow_run_id,
    )


def scoped_documents(db, principal, conversation_id=None, *, purpose='timesheet'):
    allowed = [key for key, permissions in principal.project_permissions.items() if "timesheets.view" in permissions]
    own = select(Conversation.id).where(Conversation.owner_id == principal.user.id)
    query = select(StoredFile, DocumentImport).join(DocumentImport).where(
        # Historical pre-category imports used the 'intake' purpose.
        # Preserve their visibility without mixing in payment returns.
        (StoredFile.purpose.in_(('timesheet', 'intake')) if purpose == 'timesheet'
         else StoredFile.purpose == purpose),
        or_(
            StoredFile.project_id.in_(allowed),
            # Global upload is visible only to the uploading actor.
            (StoredFile.project_id.is_(None)) & (StoredFile.uploaded_by == principal.user.id),
        ),
        or_((DocumentImport.conversation_id.is_(None)) & (StoredFile.uploaded_by == principal.user.id), DocumentImport.conversation_id.in_(own)),
    )
    if conversation_id is not None:
        query = query.where(DocumentImport.conversation_id == conversation_id)
    return query


def conversation_owned(db, principal, identifier):
    if identifier is not None:
        item = db.get(Conversation, identifier)
        if item is None or item.owner_id != principal.user.id:
            raise HTTPException(404, "Conversation unavailable")


@router.get("", response_model=list[DocumentView])
def list_documents(principal: Authenticated, db: Database, conversation_id: UUID | None = None):
    identifier = str(conversation_id) if conversation_id else None
    conversation_owned(db, principal, identifier)
    from .models import MappingProposal
    mappings=list(db.scalars(select(MappingProposal).where(MappingProposal.actor_id==principal.user.id)
                             .order_by(MappingProposal.id.desc())))
    result=[]
    for file,record in db.execute(scoped_documents(db,principal,identifier).order_by(StoredFile.uploaded_at.desc()).limit(100)):
        item=describe(file,record)
        latest={}
        for mapping in mappings:
            if mapping.conversation_id==record.conversation_id and any(sheet['file_id']==file.id for sheet in mapping.sheets):
                latest.setdefault(mapping.project_id,mapping.status)
        item.status=('MAPPING_CONFIRMED' if latest and all(v=='confirmed' for v in latest.values()) else 'PARSED_MAPPING_REQUIRED')
        item.data_rows=sum(max(0,len(sheet['rows'])-1) for sheet in record.sheets)
        item.conversation_id=record.conversation_id
        item.uploaded_at=str(file.uploaded_at)
        result.append(item)
    return result


MEDIA = {
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"},
}


@router.post("", status_code=201, response_model=DocumentView)
async def upload(request: Request, principal: Authenticated, db: Database, filename: str,
                 project_id: int | None = None, conversation_id: UUID | None = None,
                 purpose: Literal['timesheet', 'payment_return'] = 'timesheet'):
    require_csrf(request, principal)
    # Workspace managers can ingest documents only in projects they can read.
    principal.require("projects:manage")
    if project_id is None:
        if purpose != "timesheet" or conversation_id is None:
            raise HTTPException(422, "Global intake requires an owned conversation and timesheet purpose")
        if not any("timesheets.view" in keys and "projects:read" in keys
                   for keys in principal.project_permissions.values()):
            raise HTTPException(403, "No authorized projects for global intake")
    else:
        principal.require("timesheets.view", project_id)
    if purpose == 'payment_return':
        # Reuse existing privileges; no financial write permission is granted.
        principal.require("payments.view", project_id)
    identifier = str(conversation_id) if conversation_id else None
    conversation_owned(db, principal, identifier)
    if project_id is not None and db.scalar(select(projects.c.status).where(projects.c.id == project_id)) != "active":
        raise HTTPException(409, "Select an active project")
    extension = Path(filename).suffix.lower()
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if (extension not in MEDIA or media not in MEDIA[extension] or len(filename) > 200
            or any(ch in filename for ch in "/\\") or any(ord(ch) < 32 for ch in filename)):
        raise HTTPException(415, "Use a CSV or XLSX file with a valid filename")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BYTES:
            raise HTTPException(413, "Spreadsheet exceeds 5 MB")
        body.extend(chunk)
    data = bytes(body)
    try:
        sheets, count = await run_in_threadpool(parse, data, extension)
    except (ValueError, BadZipFile, csv.Error):
        raise HTTPException(422, "Spreadsheet is invalid or exceeds parsing limits") from None
    except Exception:
        raise HTTPException(422, "Spreadsheet could not be parsed safely") from None

    # Refresh permission and project state before committing a long upload.
    from .auth import current_principal
    db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))
    principal = current_principal(request, db)
    principal.require("projects:manage")
    if project_id is None:
        if purpose != "timesheet" or conversation_id is None:
            raise HTTPException(422, "Global intake requires an owned conversation and timesheet purpose")
        if not any("timesheets.view" in keys and "projects:read" in keys
                   for keys in principal.project_permissions.values()):
            raise HTTPException(403, "No authorized projects for global intake")
    else:
        principal.require("timesheets.view", project_id)
    if purpose == 'payment_return':
        # Reuse existing privileges; no financial write permission is granted.
        principal.require("payments.view", project_id)
    require_csrf(request, principal)
    conversation_owned(db, principal, identifier)
    if project_id is not None and db.scalar(select(projects.c.status).where(projects.c.id == project_id)) != "active":
        raise HTTPException(409, "Select an active project")

    root = request.app.state.config.document_root.expanduser()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    file_id = str(uuid4())
    path = root / file_id
    import os
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    file = StoredFile(id=file_id, purpose=purpose, original_filename=filename, relative_storage_key=file_id,
                      sha256=sha256(data).hexdigest(), size_bytes=len(data), mime_type=media,
                      uploaded_at=datetime.now(timezone.utc).isoformat(), project_id=project_id, uploaded_by=principal.user.id)
    record = DocumentImport(file_id=file_id, conversation_id=identifier, sheets=sheets, row_count=count)
    try:
        db.add(file)
        db.flush()
        db.add(record)
        audit(db, "document_uploaded", principal.user.id, resource_type="stored_file", resource_id=file_id,
              evidence_file_id=file_id, outcome=("payment_return_received_unverified"
                                                if purpose == "payment_return"
                                                else "parsed_mapping_required"))
        triggered_run = None
        if purpose == 'payment_return':
            # Source bytes, upload metadata and trigger commit atomically.
            # Reconciliation stays blocked pending trusted source contract.
            from .workflows import run_workflow
            triggered_run = run_workflow(
                db, principal, request.app.state.config,
                workflow_id='payment_return', project_id=project_id,
                request_key=f'payment_return:upload:{file_id}',
                payment_return_file_id=file_id,
            )
        with span("document.commit", "database"):
            db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return describe(file, record,
                    workflow_run_id=triggered_run.id if triggered_run else None)


@router.get("/{file_id}/download")
def download(file_id: UUID, request: Request, principal: Authenticated, db: Database):
    from urllib.parse import quote

    # Do not mix financial returns into timesheet discovery. Explicitly scoped
    # download still works for a payment-return evidence owner.
    candidate = db.get(StoredFile, str(file_id))
    if candidate is None or candidate.purpose not in {'timesheet', 'intake', 'payment_return'}:
        raise HTTPException(404, "Document unavailable")
    if candidate.purpose == 'payment_return':
        principal.require('payments.view', candidate.project_id)
    category = 'timesheet' if candidate.purpose == 'intake' else candidate.purpose
    row = db.execute(scoped_documents(db, principal, purpose=category)
                     .where(StoredFile.id == str(file_id))).one_or_none()
    if row is None:
        raise HTTPException(404, "Document unavailable")
    file, _ = row
    try:
        data = (request.app.state.config.document_root.expanduser() / str(file_id)).read_bytes()
    except OSError:
        raise HTTPException(409, "Stored document bytes unavailable") from None
    if len(data) != file.size_bytes or sha256(data).hexdigest() != file.sha256:
        raise HTTPException(409, "Document integrity check failed")
    audit(db, "document_downloaded", principal.user.id, resource_type="stored_file", resource_id=file.id,
          evidence_file_id=file.id, outcome="success")
    db.commit()
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.original_filename, safe='')}",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/metrics")
def document_metrics(principal: Authenticated, db: Database):
    from sqlalchemy import func

    visible = scoped_documents(db, principal).with_only_columns(DocumentImport.row_count).subquery()
    count, rows = db.execute(select(func.count(), func.coalesce(func.sum(visible.c.row_count), 0))).one()
    return {"documents": count, "source_rows": rows}


# Only emit canonical labels and counts. Raw headers, names, formulas and cells
# stay outside the model context.
HEADER_ALIASES = {
    "staff identifier": {"staff id", "volunteer id", "رقم المتطوع", "معرف الموظف"},
    "activity code": {"activity code", "رمز النشاط"},
    "session number": {"session", "session number", "رقم الجلسة"},
    "work date": {"work date", "activity date", "date", "تاريخ العمل", "التاريخ"},
    "submission date": {"timesheet submitted date", "submission date", "تاريخ التقديم"},
    "role": {"role", "الدور"},
}


@instrument("spreadsheet.profile", "validation")
def spreadsheet_profile(record):
    summaries = []
    for index, sheet in enumerate(record.sheets, 1):
        source = sheet["rows"]
        headers = source[0]["values"] if source else []
        normalized = {" ".join(str(value or "").casefold().replace("_", " ").split()) for value in headers}
        fields = [key for key, aliases in HEADER_ALIASES.items() if aliases & normalized]
        summaries.append({
            "sheet": index, "rows": len(source), "header_row": source[0]["row"] if source else None,
            "candidate_fields": fields,
        })
    # Include category-specific fields, rather than classifying every document
    # with the old timesheet-only display allowlist.
    from .column_mappings import propose_sheet
    labels = {'staff_id': 'staff identifier', 'timesheet_submitted_date': 'submission date'}
    for index, sheet in enumerate(record.sheets):
        from types import SimpleNamespace
        candidate = propose_sheet(SimpleNamespace(id='', original_filename=''), sheet, index)
        summaries[index]['category'] = candidate['kind']
        summaries[index]['candidate_fields'] = [labels.get(field, field.replace('_', ' ')) for field in candidate['columns']]
    return summaries


@instrument("documents.retrieve", "context")
def resolve_documents(db, principal, conversation_id, project_id=None, document_ids=()):
    """Resolve without traversing another user's private conversation."""
    visible = scoped_documents(db, principal)
    if project_id is not None:
        principal.require("timesheets.view", project_id)
        visible = visible.where(StoredFile.project_id == project_id)
    ids = list(dict.fromkeys(str(identifier) for identifier in document_ids))
    explicit = db.execute(visible.where(StoredFile.id.in_(ids))).all() if ids else []
    if len(explicit) != len(ids):
        raise HTTPException(404, "A selected document is unavailable in this scope")
    if ids:
        if len(ids) > 20:
            raise HTTPException(422, "Select at most 20 spreadsheets")
        for file, _ in explicit:
            reference(file.id, 'retrieved', file.sha256, category='context')
        return sorted(explicit, key=lambda row: row[0].id)
    automatic = visible.where(
        DocumentImport.conversation_id == conversation_id
    ) if project_id is None else visible.where(or_(
        DocumentImport.conversation_id == conversation_id,
        DocumentImport.conversation_id.is_(None),
        StoredFile.uploaded_by == principal.user.id,
    ))
    rows = db.execute(automatic.order_by(
        (DocumentImport.conversation_id == conversation_id).desc(), StoredFile.id,
    ).limit(21)).all()
    combined = {file.id: (file, record) for file, record in explicit}
    for file, record in rows:
        combined.setdefault(file.id, (file, record))
    if len(combined) > 20:
        raise HTTPException(422, "More than 20 spreadsheets are in scope. Narrow the project or conversation.")
    for file, _ in combined.values():
        reference(file.id, 'retrieved', file.sha256, category='context')
    return list(combined.values())


def project_report_cutoffs(db, project_id):
    from .models import ExternalReportVersion, activities

    code = db.scalar(select(projects.c.project_code).where(projects.c.id == project_id))
    if not code:
        return {}
    versions = db.scalars(select(ExternalReportVersion).join(activities, activities.c.id == ExternalReportVersion.activity_id).where(
        ExternalReportVersion.project_id == project_id, ExternalReportVersion.cutoff.is_not(None),
        activities.c.project_id == project_id, activities.c.activity_code == ExternalReportVersion.activity_code, activities.c.code_authority == 'source_supplied',
    ).order_by(ExternalReportVersion.id))
    result = {}
    for row in versions:
        from .reporting_register import financial_register_blockers
        if row.source.startswith('excel-register:') and financial_register_blockers(db,project_id,row.activity_code):
            continue
        key = (project_id, code, row.activity_code)
        if key in result:
            raise HTTPException(409, "Conflicting frozen report evidence")
        result[key] = {"id": row.id, "cutoff": row.cutoff, "version": row.version}
    return result


@router.post("/structural-validation/{project_id}")
def persist_validation(project_id: int, request: Request, principal: Authenticated, db: Database):
    from time import time
    from .auth import current_principal
    from .models import StructuralValidation
    from .session_preview import preview

    require_csrf(request, principal)
    db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))
    principal = current_principal(request, db)
    require_csrf(request, principal)
    principal.require("projects:manage")
    principal.require("timesheets.view", project_id)
    if project_id is not None and db.scalar(select(projects.c.status).where(projects.c.id == project_id)) != "active":
        raise HTTPException(409, "Select an active project")
    documents = resolve_documents(db, principal, None, project_id)
    cutoffs = project_report_cutoffs(db, project_id)
    project_code = db.scalar(select(projects.c.project_code).where(projects.c.id == project_id))
    from .planning_activities import registry
    activity_registry = registry(db, [project_id])
    cutoff_key = ":".join(f"{value['id']}@{value['cutoff']}" for value in cutoffs.values())
    import json
    registry_key = json.dumps([[list(k),v] for k,v in sorted(activity_registry.items())], sort_keys=True)
    fingerprint = sha256(("structural-v4:" + (project_code or "") + ":" + registry_key + cutoff_key + ":" + str(principal.user.id) + ":" + ":".join(sorted(file.id for file, _ in documents))).encode()).hexdigest()
    existing = db.scalar(select(StructuralValidation).where(
        StructuralValidation.project_id == project_id, StructuralValidation.fingerprint == fingerprint,
        StructuralValidation.actor_id == principal.user.id,
    ))
    if existing:
        return validation_view(readable_validation(db, principal, existing.id))
    snapshot = {"claims": [], "activities": []}
    if preview(documents, snapshot=snapshot, report_cutoffs=cutoffs, activity_registry=activity_registry,
               project_codes={project_id:db.scalar(select(projects.c.project_code).where(projects.c.id == project_id))}) is None or not snapshot["activities"]:
        raise HTTPException(422, "No supported session claims in the visible project documents")
    event = StructuralValidation(project_id=project_id, actor_id=principal.user.id,
                                 fingerprint=fingerprint, created_at=int(time()), snapshot=snapshot)
    db.add(event)
    db.flush()
    audit(db, "structural_validation_saved", principal.user.id, resource_type="structural_validation",
          resource_id=str(event.id), outcome="authority_pending")
    db.commit()
    return validation_view(event)


@router.get("/structural-validation/{project_id}")
def latest_validation(project_id: int, principal: Authenticated, db: Database):
    from .models import StructuralValidation

    principal.require("timesheets.view", project_id)
    event = db.scalar(select(StructuralValidation).where(
        StructuralValidation.project_id == project_id, StructuralValidation.actor_id == principal.user.id,
    ).order_by(StructuralValidation.id.desc()).limit(1))
    if event is None:
        return None
    event = readable_validation(db, principal, event.id)
    return validation_view(event)


def validation_view(event):
    return {"id": event.id, "project_id": event.project_id, "activities": event.snapshot["activities"]}


@router.get("/validation/{validation_id}")
def get_validation(validation_id: int, principal: Authenticated, db: Database):
    event = readable_validation(db, principal, validation_id)
    return validation_view(event)


class EvidenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_code: str = Field(min_length=1, max_length=200)
    activity_code: str = Field(min_length=1, max_length=200)
    kind: Literal["planning", "staff"]
    decision: Literal["confirmed", "rejected"]
    evidence_ref: str = Field(min_length=5, max_length=500)


def readable_validation(db, principal, validation_id):
    from .models import StructuralValidation

    event = db.get(StructuralValidation, validation_id)
    if event is None:
        raise HTTPException(404, "Validation unavailable")
    principal.require("timesheets.view", event.project_id)
    # A project permission alone cannot reveal provenance from private chats.
    visible = set(db.scalars(scoped_documents(db, principal).with_only_columns(StoredFile.id)))
    sources = {sheet["file_id"] for sheet in event.snapshot.get("sheets", [])}
    if not sources or not sources <= visible:
        raise HTTPException(404, "Validation evidence unavailable")
    return event


@router.post("/reviews/{validation_id}")
def review_evidence(validation_id: int, body: EvidenceDecision, request: Request,
                    principal: Authenticated, db: Database):
    from time import time
    from .auth import current_principal
    from .models import EvidenceReview

    require_csrf(request, principal)
    db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))
    principal = current_principal(request, db)
    require_csrf(request, principal)
    event = readable_validation(db, principal, validation_id)
    principal.require(f"{body.kind}.verify", event.project_id)
    if not any((row["project_code"], row["activity_code"]) == (body.project_code, body.activity_code)
               for row in event.snapshot["activities"]):
        raise HTTPException(404, "Activity unavailable in this validation")
    previous = db.scalar(select(EvidenceReview).where(
        EvidenceReview.validation_id == event.id, EvidenceReview.project_code == body.project_code,
        EvidenceReview.activity_code == body.activity_code, EvidenceReview.kind == body.kind,
    ).order_by(EvidenceReview.id.desc()).limit(1))
    if (previous and previous.actor_id == principal.user.id and previous.decision == body.decision
            and previous.evidence_ref == body.evidence_ref):
        return {"id": previous.id}
    entry = EvidenceReview(validation_id=event.id, actor_id=principal.user.id,
                           created_at=int(time()), **body.model_dump())
    db.add(entry)
    db.flush()
    audit(db, "evidence_review_recorded", principal.user.id, resource_type="evidence_review",
          resource_id=str(entry.id), outcome=body.decision)
    db.commit()
    # A review is the human checkpoint; resume only as this same authorized
    # actor, never by impersonating another conversation owner.
    if 'projects:manage' in principal.permissions:
        sources={sheet['file_id'] for sheet in event.snapshot.get('sheets',[])}
        conversations=list(db.scalars(select(Conversation).join(DocumentImport,DocumentImport.conversation_id==Conversation.id)
            .where(Conversation.owner_id==principal.user.id,DocumentImport.file_id.in_(sources)).distinct()))
        from .global_mappings import resume_after_evidence
        for conversation in conversations:
            documents=resolve_documents(db,principal,conversation.id,None,[])
            resume_after_evidence(db,principal,request.app.state.config,conversation,documents)
        db.commit()
    return {"id": entry.id}


@router.get("/reviews/{validation_id}")
def get_reviews(validation_id: int, principal: Authenticated, db: Database):
    from .models import EvidenceReview

    event = readable_validation(db, principal, validation_id)
    return [
        {"id": item.id, "actor_id": item.actor_id, "kind": item.kind, "decision": item.decision,
         "evidence_ref": item.evidence_ref, "created_at": item.created_at,
         "project_code": item.project_code, "activity_code": item.activity_code}
        for item in db.scalars(select(EvidenceReview).where(
            EvidenceReview.validation_id == event.id,
        ).order_by(EvidenceReview.id.desc()).limit(100))
    ]
