from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.incident import ExecutionHistory, MonitoringCheckpoint


def utc_now() -> datetime:
    return datetime.now(UTC)


class MonitoringRepository:
    def __init__(self, session: Session):
        self.session = session

    def checkpoint(self, source: str, source_identifier: str) -> MonitoringCheckpoint:
        checkpoint = self.session.scalar(
            select(MonitoringCheckpoint).where(
                MonitoringCheckpoint.source == source,
                MonitoringCheckpoint.source_identifier == source_identifier,
            )
        )
        if checkpoint is not None:
            return checkpoint
        now = utc_now()
        checkpoint = MonitoringCheckpoint(
            source=source,
            source_identifier=source_identifier,
            created_at=now,
            updated_at=now,
        )
        try:
            with self.session.begin_nested():
                self.session.add(checkpoint)
                self.session.flush()
        except IntegrityError:
            checkpoint = self.session.scalar(
                select(MonitoringCheckpoint).where(
                    MonitoringCheckpoint.source == source,
                    MonitoringCheckpoint.source_identifier == source_identifier,
                )
            )
            if checkpoint is None:
                raise
        return checkpoint

    def existing_checkpoint(
        self, source: str, source_identifier: str
    ) -> MonitoringCheckpoint | None:
        return self.session.scalar(
            select(MonitoringCheckpoint).where(
                MonitoringCheckpoint.source == source,
                MonitoringCheckpoint.source_identifier == source_identifier,
            )
        )


class ExecutionHistoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_once(self, **values) -> tuple[ExecutionHistory, bool]:
        existing = self.session.scalar(
            select(ExecutionHistory).where(
                ExecutionHistory.source == values["source"],
                ExecutionHistory.execution_id == values["execution_id"],
            )
        )
        if existing is not None:
            return existing, False
        history = ExecutionHistory(**values)
        try:
            with self.session.begin_nested():
                self.session.add(history)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(ExecutionHistory).where(
                    ExecutionHistory.source == values["source"],
                    ExecutionHistory.execution_id == values["execution_id"],
                )
            )
            if existing is None:
                raise
            return existing, False
        return history, True

    def attach_incident(self, history: ExecutionHistory, incident_id: str) -> None:
        if history.incident_id is None:
            history.incident_id = incident_id
