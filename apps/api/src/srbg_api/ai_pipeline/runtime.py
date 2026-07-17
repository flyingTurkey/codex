"""Bounded physical-call orchestration for one logical AI step."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from srbg_api.ai_pipeline.contracts import ModelRequest
from srbg_api.ai_pipeline.gateway import ModelOutputRejected, TransientProviderError

TransientModelError = TransientProviderError


class AttemptKind(StrEnum):
    PRIMARY = "PRIMARY"
    NETWORK_RETRY = "NETWORK_RETRY"
    REPAIR = "REPAIR"


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    number: int
    kind: AttemptKind
    error_code: str | None


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class StepExecutionResult[T]:
    value: T
    attempts: tuple[AttemptRecord, ...]


class ResilientStepExecutor[T]:
    def __init__(
        self,
        invoke: Callable[[ModelRequest], Awaitable[T]],
        *,
        backoff_seconds: float = 0.25,
    ) -> None:
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative")
        self._invoke = invoke
        self._backoff_seconds = backoff_seconds

    async def execute(self, request: ModelRequest) -> StepExecutionResult[T]:
        attempts: list[AttemptRecord] = []
        network_retries = 0
        repair_used = False
        current = request
        kind = AttemptKind.PRIMARY
        while True:
            number = len(attempts) + 1
            try:
                value = await self._invoke(current)
                attempts.append(AttemptRecord(number, kind, None))
                return StepExecutionResult(value=value, attempts=tuple(attempts))
            except (TransientModelError, TimeoutError):
                attempts.append(AttemptRecord(number, kind, "NETWORK_TRANSIENT"))
                if network_retries >= 2:
                    raise
                network_retries += 1
                kind = AttemptKind.NETWORK_RETRY
                if self._backoff_seconds:
                    await asyncio.sleep(self._backoff_seconds * network_retries)
            except ModelOutputRejected as error:
                error_code = _repair_code(error)
                attempts.append(AttemptRecord(number, kind, error_code))
                if repair_used or error_code is None:
                    raise
                repair_used = True
                kind = AttemptKind.REPAIR
                current = request.model_copy(
                    update={
                        "user_prompt": request.user_prompt
                        + "\n<controlled_repair>Return one valid JSON object. Error code: "
                        + error_code
                        + ".</controlled_repair>"
                    }
                )


def _repair_code(error: ModelOutputRejected) -> str | None:
    message = str(error).casefold()
    mapping = (
        ("invalid json", "INVALID_JSON"),
        ("empty content", "EMPTY_CONTENT"),
        ("finish_reason=length", "OUTPUT_LENGTH"),
        ("json schema", "SCHEMA_INVALID"),
        ("step contract", "PYDANTIC_INVALID"),
        ("evidence", "EVIDENCE_INVALID"),
        ("source block", "EXCERPT_INVALID"),
        ("bidirectional", "LINK_INVALID"),
    )
    return next((code for fragment, code in mapping if fragment in message), None)
