"""Exercise the externally visible platform runtime contract."""

from __future__ import annotations

import json
import os
import time
from http.client import HTTPConnection
from typing import Any


def host_port(name: str, default: int) -> int:
    """Return a validated host port shared with the Compose environment."""
    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer TCP port") from error
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


def request(port: int, path: str) -> tuple[int, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        connection.close()


def wait_for_status(port: int, path: str, expected_status: int, timeout: float = 90) -> str:
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            status, body = request(port, path)
            if status == expected_status:
                return body
            last_error = f"HTTP {status}: {body[:200]}"
        except OSError as error:
            last_error = str(error)
        time.sleep(1)
    raise RuntimeError(f"{path} did not return HTTP {expected_status}: {last_error}")


def parse_object(body: str) -> dict[str, Any]:
    value = json.loads(body)
    if not isinstance(value, dict):
        raise TypeError("expected a JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    api_port = host_port("API_PORT", 8000)
    web_port = host_port("WEB_PORT", 3000)

    readiness = parse_object(wait_for_status(api_port, "/health/ready", 200))
    require(readiness["status"] == "ready", "API readiness status is not ready")
    require(
        set(readiness["checks"]) == {"postgresql", "redis", "object_storage"},
        "readiness dependency set is incomplete",
    )
    require(
        all(check["status"] == "up" for check in readiness["checks"].values()),
        "one or more readiness dependencies are down",
    )

    liveness = parse_object(wait_for_status(api_port, "/health/live", 200))
    require(liveness["status"] == "ok", "API liveness status is not ok")

    version = parse_object(wait_for_status(api_port, "/api/v1/version", 200))
    require(
        version == {"api_version": "v1", "content_schema_version": "1.1.0"},
        "version contract does not match the generated contracts",
    )

    homepage = wait_for_status(web_port, "/", 200)
    require("四川路桥" in homepage, "homepage organization brand is missing")
    require("智安情报" in homepage, "homepage product brand is missing")
    require("业务数据尚未接入" in homepage, "honest homepage empty state is missing")

    print(json.dumps({"status": "ok", "checks": readiness["checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
