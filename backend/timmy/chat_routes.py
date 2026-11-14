from .session_preview import preview as session_preview
from .documents import resolve_documents, spreadsheet_profile
from datetime import datetime, timezone
from time import time
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .ai import OllamaAdapter, OllamaExtractionError, build_ollama_client
from .audit import audit
from .auth import Authenticated, Database, require_csrf
from .chat import respond
from .models import ChatTurn, Conversation
from .auth import current_principal
from .repositories import visible_projects

router = APIRouter(prefix="/api/chat/conversations")


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: UUID
    message: str = Field(min_length=1, max_length=1500)
    project_id: int | None = Field(default=None, gt=0)
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)


def owned(db: Database, principal: Authenticated, conversation_id: UUID) -> Conversation:
    principal.require("projects:read")
    conversation = db.get(Conversation, str(conversation_id))
    if conversation is None or conversation.owner_id != principal.user.id:
        raise HTTPException(404, "Conversation unavailable")
    return conversation


def view(turn: ChatTurn):
    timestamp = datetime.fromtimestamp(turn.created_at, timezone.utc).isoformat()
    return [
        {"id": f"{turn.id}-{role}", "text": value, "role": role, "timestamp": timestamp}
        for role, value in (("user", turn.prompt), ("assistant", turn.reply))
    ]


@router.post("", status_code=201)
def create(request: Request, principal: Authenticated, db: Database):
    principal.require("projects:read")
    require_csrf(request, principal)
    identifier = str(uuid4())
    db.add(Conversation(id=identifier, owner_id=principal.user.id))
    db.commit()
    return {"id": identifier, "messages": []}


@router.get("")
def list_conversations(principal: Authenticated, db: Database):
    principal.require("projects:read")
    conversations = db.scalars(select(Conversation).where(
        Conversation.owner_id == principal.user.id,
    ).order_by(Conversation.id).limit(100))
    return [history(db, item.id, limit=1) for item in conversations]


def history(db: Database, identifier: str, limit: int = 50):
    turns = db.scalars(select(ChatTurn).where(ChatTurn.conversation_id == identifier)
                       .order_by(ChatTurn.id.desc()).limit(limit)).all()
    return {"id": identifier, "title": db.get(Conversation, identifier).title, "messages": [message for turn in reversed(turns) for message in view(turn)]}


@router.get("/{conversation_id}")
def get_conversation(conversation_id: UUID, principal: Authenticated, db: Database):
    return history(db, owned(db, principal, conversation_id).id)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, request: Request, principal: Authenticated, db: Database):
    require_csrf(request, principal)
    db.delete(owned(db, principal, conversation_id))
    db.commit()
    return Response(status_code=204)


@router.post("/{conversation_id}/messages")
async def send(conversation_id: UUID, payload: SendMessage, request: Request, principal: Authenticated, db: Database):
    require_csrf(request, principal)
    identifier = owned(db, principal, conversation_id).id
    owner = principal.user.id
    request_id = str(payload.request_id)
    query = select(ChatTurn).where(ChatTurn.conversation_id == identifier, ChatTurn.request_id == request_id)

    def replay(turn: ChatTurn):
        if turn.prompt != payload.message:
            raise HTTPException(409, "Request identifier already used")
        return {"message": view(turn)[1]}

    if previous := db.scalar(query):
        return replay(previous)
    resolve_documents(db, principal, identifier, payload.project_id, payload.document_ids)
    context = [{"role": item["role"], "content": item["text"][:1000]}
               for item in history(db, identifier, limit=2)["messages"]]
    db.rollback()
    config = request.app.state.config
    used_tool = False

    def record_tool():
        nonlocal used_tool
        used_tool = True

    document_used = False

    def document_summary():
        nonlocal document_used
        document_used = True
        actor = current_principal(request, db)
        owned(db, actor, conversation_id)
        documents = resolve_documents(db, actor, identifier, payload.project_id, payload.document_ids)
        audit(db, "chat_tool_analyze_documents", owner, resource_type="conversation", resource_id=identifier,
              outcome="success" if documents else "no_visible_documents")
        arabic = any("\u0600" <= character <= "\u06ff" for character in payload.message)
        if not documents:
            return "لا توجد ملفات متاحة في هذه المحادثة." if arabic else "No accessible spreadsheets were found here. Select an assigned project in Context to include its available documents, or attach a spreadsheet."
        import re

        if re.search(r"session|validate|eligib|payment policy|الجلسات|تحقق", payload.message, re.I):
            result = session_preview(documents)
            if result is not None:
                return result
            return (
                "I couldn't run session checks because none of the accessible sheets has the required "
                "timesheet columns: project code, activity code, staff ID, role, session number, work date, "
                "and submission date. Payment eligibility remains blocked."
            )
        pending = (
            "تم فحص بنية الملفات. يجب تأكيد الأعمدة والهويات قبل التحقق من سياسة الجلسات."
            if arabic else "I inspected the parsed spreadsheet structure. Confirm column mappings and identities before session-policy validation."
        )
        labels = {
            "staff identifier": "معرّف الموظف", "activity code": "رمز النشاط",
            "session number": "رقم الجلسة", "work date": "تاريخ العمل",
            "submission date": "تاريخ التقديم", "role": "الدور",
        }
        lines = [pending]
        for file, record in documents:
            # Escape filename punctuation before embedding it in Markdown.
            filename = "".join(
                "\\" + char if char in r"\`*_{}[]<>()#+-.!|~&" else char
                for char in file.original_filename
            )
            lines.append(f"\n**{filename}**")
            lines.append(f"- {'مرجع الملف' if arabic else 'File reference'}: `{file.id}`")
            for sheet in spreadsheet_profile(record):
                candidates = sheet["candidate_fields"]
                fields = ", ".join(labels[key] if arabic else key for key in candidates) or ("لا يوجد" if arabic else "none recognized")
                if arabic:
                    lines.append(f"- الورقة {sheet['sheet']}: {sheet['rows']} صفوف مصدر؛ الحقول المقترحة: {fields}.")
                else:
                    lines.append(f"- Sheet {sheet['sheet']}: {sheet['rows']} source rows; candidate fields: {fields}.")
        return "\n".join(lines)


    try:
        async with build_ollama_client(config) as client:
            reply, projects = await respond(
                OllamaAdapter(config, client),
                [*context, {"role": "user", "content": payload.message}],
                lambda: visible_projects(db, owner),
                record_tool,
                document_summary,
            )
    except OllamaExtractionError as error:
        raise HTTPException(503, f"Local assistant unavailable ({error.code})") from None
    principal = current_principal(request, db)
    owned(db, principal, conversation_id)
    turn = ChatTurn(conversation_id=identifier, request_id=request_id, prompt=payload.message,
                    reply="Spreadsheet inspection requested." if document_used else reply, created_at=int(time()))
    db.add(turn)
    if used_tool:
        audit(db, "chat_tool_list_projects", owner)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if previous := db.scalar(query):
            return replay(previous)
        raise HTTPException(409, "Conversation changed while processing") from None
    message = view(turn)[1]
    if document_used:
        message["text"] = reply
    if projects is not None:
        message["tables"] = [{"title": "Assigned projects", "columns": ["Project"],
                              "rows": [[project.name] for project in projects]}]
    return {"message": message}


class RenameConversation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)


@router.patch("/{conversation_id}")
def rename(conversation_id: UUID, payload: RenameConversation, request: Request,
           principal: Authenticated, db: Database):
    require_csrf(request, principal)
    conversation = owned(db, principal, conversation_id)
    conversation.title = payload.title
    db.commit()
    return history(db, str(conversation_id))
