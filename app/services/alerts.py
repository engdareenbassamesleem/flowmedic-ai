import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.incident import ExecutionHistory, Incident
from app.repositories.alerts import (
    AlertConditionStateRepository,
    AlertEventRepository,
    AlertRuleRepository,
)
from app.services.health import build_workflow_health

logger = logging.getLogger(__name__)

TRIGGER_NEW_INCIDENT = "new_incident"
TRIGGER_WORKFLOW_UNHEALTHY = "workflow_unhealthy"
TRIGGER_MONITORING_DEGRADED = "monitoring_degraded"


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class DeliveryPayload:
    event_id: str
    trigger_type: str
    incident_id: str | None
    workflow_id: str | None


class AlertDeliveryProvider:
    """Future delivery adapters must keep this boundary free of raw incident payloads."""

    name = "provider"

    def deliver(self, payload: DeliveryPayload) -> None:
        raise NotImplementedError


class MockAlertDeliveryProvider(AlertDeliveryProvider):
    """Local-only provider used for tests and safe development; it sends nothing externally."""

    name = "mock"

    def deliver(self, payload: DeliveryPayload) -> None:
        logger.info(
            "alert_mock_delivered event_id=%s trigger_type=%s",
            payload.event_id,
            payload.trigger_type,
        )


class AlertService:
    def __init__(self, settings, session_factory, provider: AlertDeliveryProvider | None = None):
        self.settings = settings
        self.session_factory = session_factory
        self.provider = provider or MockAlertDeliveryProvider()

    @property
    def enabled(self) -> bool:
        return not self.settings.demo_mode

    def on_new_incident(self, incident_id: str, workflow_id: str) -> int:
        return self._trigger(
            TRIGGER_NEW_INCIDENT,
            deduplication_key=f"incident:{incident_id}",
            incident_id=incident_id,
            workflow_id=workflow_id,
        )

    def evaluate_workflow_health(self) -> int:
        if not self.enabled:
            return 0
        with self.session_factory() as session:
            histories = session.scalars(select(ExecutionHistory)).all()
            incidents = session.scalars(select(Incident)).all()
            health_rows = build_workflow_health(histories, incidents)
            states = AlertConditionStateRepository(session)
            unhealthy_workflows = []
            for row in health_rows:
                changed = states.transition(
                    TRIGGER_WORKFLOW_UNHEALTHY,
                    row.workflow_id,
                    row.health,
                )
                if changed and row.health == "unhealthy":
                    unhealthy_workflows.append(row.workflow_id)
            session.commit()
        return sum(
            self._trigger(
                TRIGGER_WORKFLOW_UNHEALTHY,
                deduplication_key=f"workflow:{workflow_id}:unhealthy",
                workflow_id=workflow_id,
            )
            for workflow_id in unhealthy_workflows
        )

    def evaluate_monitoring_state(self, state: str) -> int:
        if not self.enabled:
            return 0
        with self.session_factory() as session:
            changed = AlertConditionStateRepository(session).transition(
                TRIGGER_MONITORING_DEGRADED,
                "n8n:default",
                state,
            )
            session.commit()
        if changed and state == "degraded":
            return self._trigger(
                TRIGGER_MONITORING_DEGRADED,
                deduplication_key="monitoring:n8n:default:degraded",
            )
        return 0

    def _trigger(
        self,
        trigger_type: str,
        *,
        deduplication_key: str,
        incident_id: str | None = None,
        workflow_id: str | None = None,
    ) -> int:
        if not self.enabled:
            return 0
        created_event_ids: list[str] = []
        now = utc_now()
        with self.session_factory() as session:
            rules = AlertRuleRepository(session).enabled_for(trigger_type)
            events = AlertEventRepository(session)
            for rule in rules:
                if events.in_cooldown(rule.id, deduplication_key, now) is not None:
                    continue
                event_key = self._event_key(rule.id, deduplication_key, now, rule.cooldown_seconds)
                event, created = events.create_once(
                    rule_id=rule.id,
                    trigger_type=trigger_type,
                    event_key=event_key,
                    deduplication_key=deduplication_key,
                    incident_id=incident_id,
                    workflow_id=workflow_id,
                    status="pending",
                    cooldown_until=now + timedelta(seconds=rule.cooldown_seconds),
                    last_error_summary=None,
                    created_at=now,
                    delivered_at=None,
                )
                if created:
                    created_event_ids.append(event.id)
            session.commit()
        for event_id in created_event_ids:
            self.deliver(event_id)
        return len(created_event_ids)

    def deliver(self, event_id: str) -> None:
        if not self.enabled:
            return
        with self.session_factory() as session:
            existing_attempts = AlertEventRepository(session).attempt_count(event_id)
        for attempt_number in range(
            existing_attempts + 1,
            self.settings.alert_max_retries + 1,
        ):
            with self.session_factory() as session:
                events = AlertEventRepository(session)
                event = events.get(event_id)
                if event is None or event.status == "delivered":
                    return
                attempt = events.create_attempt(
                    alert_event_id=event.id,
                    provider=self.provider.name,
                    attempt_number=attempt_number,
                    status="pending",
                    error_summary=None,
                    started_at=utc_now(),
                    completed_at=None,
                )
                session.commit()
                attempt_id = attempt.id
                payload = DeliveryPayload(
                    event_id=event.id,
                    trigger_type=event.trigger_type,
                    incident_id=event.incident_id,
                    workflow_id=event.workflow_id,
                )
            try:
                self.provider.deliver(payload)
            except Exception:
                with self.session_factory() as session:
                    event = AlertEventRepository(session).get(event_id)
                    attempt = AlertEventRepository(session).attempt(attempt_id)
                    if event is None or attempt is None:
                        return
                    attempt.status = "failed"
                    attempt.error_summary = "Alert delivery provider failed"
                    attempt.completed_at = utc_now()
                    event.status = "failed"
                    event.last_error_summary = "Alert delivery provider failed"
                    session.commit()
                logger.warning(
                    "alert_delivery_failed event_id=%s attempt=%s", event_id, attempt_number
                )
                continue
            with self.session_factory() as session:
                event = AlertEventRepository(session).get(event_id)
                attempt = AlertEventRepository(session).attempt(attempt_id)
                if event is None or attempt is None:
                    return
                attempt.status = "delivered"
                attempt.completed_at = utc_now()
                event.status = "delivered"
                event.delivered_at = attempt.completed_at
                event.last_error_summary = None
                session.commit()
            logger.info("alert_delivery_completed event_id=%s attempt=%s", event_id, attempt_number)
            return

    @staticmethod
    def _event_key(
        rule_id: str, deduplication_key: str, now: datetime, cooldown_seconds: int
    ) -> str:
        window_start = int(now.timestamp()) // cooldown_seconds
        value = f"{rule_id}:{deduplication_key}:{window_start}".encode()
        return hashlib.sha256(value).hexdigest()
