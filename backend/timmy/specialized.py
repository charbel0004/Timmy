"""Draft prompt evaluators for server-curated inputs, with no operational side effects."""

from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ai import OllamaAdapter, OllamaExtractionError

PROMPTS = {
    "AT-AI-001": "QWEN_TIMESHEET_MAPPING_SYSTEM.md",
    "AT-AI-002": "QWEN_DISCREPANCY_EXPLANATION_SYSTEM.md",
    "AT-AI-003": "QWEN_CLARIFICATION_SYSTEM.md",
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Column(Strict):
    column_index: int = Field(ge=0)
    header: str = Field(max_length=256)
    non_sensitive_examples: list[str] = Field(max_length=3)


class MappingInput(Strict):
    schema_version: Literal["DRAFT-1"] = "DRAFT-1"
    policy_family: Literal["session", "hours"]
    allowed_fields: list[str] = Field(max_length=40)
    columns: list[Column] = Field(max_length=50)
    known_aliases: list[str] = Field(default_factory=list, max_length=50)


class Proposal(Strict):
    column_index: int
    source_header: str
    canonical_field: str
    interpretation: str
    support: str
    uncertainty: Literal["low", "medium", "high"]


class Mapping(Strict):
    schema_version: Literal["DRAFT-1"]
    status: Literal["NEEDS_HUMAN_CONFIRMATION", "BLOCKED"]
    proposals: list[Proposal] = Field(max_length=50)
    unmapped_columns: list[int]
    ambiguities: list[str]
    questions_for_human: list[str]
    suspicious_content_detected: bool


class Issue(Strict):
    issue_id: str
    code: str
    status: str
    evidence_ids: list[str]
    permitted_next_actions: list[str]
    language: Literal["ar", "en"]


class Explanation(Strict):
    issue_id: str
    language: Literal["ar", "en"]
    summary: str
    evidence_ids: list[str]
    uncertainties: list[str]
    human_action_needed: str
    cannot_resolve_automatically: bool


class Missing(Strict):
    missing_fields: list[str] = Field(min_length=1, max_length=30)
    context: str = Field(max_length=1000)
    language: Literal["ar", "en"]


class Question(Strict):
    field: str
    question: str
    reason: str


class Clarification(Strict):
    status: Literal["CLARIFICATION_REQUIRED", "BLOCKED"]
    questions: list[Question] = Field(max_length=30)
    missing_fields: list[str]
    assumptions_used: list[str] = Field(max_length=0)


def load_prompt(identifier: str) -> tuple[str, str]:
    path = Path(__file__).resolve().parents[2] / "docs" / "ai" / PROMPTS[identifier]
    document = path.read_text(encoding="utf-8")
    section = document.split("## SYSTEM MESSAGE", 1)[1].split("\n", 1)[1]
    system = section.split("\n## ", 1)[0].strip()
    return system, sha256(document.encode()).hexdigest()


async def evaluate(adapter: OllamaAdapter, identifier: str, data: Strict, schema):
    system, _ = load_prompt(identifier)
    payload = data.model_dump_json()
    if len(payload) > 8000:
        raise ValueError("Draft prompt input exceeds limit")
    return await adapter.structured([
        {"role": "system", "content": system}, {"role": "user", "content": payload},
    ], schema)


async def propose_mapping(adapter: OllamaAdapter, data: MappingInput) -> Mapping:
    columns = {column.column_index: column.header for column in data.columns}
    ensure(len(columns) == len(data.columns))
    result = await evaluate(adapter, "AT-AI-001", data, Mapping)
    ensure(not result.proposals or (result.status != "BLOCKED" and not result.suspicious_content_detected))
    ensure(set(result.unmapped_columns) <= columns.keys())
    ensure(len({item.canonical_field for item in result.proposals}) == len(result.proposals))
    ensure(len({item.column_index for item in result.proposals}) == len(result.proposals))
    for item in result.proposals:
        ensure(columns.get(item.column_index) == item.source_header and item.canonical_field in data.allowed_fields)
        ensure(data.policy_family != "session" or item.canonical_field not in {
            "start_datetime", "end_datetime", "duration_hours",
        })
    return result


async def explain_issue(adapter: OllamaAdapter, data: Issue) -> Explanation:
    result = await evaluate(adapter, "AT-AI-002", data, Explanation)
    ensure(result.issue_id == data.issue_id and result.language == data.language)
    ensure(set(result.evidence_ids) <= set(data.evidence_ids))
    ensure(bool(data.evidence_ids) or result.cannot_resolve_automatically)
    return result


async def clarify_missing(adapter: OllamaAdapter, data: Missing) -> Clarification:
    result = await evaluate(adapter, "AT-AI-003", data, Clarification)
    ensure(result.missing_fields == data.missing_fields)
    ensure(all(question.field in data.missing_fields for question in result.questions))
    return result


def ensure(condition: bool) -> None:
    if not condition:
        raise OllamaExtractionError("schema_validation")
