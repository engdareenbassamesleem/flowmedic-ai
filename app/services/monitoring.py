import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime

from app.core.errors import ServiceError
from app.integrations.n8n.client import Execution, is_failed
from app.repositories.incidents import IncidentRepository
from app.repositories.monitoring import ExecutionHistoryRepository, MonitoringRepository
from app.schemas.domain import MonitoringStatus, MonitoringSyncResult
from app.services.incidents import normalize

logger = logging.getLogger(__name__)
SOURCE = "n8n"
SOURCE_IDENTIFIER = "default"
TRANSIENT_CODES = {
    "n8n_timeout",
    "n8n_unreachable",
    "n8n_rate_limited",
    "n8n_server_error",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def execution_success(status: str | None) -> bool | None:
    if status == "success":
        return True
    if status in {"error", "crashed"}:
        return False
    return None


class MonitoringService:
    """One read-only polling task per FastAPI application instance."""

    def __init__(self, settings, session_factory, n8n):
        self.settings = settings
        self.session_factory = session_factory
        self.n8n = n8n
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._state = "disabled" if not self.enabled else "idle"
        self._stopping = False

    @property
    def enabled(self) -> bool:
        return bool(
            not self.settings.demo_mode
            and self.settings.n8n_base_url
            and self.settings.n8n_api_key.get_secret_value()
        )

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._loop(), name="flowmedic-monitor")
        logger.info(
            "monitoring_loop_started interval_seconds=%s",
            self.settings.monitor_poll_interval_seconds,
        )

    async def stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        logger.info("monitoring_loop_stopped")

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(self.settings.monitor_poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            await self.sync()

    def status(self) -> MonitoringStatus:
        with self.session_factory() as session:
            checkpoint = MonitoringRepository(session).existing_checkpoint(
                SOURCE, SOURCE_IDENTIFIER
            )
            return MonitoringStatus(
                enabled=self.enabled,
                state="disabled" if not self.enabled else self._state,
                poll_interval_seconds=self.settings.monitor_poll_interval_seconds,
                last_checked_at=checkpoint.last_checked_at if checkpoint else None,
                last_successful_sync_at=checkpoint.last_successful_sync_at if checkpoint else None,
                last_error_at=checkpoint.last_error_at if checkpoint else None,
                last_error_summary=checkpoint.last_error_summary if checkpoint else None,
                consecutive_failure_count=checkpoint.consecutive_failure_count if checkpoint else 0,
            )

    async def sync(self) -> MonitoringSyncResult:
        if not self.enabled:
            return MonitoringSyncResult(status="disabled")
        if self._lock.locked():
            return MonitoringSyncResult(status="skipped")
        async with self._lock:
            was_degraded = self._state == "degraded"
            self._state = "running"
            logger.info("monitoring_poll_started")
            try:
                result = await self._sync_with_retries()
            except ServiceError as exc:
                self._record_failure(exc)
                self._state = "degraded"
                logger.warning("monitoring_poll_failed code=%s", exc.code)
                return MonitoringSyncResult(status="failed")
            except Exception:
                # Keep monitoring failures isolated from the API process and avoid logging payloads.
                self._record_failure(
                    ServiceError("monitoring_error", "Monitoring poll failed", 503)
                )
                self._state = "degraded"
                logger.exception("monitoring_poll_failed code=monitoring_error")
                return MonitoringSyncResult(status="failed")
            self._record_success()
            self._state = "idle"
            if was_degraded:
                logger.info("monitoring_recovered")
            logger.info(
                (
                    "monitoring_poll_completed executions_discovered=%s "
                    "history_records_created=%s incidents_created=%s"
                ),
                result.executions_discovered,
                result.history_records_created,
                result.incidents_created,
            )
            return result

    async def _sync_with_retries(self) -> MonitoringSyncResult:
        for attempt in range(self.settings.monitor_max_retries + 1):
            try:
                return await self._sync_page()
            except ServiceError as exc:
                if exc.code not in TRANSIENT_CODES or attempt >= self.settings.monitor_max_retries:
                    raise
                delay = self.settings.monitor_retry_base_seconds * (2**attempt)
                logger.warning(
                    "monitoring_retry attempt=%s delay_seconds=%s code=%s",
                    attempt + 1,
                    delay,
                    exc.code,
                )
                await asyncio.sleep(delay)
        raise ServiceError("monitoring_error", "Monitoring poll failed", 503)

    async def _sync_page(self) -> MonitoringSyncResult:
        with self.session_factory() as session:
            checkpoint = MonitoringRepository(session).existing_checkpoint(
                SOURCE, SOURCE_IDENTIFIER
            )
            cursor = checkpoint.cursor_value if checkpoint is not None else None
        page = await self.n8n.recent_executions(self.settings.monitor_page_size, cursor)
        with self.session_factory() as session:
            checkpoints = MonitoringRepository(session)
            checkpoint = checkpoints.checkpoint(SOURCE, SOURCE_IDENTIFIER)
            history = ExecutionHistoryRepository(session)
            incidents = IncidentRepository(session)
            created_history = 0
            created_incidents = 0
            last_execution_id = None
            secrets = self._secrets()
            for execution in page.data:
                detail = execution
                if execution.status is None or is_failed(execution):
                    detail = await self.n8n.execution_details(execution.id)
                workflow_name = self._workflow_name(detail)
                record, inserted = history.create_once(
                    source=SOURCE,
                    workflow_id=detail.workflowId,
                    workflow_name=workflow_name,
                    execution_id=detail.id,
                    execution_status=detail.status,
                    recorded_at=utc_now(),
                    started_at=detail.startedAt,
                    stopped_at=detail.stoppedAt,
                    is_success=execution_success(detail.status),
                )
                created_history += int(inserted)
                if is_failed(detail):
                    incident, created = incidents.create_once(normalize(detail, secrets))
                    history.attach_incident(record, incident.id)
                    created_incidents += int(created)
                last_execution_id = detail.id
            now = utc_now()
            checkpoint.cursor_value = page.nextCursor
            checkpoint.last_execution_id = last_execution_id or checkpoint.last_execution_id
            checkpoint.last_checked_at = now
            checkpoint.last_successful_sync_at = now
            checkpoint.last_error_at = None
            checkpoint.last_error_summary = None
            checkpoint.consecutive_failure_count = 0
            checkpoint.updated_at = now
            session.commit()
            if not page.data:
                logger.info("monitoring_no_new_data")
            else:
                logger.info("monitoring_executions_discovered count=%s", len(page.data))
            return MonitoringSyncResult(
                status="completed",
                executions_discovered=len(page.data),
                history_records_created=created_history,
                incidents_created=created_incidents,
                next_cursor=page.nextCursor,
            )

    def _record_success(self) -> None:
        # _sync_page persisted timestamps; this remains a deliberate lifecycle hook.
        return None

    def _record_failure(self, error: ServiceError) -> None:
        with self.session_factory() as session:
            checkpoint = MonitoringRepository(session).checkpoint(SOURCE, SOURCE_IDENTIFIER)
            now = utc_now()
            checkpoint.last_checked_at = now
            checkpoint.last_error_at = now
            checkpoint.last_error_summary = error.message[:500]
            checkpoint.consecutive_failure_count += 1
            checkpoint.updated_at = now
            session.commit()

    def _secrets(self) -> tuple[str, ...]:
        return tuple(
            key.get_secret_value()
            for key in (
                self.settings.n8n_api_key,
                self.settings.ai_api_key,
                self.settings.flowmedic_api_key,
            )
        )

    @staticmethod
    def _workflow_name(execution: Execution) -> str:
        value = (execution.workflowData or {}).get("name")
        return value if isinstance(value, str) and value else "Unknown workflow"
