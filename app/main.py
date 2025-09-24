"""FastAPI entrypoint for the PDF → ventilation specification service."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import extractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF to Ventilation Spec")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

results_dir = Path(__file__).resolve().parent.parent / "results"
results_dir.mkdir(exist_ok=True)
app.mount("/results", StaticFiles(directory=results_dir), name="results")


@app.get("/health")
def health() -> JSONResponse:
    """Simple health check endpoint."""
    return JSONResponse({"status": "ok"})


@app.post("/extract")
async def extract(file: UploadFile = File(...)) -> JSONResponse:
    """Process an uploaded ventilation PDF and return the extraction summary."""
    try:
        result = await run_in_threadpool(extractor.process_upload, file)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.exception("Unhandled error during extraction")
        raise HTTPException(status_code=500, detail="Failed to process PDF") from exc
    return JSONResponse(result)
