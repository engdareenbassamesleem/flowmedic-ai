"""Synthetic data used only to make the public demo runnable without credentials."""

from datetime import UTC, datetime

from app.schemas.domain import Failure

DEMO_EXECUTION_ID = "demo-execution-auth-401"


def demo_failure() -> Failure:
    """Return a fixed, non-sensitive failure that exercises the diagnosis flow."""
    return Failure(
        workflow_id="demo-order-import",
        workflow_name="Demo order import",
        execution_id=DEMO_EXECUTION_ID,
        failed_node="Fetch orders",
        error_type="NodeApiError",
        error_message="401 Unauthorized from a simulated upstream service.",
        execution_timestamp=datetime(2026, 9, 9, 8, 0, tzinfo=UTC),
        severity="medium",
    )
