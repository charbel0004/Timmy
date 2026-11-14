from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)


class SessionView(BaseModel):
    username: str
    role: str
    permissions: list[str]
    project_permissions: dict[int, list[str]]
    csrf_token: str
    demo_mode: bool
    must_change_password: bool


class ProjectView(BaseModel):
    id: int
    name: str


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_column: str | None
    source_text: str | None
    normalized_value: str | None
    status: Literal["clear", "missing", "uncertain"]

    @property
    def source(self) -> str | None:
        return self.source_text

    @property
    def normalized(self) -> str | None:
        return self.normalized_value


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    volunteer: ExtractedField
    activity: ExtractedField
    date: ExtractedField
    hours: ExtractedField
    sessions: ExtractedField

    @property
    def requires_review(self) -> bool:
        def clear(field: ExtractedField) -> bool:
            return field.status == "clear" and bool(
                field.source_column and field.source_text and field.normalized_value
            )

        return (
            not all(clear(field) for field in (self.volunteer, self.activity, self.date))
            or not any(clear(field) for field in (self.hours, self.sessions))
            or any(field.status == "uncertain" for field in (self.hours, self.sessions))
        )


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_row: dict[str, str]
    extracted: Extraction
    requires_review: bool
    review_issues: dict[str, list[str]] = Field(default_factory=dict)
