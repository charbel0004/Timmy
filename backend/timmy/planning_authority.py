"""Typed boundary for a server-registered authoritative planning source."""
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApprovedActivity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_code: str = Field(min_length=1, max_length=80)
    activity_code: str = Field(min_length=1, max_length=200)
    approved_start_date: date
    approved_end_date: date
    version: str = Field(min_length=1, max_length=200)
    evidence_ref: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_window(self):
        if self.approved_end_date < self.approved_start_date:
            raise ValueError("Approved planning window ends before it starts")
        return self


class PlanningProvider(Protocol):
    """An MCP-backed implementation must be bound to an approved server and tool."""

    source: str

    def approved_activities(self, project_code: str) -> list[ApprovedActivity]: ...
