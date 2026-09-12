from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.core.security import sanitize
from app.models.incident import ExecutionHistory, Incident
from app.repositories.incidents import IncidentRepository
from app.schemas.domain import (
    DemoInfo,
    Failure,
    FailurePage,
    IncidentOut,
    IncidentPage,
    MonitoringStatus,
    MonitoringSyncResult,
    OverviewMetrics,
    SyncResult,
    SystemStatus,
    Workflow,
    WorkflowHealth,
    WorkflowHealthPage,
    WorkflowPage,
)
from app.services.health import build_workflow_health, global_recent_counts
from app.services.incidents import normalize

router = APIRouter(prefix="/api/v1")
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=2048)]


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


DB = Annotated[Session, Depends(get_session)]


def secrets(request):
    config = request.app.state.settings
    return tuple(
        key.get_secret_value()
        for key in (
            config.n8n_api_key,
            config.ai_api_key,
            config.flowmedic_api_key,
        )
    )


@router.get("/n8n/status")
async def n8n_status(request: Request) -> dict[str, bool]:
    return await request.app.state.n8n.connectivity()


@router.get("/system/status", response_model=SystemStatus)
def system_status(request: Request) -> SystemStatus:
    config = request.app.state.settings
    database_engine = config.database_url.split(":", 1)[0].lower()
    return SystemStatus(
        n8n_configured=bool(config.n8n_base_url and config.n8n_api_key.get_secret_value()),
        ai_mode="configured" if config.ai_api_key.get_secret_value() else "mock",
        database_engine=database_engine,
    )


@router.get("/monitoring/status", response_model=MonitoringStatus)
def monitoring_status(request: Request) -> MonitoringStatus:
    return request.app.state.monitoring.status()


@router.post("/monitoring/sync", response_model=MonitoringSyncResult)
async def monitoring_sync(request: Request) -> MonitoringSyncResult:
    return await request.app.state.monitoring.sync()


def workflow_health_rows(session: Session) -> list[WorkflowHealth]:
    history = session.scalars(select(ExecutionHistory)).all()
    incidents = session.scalars(select(Incident)).all()
    return build_workflow_health(history, incidents)


@router.get("/metrics/overview", response_model=OverviewMetrics)
def overview_metrics(request: Request, session: DB) -> OverviewMetrics:
    workflows = workflow_health_rows(session)
    successes, failures = global_recent_counts(session.scalars(select(ExecutionHistory)).all())
    monitoring = request.app.state.monitoring.status()
    return OverviewMetrics(
        monitored_workflow_count=len(workflows),
        healthy_workflow_count=sum(item.health == "healthy" for item in workflows),
        degraded_workflow_count=sum(item.health == "degraded" for item in workflows),
        unhealthy_workflow_count=sum(item.health == "unhealthy" for item in workflows),
        unknown_workflow_count=sum(item.health == "unknown" for item in workflows),
        open_incident_count=sum(
            item.status == "open" for item in session.scalars(select(Incident)).all()
        ),
        recent_failure_count=failures,
        recent_success_count=successes,
        last_successful_monitoring_sync_at=monitoring.last_successful_sync_at,
        monitoring=monitoring,
    )


@router.get("/metrics/workflows", response_model=WorkflowHealthPage)
def workflow_metrics(session: DB) -> WorkflowHealthPage:
    return WorkflowHealthPage(data=workflow_health_rows(session))


@router.get("/workflows/{workflow_id}/health", response_model=WorkflowHealth)
def workflow_health(workflow_id: str, session: DB) -> WorkflowHealth:
    if len(workflow_id) > 255:
        raise ServiceError("workflow_not_found", "Workflow health was not found", 404)
    for health in workflow_health_rows(session):
        if health.workflow_id == workflow_id:
            return health
    raise ServiceError("workflow_not_found", "Workflow health was not found", 404)


@router.get("/workflows", response_model=WorkflowPage)
async def workflows(request: Request, limit: Limit = 50, cursor: Cursor = None):
    page = await request.app.state.n8n.workflows(limit, cursor)
    return WorkflowPage(
        data=[
            Workflow(
                id=w.id,
                name=sanitize(w.name, secrets(request)),
                active=w.active,
            )
            for w in page.data
        ],
        next_cursor=page.nextCursor,
    )


@router.get("/executions/failed", response_model=FailurePage)
async def failed_executions(request: Request, limit: Limit = 50, cursor: Cursor = None):
    failures, next_cursor, _ = await request.app.state.n8n.failed_executions(limit, cursor)
    return FailurePage(
        data=[normalize(item, secrets(request)) for item in failures],
        next_cursor=next_cursor,
    )


@router.post("/incidents/sync", response_model=SyncResult)
async def sync_incidents(request: Request, session: DB, limit: Limit = 50, cursor: Cursor = None):
    failures, next_cursor, scanned = await request.app.state.n8n.failed_executions(limit, cursor)
    repository = IncidentRepository(session)
    created = 0
    for item in failures:
        _, inserted = repository.create_once(normalize(item, secrets(request)))
        created += int(inserted)
    session.commit()
    return SyncResult(scanned=scanned, created=created, next_cursor=next_cursor)


@router.get("/demo", response_model=DemoInfo)
def demo_info(request: Request):
    if not request.app.state.settings.demo_mode:
        raise ServiceError("demo_not_enabled", "Demo mode is disabled", 404)
    return DemoInfo(
        mode="synthetic",
        incident_id=request.app.state.demo_incident_id,
        diagnosis_provider="mock",
        note="Synthetic data only; no n8n instance or AI provider was contacted.",
    )


@router.get("/incidents", response_model=IncidentPage)
def incidents(session: DB, limit: Limit = 50, offset: Annotated[int, Query(ge=0)] = 0):
    return IncidentPage(data=IncidentRepository(session).list(limit, offset))


def require_incident(session, incident_id):
    incident = IncidentRepository(session).get(str(incident_id))
    if incident is None:
        raise ServiceError("incident_not_found", "Incident was not found", 404)
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
def incident(incident_id: UUID, session: DB):
    return require_incident(session, incident_id)


@router.post("/incidents/{incident_id}/diagnose", response_model=IncidentOut)
async def diagnose(incident_id: UUID, request: Request, session: DB):
    incident = require_incident(session, incident_id)
    context = Failure.model_validate(incident, from_attributes=True)
    provider = request.app.state.provider
    diagnosis = await provider.diagnose(context)
    incident.diagnosis = diagnosis.model_dump()
    incident.diagnosis_provider = provider.name
    incident.status = "diagnosed"
    session.commit()
    return incident
