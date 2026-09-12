from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=2000)
    probable_root_cause: str = Field(min_length=1, max_length=2000)
    affected_component: str = Field(min_length=1, max_length=1000)
    recommended_fix: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    risk_level: Literal["low", "medium", "high"]


class Failure(BaseModel):
    workflow_id: str
    workflow_name: str
    execution_id: str
    failed_node: str | None = None
    error_type: str
    error_message: str
    execution_timestamp: datetime | None = None
    severity: Literal["medium", "high"] = "medium"


class IncidentOut(Failure):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: Literal["open", "diagnosed"]
    diagnosis: Diagnosis | None = None
    diagnosis_provider: str | None = None


class Workflow(BaseModel):
    id: str
    name: str
    active: bool


class WorkflowPage(BaseModel):
    data: list[Workflow]
    next_cursor: str | None = None


class FailurePage(BaseModel):
    data: list[Failure]
    next_cursor: str | None = None


class IncidentPage(BaseModel):
    data: list[IncidentOut]


class SyncResult(BaseModel):
    scanned: int
    created: int
    next_cursor: str | None = None


class DemoInfo(BaseModel):
    mode: Literal["synthetic"]
    incident_id: str
    diagnosis_provider: Literal["mock"]
    note: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
