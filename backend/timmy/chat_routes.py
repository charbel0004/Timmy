from .observability import instrument, current, span
import re
from .session_preview import preview as session_preview
from .documents import resolve_documents, spreadsheet_profile
from datetime import datetime, timezone
from time import time
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from .ai import OllamaAdapter, OllamaExtractionError, build_ollama_client
from .audit import audit
from .auth import Authenticated, Database, require_csrf
from .chat import respond
from .models import ChatTurn, Conversation, DocumentImport, StoredFile, projects as project_table
from .auth import current_principal
from .demo_operations import records as demo_records, summary as demo_summary
from .repositories import visible_projects
from .workflows import run_workflow, render_run
from .documents import project_report_cutoffs
from .conversation_workflow import handle_message, public_state, confirm_mapping
from .project_discovery import discover_projects, render_project_discovery
from .global_workflow import run_global_workflow, global_workflow_status
from .conversation_workflow import STATUS, check_integrity
from .workflows import choose_workflow
from .failure_diagnostics import classify

router = APIRouter(prefix="/api/chat/conversations")


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: UUID
    message: str = Field(min_length=1, max_length=1500)
    project_id: int | None = Field(default=None, gt=0)
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)


def attached_sources(db: Database, identifier: str, project_id: int) -> list[str]:
    """Files attached in this conversation for the selected project only."""
    rows = db.execute(select(DocumentImport.file_id)
                      .join(StoredFile, StoredFile.id == DocumentImport.file_id)
                      .where(DocumentImport.conversation_id == identifier,
                             StoredFile.project_id == project_id)
                      .order_by(DocumentImport.file_id)).all()
    return [str(row[0]) for row in rows]


def owned(db: Database, principal: Authenticated, conversation_id: UUID) -> Conversation:
    principal.require("projects:read")
    conversation = db.get(Conversation, str(conversation_id))
    if conversation is None or conversation.owner_id != principal.user.id:
        raise HTTPException(404, "Conversation unavailable")
    return conversation


def view(turn: ChatTurn):
    timestamp = datetime.fromtimestamp(turn.created_at, timezone.utc).isoformat()
    return [
        {"id": f"{turn.id}-{role}", "text": value, "role": role, "timestamp": timestamp,
         **({"requestId": turn.request_id, "executionId": (turn.context or {}).get("execution_id")} if role == "assistant" else {})}
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
    return [history(db, item.id, limit=1, principal=principal) for item in conversations]


def history(db: Database, identifier: str, limit: int = 50, principal=None):
    turns = db.scalars(select(ChatTurn).where(ChatTurn.conversation_id == identifier)
                       .order_by(ChatTurn.id.desc()).limit(limit)).all()
    messages = []
    for turn in reversed(turns):
        pair = view(turn)
        if principal and turn.context:
            try:
                if turn.context.get("payment_policy_lookup"):
                    project_id = turn.context["request"].get("project_id")
                    if project_id is not None:
                        principal.require("projects:read", project_id)
                else:
                    resolve_documents(db, principal, identifier, turn.context['request'].get('project_id'),
                                      turn.context.get('source_ids', []))
            except HTTPException:
                pair[1]['text'] = 'This result is unavailable under your current document permissions.'
        messages.extend(pair)
    conversation = db.get(Conversation, identifier)
    return {"id": identifier, "title": conversation.title, "messages": messages}


@router.get("/{conversation_id}")
def get_conversation(conversation_id: UUID, principal: Authenticated, db: Database):
    conversation = owned(db, principal, conversation_id)
    result = history(db, conversation.id, principal=principal)
    try:
        result['workflow'] = public_state(db, principal, conversation)
    except HTTPException as error:
        if error.status_code not in (403, 404):
            raise
        result['workflow'] = {'stage': 'ACCESS_DENIED', 'validation': None}
    return result


@router.get('/{conversation_id}/workflow')
def workflow_state(conversation_id: UUID, principal: Authenticated, db: Database):
    return public_state(db, principal, owned(db, principal, conversation_id))


class SheetSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    file_id: str = Field(min_length=36, max_length=36)
    sheet_index: int = Field(ge=0, le=11)
    kind: str
    columns: dict[str, int] = Field(max_length=20)


class ConfirmMapping(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: int = Field(ge=1)
    fingerprint: str = Field(pattern='^[0-9a-f]{64}$')
    sheets: list[SheetSelection] | None = Field(default=None, max_length=240)


@router.post('/{conversation_id}/mappings/{proposal_id}/confirm')
def confirm_columns(conversation_id: UUID, proposal_id: UUID, body: ConfirmMapping,
                    request: Request, principal: Authenticated, db: Database):
    require_csrf(request, principal)
    db.rollback()
    db.execute(text('BEGIN IMMEDIATE'))
    principal = current_principal(request, db)
    require_csrf(request, principal)
    conversation = owned(db, principal, conversation_id)
    reply = confirm_mapping(db, principal, request.app.state.config, conversation, str(proposal_id),
                            body.version, body.fingerprint, body.sheets)
    confirmation_key = str(uuid5(NAMESPACE_URL, f'mapping-confirmation:{proposal_id}:{body.version}'))
    if not db.scalar(select(ChatTurn.id).where(ChatTurn.conversation_id == conversation.id,
                                               ChatTurn.request_id == confirmation_key)):
        scope = conversation.workflow_state['scope']
        db.add(ChatTurn(conversation_id=conversation.id, request_id=confirmation_key,
                        prompt=f'Column mappings confirmed (proposal {proposal_id}, version {body.version}).',
                        reply=reply, created_at=int(time()), context={
                            'request': {'project_id': scope['project_id']}, 'source_ids': scope['source_ids']}))
    db.commit()
    return {'message': reply, 'workflow': public_state(db, principal, conversation)}


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, request: Request, principal: Authenticated, db: Database):
    require_csrf(request, principal)
    db.delete(owned(db, principal, conversation_id))
    db.commit()
    return Response(status_code=204)


@router.get("/{conversation_id}/activity/{request_id}")
async def activity(conversation_id: UUID, request_id: UUID, request: Request,
                   principal: Authenticated, db: Database):
    identifier = owned(db, principal, conversation_id).id
    return {"steps": request.app.state.chat_activity.traces.get((identifier, str(request_id)), [])}


@router.post("/{conversation_id}/messages")
async def send(conversation_id: UUID, payload: SendMessage, request: Request, principal: Authenticated, db: Database):
    require_csrf(request, principal)
    identifier = owned(db, principal, conversation_id).id
    key = (identifier, str(payload.request_id))
    _, record = request.app.state.chat_activity.start(key)
    record("Checking project and document access")
    try:
        result = await answer(conversation_id, payload, request, principal, db, identifier, record)
    except HTTPException as error:
        record("Request stopped", status=error.status_code)
        raise
    except Exception as error:
        failure = classify(error, step="CHAT_REQUEST")
        record("Request failed safely", code=failure.code,
               correlation_id=failure.correlation_id,
               error_type=failure.exception_type)
        # Return a stable, actionable incident reference, not sensitive
        # exception text or a false success result.
        raise HTTPException(500, {
            "code": failure.code,
            "correlation_id": failure.correlation_id,
            "action": "Request authorized operator review; do not retry automatically",
        }) from None
    record("Response ready")
    result["message"]["requestId"] = key[1]
    return result


@instrument("agent.orchestrate", "orchestrator")
async def answer(conversation_id, payload, request, principal, db, identifier, record):
    conversation = owned(db, principal, conversation_id)
    owner = principal.user.id
    request_id = str(payload.request_id)
    query = select(ChatTurn).where(ChatTurn.conversation_id == identifier, ChatTurn.request_id == request_id)

    policy_lookup = not payload.document_ids and bool(re.search(
        r"\b(?:hourly|session|payment) rate\b|\bpayment polic(?:y|ies)\b", payload.message, re.I
    ))
    request_context = payload.model_dump(mode='json', exclude={'request_id'})
    saved_scope = (conversation.workflow_state or {}).get('scope', {})
    # A selected project limits this conversation to its own attachments, so an
    # unrelated file from another conversation cannot block Process or mapping.
    selected_ids = payload.document_ids
    if payload.project_id is not None and not selected_ids:
        selected_ids = attached_sources(db, identifier, payload.project_id)
    inherited_scope = payload.project_id is None and not selected_ids
    # An existing single-project workflow must not shadow newly attached global
    # documents or make a chat permanently tied to an older selected project.
    current_documents = resolve_documents(db, principal, identifier, None, []) if inherited_scope else []
    global_sources = any(f.project_id is None for f, _ in current_documents) or (
        len({f.project_id for f, _ in current_documents}) > 1
    )
    effective_project = (saved_scope.get('project_id') if inherited_scope and not global_sources
                         else payload.project_id)
    effective_ids = (saved_scope.get('source_ids', []) if inherited_scope and not global_sources
                     else selected_ids)
    documents = [] if policy_lookup else resolve_documents(db, principal, identifier, effective_project, effective_ids)
    source_ids = [file.id for file, _ in documents]
    multi_project_documents = bool(documents) and (
        any(file.project_id is None for file, _ in documents)
        or len({file.project_id for file, _ in documents}) > 1
    )

    def replay(turn: ChatTurn):
        if turn.prompt != payload.message or not turn.context or turn.context.get('request') != request_context:
            raise HTTPException(409, "Request identifier already used")
        if turn.context.get("payment_policy_lookup"):
            if payload.project_id is not None:
                principal.require("projects:read", payload.project_id)
        else:
            resolve_documents(db, principal, identifier, payload.project_id, turn.context.get('source_ids', []))
        return {"message": view(turn)[1]}

    if previous := db.scalar(query):
        return replay(previous)
    context = [{"role": item["role"], "content": item["text"][:1000]}
               for item in history(db, identifier, limit=2, principal=principal)["messages"]]
    db.rollback()
    config = request.app.state.config
    used_tool = False

    def record_tool():
        nonlocal used_tool
        used_tool = True
        record("Listing assigned projects")

    document_used = False

    @instrument("documents.inspect", "internal_tool")
    def document_summary():
        nonlocal document_used
        document_used = True
        record("Inspecting accessible spreadsheets")
        actor = current_principal(request, db)
        owned(db, actor, conversation_id)
        documents = resolve_documents(db, actor, identifier, effective_project, effective_ids)
        audit(db, "chat_tool_analyze_documents", owner, resource_type="conversation", resource_id=identifier,
              outcome="success" if documents else "no_visible_documents")
        arabic = any("\u0600" <= character <= "\u06ff" for character in payload.message)
        if not documents:
            return "لا توجد ملفات متاحة في هذه المحادثة." if arabic else "No accessible spreadsheets were found in this conversation. Attach CSV or XLSX files to analyze."
        if multi_project_documents:
            check_integrity(config, documents)
            record("Matched source projects across available project context")
            return render_project_discovery(discover_projects(db, actor, documents))
        import re

        if re.search(r"session|validate|eligib|payment policy|الجلسات|تحقق", payload.message, re.I):
            cutoffs = {}
            cutoffs_ids = {file.project_id for file, _ in documents}
            for project in sorted(cutoffs_ids):
                cutoffs.update(project_report_cutoffs(db, project))
            project_codes = dict(db.execute(select(project_table.c.id, project_table.c.project_code)
                                            .where(project_table.c.id.in_(cutoffs_ids))).all())
            result = session_preview(documents, report_cutoffs=cutoffs, project_codes=project_codes)
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
        for file, spreadsheet in documents:
            # Escape filename punctuation before embedding it in Markdown.
            filename = "".join(
                "\\" + char if char in r"\`*_{}[]<>()#+-.!|~&" else char
                for char in file.original_filename
            )
            lines.append(f"\n**{filename}**")
            lines.append(f"- {'مرجع الملف' if arabic else 'File reference'}: `{file.id}`")
            for sheet in spreadsheet_profile(spreadsheet):
                candidates = sheet["candidate_fields"]
                fields = ", ".join(labels[key] if arabic else key for key in candidates) or ("لا يوجد" if arabic else "none recognized")
                if arabic:
                    lines.append(f"- الورقة {sheet['sheet']}: {sheet['rows']} صفوف مصدر؛ الحقول المقترحة: {fields}.")
                else:
                    lines.append(f"- Sheet {sheet['sheet']}: {sheet['rows']} source rows; candidate fields: {fields}.")
        return "\n".join(lines)


    @instrument("workflow.execute", "internal_tool")
    def execute_workflow(workflow_id):
        db.rollback()
        db.execute(text('BEGIN IMMEDIATE'))
        actor = current_principal(request, db)
        active_conversation = owned(db, actor, conversation_id)
        available = resolve_documents(db, actor, identifier, payload.project_id, selected_ids)
        if any(file.project_id is None for file, _ in available) or len({file.project_id for file, _ in available}) > 1:
            record("Executing guarded global workflow with per-project receipts")
            return run_global_workflow(db, actor, config, active_conversation, available,
                                       workflow_id=workflow_id, request_id=request_id, on_step=record)
        if workflow_id in {'analyze_intake', 'process_activity'}:
            return handle_message(db, actor, config, active_conversation,
                                  'Analyze' if workflow_id == 'analyze_intake' else 'Process',
                                  payload.project_id, selected_ids, request_id)
        project_ids = {file.project_id for file, _ in available}
        project_id = payload.project_id or (next(iter(project_ids)) if len(project_ids) == 1 else None)
        if project_id is None:
            return 'Select the project in Context so I can run the stored workflow. You do not need to specify its steps.'
        run = run_workflow(db, actor, config, workflow_id=workflow_id, project_id=project_id,
                           request_key=f'chat:{identifier}:{request_id}', conversation_id=identifier,
                           document_ids=selected_ids)
        return render_run(run)

    # Conversation control/status never depends on an untrusted model answer.
    db.execute(text('BEGIN IMMEDIATE'))
    principal = current_principal(request, db)
    conversation = owned(db, principal, conversation_id)
    demo_lookup = config.demo_mode and payload.message.strip().casefold().rstrip("?") == "demo payment summary"
    if demo_lookup:
        records = demo_records(db, principal)
        if payload.project_id is not None:
            records = [row for row in records if row["project_id"] == payload.project_id]
        lines = ["DEMO payment summary. All evidence is synthetic."]
        totals = demo_summary(records)
        for currency, values in totals.items():
            lines.append(f"- {currency} {values['calculated']} calculated. "
                         f"Simulated net {values['net']}; outstanding {values['outstanding']}; overpaid {values['overpaid']}.")
        pending = sum(row["status"] == "pending_human_approval" for row in records)
        if pending:
            lines.append(f"{pending} project runs are awaiting human authorization.")
        if not totals:
            lines.append("No demo obligations are visible in this scope.")
        # Do not keep a financial report in chat after its scoped permissions change.
        reply = "\n".join(lines)
        record("Read scoped DEMO payment records")
        document_used = True
    elif policy_lookup:
        if payload.project_id is None:
            from .repositories import visible_projects
            accessible = visible_projects(db, owner)
            if not accessible:
                reply = "No active projects are available."
            else:
                project_ids = [project.id for project in accessible]
                families = dict(db.execute(select(project_table.c.id, project_table.c.policy_family).where(
                    project_table.c.id.in_(project_ids))).all())
                summaries = {
                    "session": "SESSION — USD 25 per complete 3 validated credits; full six-session Trainer/Logistic activity and independent report/approval gates apply",
                    "hours": "HOURS — USD 5/hour; per-shift nearest 30m, monthly whole-hour floor, USD 600/month per verified staff/project, 16 actual hours in any rolling 24h; no overtime or overnight premium",
                }
                reply = "Built-in payment policies for available projects (not editable):\n" + "\n".join(
                    f"- {project.name}: {summaries.get(families.get(project.id), 'unassigned (legacy project)')}"
                    for project in accessible) + "\nCalculation rules do not confer payment eligibility or export approval."
        else:
            principal.require("projects:read", payload.project_id)
            family = db.execute(select(project_table.c.policy_family).where(
                project_table.c.id == payload.project_id
            )).scalar_one_or_none()
            if family == "session":
                reply = "This project uses the fixed session-based policy. Project-specific rate and rule editing is disabled."
            elif family == "hours":
                reply = ("This project uses fixed HOURS rules: USD 5 per hour; nearest 30-minute "
                         "shift rounding, monthly whole-hour flooring, USD 600 per verified staff "
                         "per hours-based project per calendar month; max 16 actual nonoverlapping "
                         "hours in any rolling 24h; no overtime or overnight premium. "
                         "Financial eligibility, source authority and export remain separately gated.")
            else:
                reply = "This legacy project's payment policy type needs administrator review."
        record("Checked project payment policy configuration")
    elif multi_project_documents and STATUS.search(payload.message):
        check_integrity(config, documents)
        reply = global_workflow_status(db, principal, conversation, documents)
        record("Read recorded global project workflow status")
    elif multi_project_documents and choose_workflow(payload.message) in {'analyze_intake', 'process_activity', 'show_issues'}:
        selection = choose_workflow(payload.message)
        reply = run_global_workflow(db, principal, config, conversation, documents,
                                    workflow_id=selection, request_id=request_id, on_step=record)
        record("Recorded guarded per-project workflow steps for global conversation")
        # Persist the actual bounded workflow receipt summary in chat history.
        # Unlike ad-hoc source previews, it is safe and must survive reload.
    else:
        reply = handle_message(db, principal, config, conversation, payload.message, payload.project_id,
                               selected_ids, request_id)
    handled_workflow = reply is not None
    projects = None
    if handled_workflow:
        record("Handled request using saved conversation workflow")
    if reply is None:
        db.rollback()  # Do not hold a SQLite write lock across model inference.
    try:
        if reply is None:
            async with build_ollama_client(config) as client:
                reply, projects = await respond(
                    OllamaAdapter(config, client),
                    [*context, {"role": "user", "content": payload.message}],
                    lambda: visible_projects(db, owner),
                    record_tool,
                    document_summary,
                    workflow=execute_workflow,
                    activity=record,
                )
    except OllamaExtractionError as error:
        record("Local model failed", code=error.code)
        raise HTTPException(503, f"Local assistant unavailable ({error.code})") from None
    principal = current_principal(request, db)
    conversation = owned(db, principal, conversation_id)
    current_scope = (conversation.workflow_state or {}).get('scope', {})
    if handled_workflow and not policy_lookup:
        source_ids = current_scope.get('source_ids', source_ids)
    turn = ChatTurn(conversation_id=identifier, request_id=request_id, prompt=payload.message,
                    reply=("Scoped DEMO lookup requested." if demo_lookup else "Spreadsheet inspection requested.") if document_used else reply, created_at=int(time()),
                    context={"request": request_context, "source_ids": source_ids, "payment_policy_lookup": policy_lookup, "execution_id": current.get().info["id"] if current.get() else None})
    record("Saving conversation response")
    db.add(turn)
    if used_tool:
        audit(db, "chat_tool_list_projects", owner)
    try:
        with span("conversation.commit", "database"):
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
    return history(db, str(conversation_id), principal=principal)
