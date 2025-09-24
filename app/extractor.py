"""Core extraction pipeline for the ventilation specification service."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # type: ignore
import pytesseract
import yaml
from fastapi import HTTPException, UploadFile

from . import parsers, utils

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
RESULTS_DIR = BASE_DIR / "results"
PATTERN_PATH = Path(__file__).resolve().parent / "patterns.yaml"
CHAR_THRESHOLD = 500


@lru_cache(maxsize=1)
def load_patterns() -> Dict:
    """Load parsing patterns from the YAML configuration file."""
    try:
        with PATTERN_PATH.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="patterns.yaml not found") from exc
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=500, detail="Failed to parse patterns.yaml") from exc


def _split_lines(text: str) -> List[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


def extract_text(pdf_path: Path) -> Tuple[str, List[str], Dict[str, int]]:
    """Extract text from the PDF combining vector and OCR sources."""
    notes: List[str] = []
    vector_lines: List[str] = []
    ocr_lines: List[str] = []
    stats = {"vector_chars": 0, "ocr_lines": 0, "pages": 0}

    with fitz.open(pdf_path) as document:
        stats["pages"] = document.page_count
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            text = page.get_text("text")
            stats["vector_chars"] += len(text)
            vector_lines.extend(_split_lines(text))

        if stats["vector_chars"] > 0:
            notes.append("vector_text")

        if stats["vector_chars"] < CHAR_THRESHOLD:
            notes.append("ocr_used")
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                image = utils.render_page_to_image(page)
                ocr_text = pytesseract.image_to_string(image, lang="eng+pol")
                page_lines = _split_lines(ocr_text)
                ocr_lines.extend(page_lines)
            stats["ocr_lines"] = len(ocr_lines)

    combined_lines = utils.deduplicate_lines(vector_lines, ocr_lines)
    combined_text = "\n".join(combined_lines)
    logger.info(
        "Extracted text from %s: vector_chars=%s, ocr_lines=%s, notes=%s",
        pdf_path,
        stats["vector_chars"],
        stats["ocr_lines"],
        notes,
    )
    return combined_text, notes, stats


def build_round_rows(round_counter: Dict[str, int]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for size, count in sorted(round_counter.items()):
        rows.append(
            {
                "Element": "Rura SPIRO",
                "Wymiar": f"{size} mm",
                "Ilość": int(count),
                "Uwagi": "Etykiety; bez długości",
            }
        )
    return rows


def build_rect_rows(rect_counter: Dict[str, int]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for size, count in sorted(rect_counter.items()):
        rows.append(
            {
                "Element": "Kanał prostokątny",
                "Wymiar": f"{size} mm",
                "Ilość": int(count),
                "Uwagi": "Etykiety; bez długości",
            }
        )
    return rows


def process_upload(upload: UploadFile) -> Dict:
    """Main entry point for processing an uploaded PDF."""
    if upload.content_type not in {"application/pdf", "application/x-pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Expected a PDF file")

    job_id = utils.generate_job_id()
    upload_dir, result_dir = utils.prepare_job_directories(UPLOADS_DIR, RESULTS_DIR, job_id)
    pdf_path = upload_dir / "input.pdf"
    utils.save_upload_file(upload, pdf_path)

    try:
        raw_text, notes, _stats = extract_text(pdf_path)
    except RuntimeError as exc:
        logger.exception("Failed to read PDF %s", pdf_path)
        raise HTTPException(status_code=400, detail="Invalid or corrupt PDF") from exc
    except Exception as exc:
        logger.exception("Unexpected error while extracting text")
        raise HTTPException(status_code=500, detail="Failed to extract text") from exc
    normalized_text = utils.normalize_text(raw_text)
    lines = utils.as_lines(normalized_text)

    patterns = load_patterns()
    equipment_items = parsers.parse_equipment(lines, patterns)
    fittings_items = parsers.parse_fittings(lines, patterns)
    round_counter, rect_counter = parsers.parse_duct_sizes(normalized_text, patterns)

    equipment_rows = parsers.aggregate_items(equipment_items)
    fittings_rows = parsers.aggregate_items(fittings_items)
    round_rows = build_round_rows(round_counter)
    rect_rows = build_rect_rows(rect_counter)

    all_rows: List[Dict[str, object]] = []
    all_rows.extend(equipment_rows)
    all_rows.extend(fittings_rows)
    all_rows.extend(round_rows)
    all_rows.extend(rect_rows)

    excel_path = result_dir / "spec.xlsx"
    utils.write_excel(all_rows, excel_path)

    counts = {
        "equipment": sum(row["Ilość"] for row in equipment_rows),
        "fittings": sum(row["Ilość"] for row in fittings_rows),
        "round_sizes": sum(row["Ilość"] for row in round_rows),
        "rect_sizes": sum(row["Ilość"] for row in rect_rows),
    }

    response = {
        "job_id": job_id,
        "excel_path": f"/results/{job_id}/spec.xlsx",
        "counts": counts,
        "notes": notes,
    }
    return response
