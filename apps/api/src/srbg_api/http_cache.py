"""Canonical private ETag responses for authenticated contract payloads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


def contract_etag_response(
    request: Request,
    payload: BaseModel | Sequence[BaseModel],
    *,
    exclude_none: bool = False,
    exclude_unset: bool = False,
) -> Response:
    data: Any
    if isinstance(payload, BaseModel):
        data = payload.model_dump(
            mode="json", exclude_none=exclude_none, exclude_unset=exclude_unset
        )
    else:
        data = [
            entry.model_dump(
                mode="json", exclude_none=exclude_none, exclude_unset=exclude_unset
            )
            for entry in payload
        ]
    etag_data = data
    if isinstance(data, dict):
        etag_data = {key: value for key, value in data.items() if key != "generated_at"}
    canonical = json.dumps(etag_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    etag = f'"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"'
    headers = {"ETag": etag, "Cache-Control": "private, must-revalidate"}
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return JSONResponse(content=data, headers=headers)
