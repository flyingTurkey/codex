import asyncio
import struct

import pytest
from srbg_api.document_vault.scanner import ClamAVScanner
from srbg_api.document_vault.security import MalwareDetected, MalwareScanInconclusive


async def _server_response(response: bytes) -> tuple[asyncio.Server, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert await reader.readuntil(b"\0") == b"zINSTREAM\0"
        received = bytearray()
        while True:
            length = struct.unpack("!I", await reader.readexactly(4))[0]
            if length == 0:
                break
            received.extend(await reader.readexactly(length))
        assert received
        writer.write(response + b"\0")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    return server, port


async def test_clamav_instream_accepts_clean_and_rejects_found() -> None:
    clean_server, clean_port = await _server_response(b"stream: OK")
    async with clean_server:
        await ClamAVScanner("127.0.0.1", clean_port, 1).scan(b"clean fixture")

    found_server, found_port = await _server_response(b"stream: Eicar-Signature FOUND")
    async with found_server:
        with pytest.raises(MalwareDetected, match="rejected"):
            await ClamAVScanner("127.0.0.1", found_port, 1).scan(b"EICAR fixture")


async def test_clamav_connection_failure_is_fail_closed() -> None:
    with pytest.raises(MalwareScanInconclusive, match="unavailable"):
        await ClamAVScanner("127.0.0.1", 1, 0.1).scan(b"fixture")


async def test_clamav_invalid_protocol_result_is_inconclusive_not_malware() -> None:
    server, port = await _server_response(b"stream: UNKNOWN")
    async with server:
        with pytest.raises(MalwareScanInconclusive, match="invalid result"):
            await ClamAVScanner("127.0.0.1", port, 1).scan(b"fixture")
