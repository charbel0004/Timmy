"""Private spreadsheet intake and project-scoped read tools."""
import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, text
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
    project_id: int
    filename: str
    sha256: str
    rows: int
    status: str = "PARSED_MAPPING_REQUIRED"


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


def describe(file, record):
    return DocumentView(id=file.id, project_id=file.project_id, filename=file.original_filename,
                        sha256=file.sha256, rows=record.row_count)


def scoped_documents(db, principal, conversation_id=None):
    allowed = [key for key, permissions in principal.project_permissions.items() if "timesheets.view" in permissions]
    query = select(StoredFile, DocumentImport).join(DocumentImport).where(StoredFile.project_id.in_(allowed))
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
    return [describe(file, record) for file, record in db.execute(
        scoped_documents(db, principal, identifier).order_by(StoredFile.uploaded_at.desc()).limit(100)
    )]


MEDIA = {
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"},
}


@router.post("", status_code=201, response_model=DocumentView)
async def upload(request: Request, principal: Authenticated, db: Database, project_id: int,
                 filename: str, conversation_id: UUID | None = None):
    require_csrf(request, principal)
    # Workspace managers can ingest documents only in projects they can read.
    principal.require("projects:manage")
    principal.require("timesheets.view", project_id)
    identifier = str(conversation_id) if conversation_id else None
    conversation_owned(db, principal, identifier)
    if db.scalar(select(projects.c.status).where(projects.c.id == project_id)) != "active":
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
    principal.require("timesheets.view", project_id)
    require_csrf(request, principal)
    conversation_owned(db, principal, identifier)
    if db.scalar(select(projects.c.status).where(projects.c.id == project_id)) != "active":
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
    file = StoredFile(id=file_id, purpose="timesheet", original_filename=filename, relative_storage_key=file_id,
                      sha256=sha256(data).hexdigest(), size_bytes=len(data), mime_type=media,
                      uploaded_at=datetime.now(timezone.utc).isoformat(), project_id=project_id, uploaded_by=principal.user.id)
    record = DocumentImport(file_id=file_id, conversation_id=identifier, sheets=sheets, row_count=count)
    try:
        db.add(file)
        db.flush()
        db.add(record)
        audit(db, "document_uploaded", principal.user.id, resource_type="stored_file", resource_id=file_id,
              evidence_file_id=file_id, outcome="parsed_mapping_required")
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return describe(file, record)


@router.get("/{file_id}/download")
def download(file_id: UUID, request: Request, principal: Authenticated, db: Database):
    from urllib.parse import quote

    row = db.execute(scoped_documents(db, principal).where(StoredFile.id == str(file_id))).one_or_none()
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
    return summaries
