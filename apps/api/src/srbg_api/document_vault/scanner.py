"""Bounded ClamAV INSTREAM client; scanner failures reject the upload."""

import asyncio
import struct

from srbg_api.document_vault.security import UploadRejected


class ClamAVScanner:
    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds

    async def scan(self, content: bytes) -> None:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_connection(self._host, self._port)
                try:
                    writer.write(b"zINSTREAM\0")
                    for offset in range(0, len(content), 64 * 1024):
                        chunk = content[offset : offset + 64 * 1024]
                        writer.write(struct.pack("!I", len(chunk)))
                        writer.write(chunk)
                    writer.write(struct.pack("!I", 0))
                    await writer.drain()
                    response = await reader.readuntil(b"\0")
                finally:
                    writer.close()
                    await writer.wait_closed()
        except (
            TimeoutError,
            OSError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ) as exc:
            raise UploadRejected("malware scanner is unavailable") from exc

        result = response.rstrip(b"\0").decode("utf-8", errors="replace")
        if result.endswith(" FOUND"):
            raise UploadRejected("malware scanner rejected the fixture")
        if not result.endswith(" OK"):
            raise UploadRejected("malware scanner returned an invalid result")
