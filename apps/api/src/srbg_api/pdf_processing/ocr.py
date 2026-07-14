"""OCR adapter protocol and bounded local Tesseract implementation."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OcrWord:
    text: str
    x0_px: int
    y0_px: int
    x1_px: int
    y1_px: int
    confidence_bps: int


@dataclass(frozen=True, slots=True)
class OcrPageResult:
    words: tuple[OcrWord, ...]
    image_width_px: int
    image_height_px: int
    engine_version: str


class OcrAdapter(Protocol):
    def recognize(self, png_bytes: bytes, *, page_number: int) -> OcrPageResult: ...


class OcrUnavailable(RuntimeError):
    pass


class TesseractOcrAdapter:
    def __init__(self, *, executable: str = "tesseract", timeout_seconds: float = 30) -> None:
        if timeout_seconds <= 0:
            raise ValueError("OCR timeout must be positive")
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def recognize(self, png_bytes: bytes, *, page_number: int) -> OcrPageResult:
        with TemporaryDirectory(prefix="srbg-ocr-") as directory:
            image_path = Path(directory) / f"page-{page_number}.png"
            image_path.write_bytes(png_bytes)
            environment = {
                key: value
                for key, value in os.environ.items()
                if key.casefold() in {"path", "systemroot", "windir", "tmp", "temp", "lang"}
            }
            try:
                completed = subprocess.run(  # noqa: S603
                    [
                        self._executable,
                        str(image_path),
                        "stdout",
                        "-l",
                        "chi_sim+eng",
                        "--psm",
                        "6",
                        "tsv",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                    env=environment,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as error:
                raise OcrUnavailable("OCR_ENGINE_UNAVAILABLE") from error
            if completed.returncode != 0:
                raise OcrUnavailable("OCR_ENGINE_FAILED")
            return _parse_tsv(completed.stdout)


def _parse_tsv(value: str) -> OcrPageResult:
    rows = value.splitlines()
    words: list[OcrWord] = []
    width = 0
    height = 0
    for row in rows[1:]:
        columns = row.split("\t")
        if len(columns) < 12:
            continue
        left, top, cell_width, cell_height = (int(columns[index]) for index in range(6, 10))
        width = max(width, left + cell_width)
        height = max(height, top + cell_height)
        text = columns[11].strip()
        try:
            confidence = float(columns[10])
        except ValueError:
            continue
        if not text or confidence < 0:
            continue
        words.append(
            OcrWord(
                text=text,
                x0_px=left,
                y0_px=top,
                x1_px=left + cell_width,
                y1_px=top + cell_height,
                confidence_bps=max(0, min(10000, round(confidence * 100))),
            )
        )
    return OcrPageResult(
        words=tuple(words),
        image_width_px=max(width, 1),
        image_height_px=max(height, 1),
        engine_version="tesseract-local-chi_sim+eng",
    )
