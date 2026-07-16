"""Legacy scheduled discovery entrypoint, fail-closed during Round 15.

Round 15 grants source eligibility but intentionally does not bind a production
executor and target to a versioned connector definition/configuration.  The
legacy MEM configuration therefore cannot borrow authority from an unrelated
V2 connector and this entrypoint schedules nothing.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.observability import SOURCE_PRODUCTION_SCHEDULING_BLOCKED


async def run_scheduled_mem_discovery(settings: Settings) -> dict[str, object]:
    engine = create_database_engine(settings)
    try:
        connectors = await _enabled_mem_connectors(engine)
        return {"connector_count": len(connectors), "runs": []}
    finally:
        await engine.dispose()


async def _enabled_mem_connectors(engine: AsyncEngine) -> list[dict[str, object]]:
    # Keep the parameter so the worker entrypoint remains stable, but never query
    # legacy targets until definition + config + executor + target are one reviewed
    # production binding. Dynamic production scheduling is outside Round 15.
    del engine
    reason = "executor_binding_unavailable"
    SOURCE_PRODUCTION_SCHEDULING_BLOCKED.labels(reason).inc()
    logging.getLogger("srbg.worker.safety_regulations").info(
        "source_production_scheduling_blocked",
        extra={
            "event_name": "source_production_scheduling_blocked",
            "action": "SCHEDULE_SOURCE",
            "outcome": "BLOCKED",
            "reason_code": reason.upper(),
        },
    )
    return []
