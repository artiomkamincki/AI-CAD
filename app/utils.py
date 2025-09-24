"""Utility helpers for the ventilation specification extractor."""
from __future__ import annotations

import io
import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Iterable, List

import fitz  # type: ignore
import pandas as pd
from PIL import Image
from fastapi import UploadFile

logger = logging.getLogger(__name__)


def generate_job_id() -> str:
    """Generate a random hexadecimal job identifier."""
    return uuid.uuid4().hex


def ensure_directory(path: Path) -> None:
    """Create a directory (and parents) if it does not yet exist."""
    path.mkdir(parents=True, exist_ok=True)


def prepare_job_directories(base_upload: Path, base_results: Path, job_id: str) -> tuple[Path, Path]:
    """Create and return upload/result directories for the job."""
    upload_dir = base_upload / job_id
    result_dir = base_results / job_id
    ensure_directory(upload_dir)
    ensure_directory(result_dir)
    return upload_dir, result_dir


def save_upload_file(upload: UploadFile, destination: Path) -> None:
    """Persist the uploaded file to disk."""
    ensure_directory(destination.parent)
    with destination.open("wb") as buffer:
        upload.file.seek(0)
        shutil.copyfileobj(upload.file, buffer)


def render_page_to_image(page: fitz.Page, zoom: float = 3.2) -> Image.Image:
    """Render a PDF page to a PIL image using the provided zoom factor."""
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
    if mode == "RGBA":
        image = image.convert("RGB")
    return image


def normalize_autocad_symbols(text: str) -> str:
    """Replace AutoCAD-style placeholders with human-readable symbols."""
    replacements = {
        "%%c": "Ø",
        "ø": "Ø",
        "φ": "Ø",
        "Φ": "Ø",
        "°": "°",
        "–": "-",
        "—": "-",
        "‒": "-",
        "×": "x",
        "·": ".",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Replace common diameter prefixes (O,0) when followed by digits
    text = re.sub(r"\b[Oo0]\s?(\d{2,4})", r"Ø\1", text)
    return text


def collapse_whitespace(text: str) -> str:
    """Collapse repeated whitespace characters while preserving newlines."""
    # Normalise Windows line endings then collapse spaces per line
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw_line in text.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        lines.append(line)
    return "\n".join(line for line in lines if line)


def normalize_text(text: str) -> str:
    """Perform a full normalization pass on raw extracted text."""
    text = normalize_autocad_symbols(text)
    text = text.replace("->", "→").replace("=>", "→")
    text = collapse_whitespace(text)
    # Remove stray commas between dimensions like "Ø160 ,"
    text = re.sub(r"\s*,\s*", ", ", text)
    # Ensure arrows surrounded by spaces for readability
    text = re.sub(r"\s*→\s*", " → ", text)
    text = re.sub(r"\s+/\s*", " / ", text)
    return text


def deduplicate_lines(primary: Iterable[str], secondary: Iterable[str]) -> List[str]:
    """Combine two iterables of lines keeping duplicates from the primary.

    Lines from the secondary source are appended only when the exact line has not
    already appeared in the primary source. This keeps counts from vector text
    while preventing duplication when OCR adds the same content.
    """
    result: List[str] = []
    seen_primary = set()
    for line in primary:
        if not line:
            continue
        result.append(line)
        seen_primary.add(line)
    for line in secondary:
        if not line:
            continue
        if line in seen_primary:
            continue
        result.append(line)
    return result


def write_excel(rows: List[dict], destination: Path) -> None:
    """Write extracted rows into an Excel file."""
    ensure_directory(destination.parent)
    df = pd.DataFrame(rows, columns=["Element", "Wymiar", "Ilość", "Uwagi"])
    with io.BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Spec")
        destination.write_bytes(buffer.getvalue())


def as_lines(text: str) -> List[str]:
    """Split text into non-empty lines preserving order."""
    return [line for line in text.split("\n") if line.strip()]
