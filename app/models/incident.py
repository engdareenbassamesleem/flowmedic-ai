import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    workflow_id: Mapped[str] = mapped_column(String(255))
    workflow_name: Mapped[str] = mapped_column(String(1000))
    failed_node: Mapped[str | None] = mapped_column(String(1000))
    error_type: Mapped[str] = mapped_column(String(1000))
    error_message: Mapped[str] = mapped_column(Text)
    execution_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")
    severity: Mapped[str] = mapped_column(String(20))
    diagnosis: Mapped[dict | None] = mapped_column(JSON)
    diagnosis_provider: Mapped[str | None] = mapped_column(String(50))
