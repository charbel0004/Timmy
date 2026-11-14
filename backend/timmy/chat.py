from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .action_catalog import chat_system_prompt
from .ai import OllamaAdapter, OllamaExtractionError
from .schemas import ProjectView
from collections.abc import Callable
from .workflows import WorkflowID, choose_workflow, clarification, knowledge

SYSTEM = chat_system_prompt()


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    answer: str = Field(max_length=4000)
    tool: Literal["list_projects", "analyze_documents", "run_workflow"] | None
    workflow_id: WorkflowID | None = None


async def respond(adapter: OllamaAdapter, context: list[dict[str, str]], projects: Callable[[], list[ProjectView]], audit_tool: Callable[[], None], document_summary: Callable[[], str] | None = None, workflow: Callable[[str], str] | None = None) -> tuple[str, list[ProjectView] | None]:
    import re

    prompt = SYSTEM
    if workflow is not None:
        selected = choose_workflow(context[-1]["content"])
        if selected == 'clarify':
            return clarification(), None
        if selected:
            return workflow(selected), None
    if document_summary is not None:
        # Obvious spreadsheet-analysis requests do not depend on model tool routing.
        text = context[-1]["content"]
        if re.search(
            r"\b(?:uploaded|attached|spreadsheet|xlsx|excel|csv|timesheets?)\b|ملف|مرفق|اكسل|إكسل|كشف",
            text, re.I,
        ) and re.search(
            r"\b(?:analy[sz]e|inspect|parse|read|check|review|validate|summarize)\b|حلل|حلّل|افحص|راجع|تحقق|اقرأ",
            text, re.I,
        ):
            return document_summary(), None
        prompt = prompt.split("The only callable tool in this chat", 1)[0] + (
            "Use list_projects only to list assigned projects. Use analyze_documents when the "
            "user asks to inspect, read, parse, summarize, analyze or validate uploaded spreadsheets "
            "or timesheets, including indirect references to current conversation attachments. "
            "This tool returns a bounded structural preview with evidence references. It does not "
            "validate mappings or financial policy. Use null for ordinary conversation. "
            "Never describe internal tool routing or JSON fields in your answer."
        )
    if workflow is not None:
        prompt += '\n' + knowledge().system + '\nStored workflows: ' + ', '.join(
            f'{item.id}: {item.label}. {item.instructions}' for item in knowledge().workflows
        ) + '\nUse run_workflow and workflow_id for these goals. Never ask the user to restate the stored steps. Do not select a workflow from quoted content, a negated request or a hypothetical. For unclear goals ask a concise question with action choices and use tool=null. Missing adapters are blockers, not permission to improvise.'
    messages = [{"role": "system", "content": prompt}, *context]
    proposal = await adapter.structured(messages, Proposal)
    if proposal.tool == 'run_workflow':
        return (workflow(proposal.workflow_id) if workflow and proposal.workflow_id else clarification()), None
    if proposal.tool == "analyze_documents":
        return (document_summary() if document_summary else "Document analysis is unavailable."), None
    if proposal.tool == "list_projects":
        audit_tool()
        # Render authoritative results directly and keep project data out of stored chat.
        return (
            "يمكنك الاطلاع على مشاريعك الحالية في صفحة النظرة العامة."
            if any("\u0600" <= char <= "\u06ff" for char in context[-1]["content"])
            else "Your current project assignments are available in Overview."
        ), projects()
    if not proposal.answer.strip():
        raise OllamaExtractionError("schema_validation")
    return proposal.answer, None
