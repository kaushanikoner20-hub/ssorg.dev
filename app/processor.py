"""Stage 2: the processing workflow for screenshots.

For each screenshot:  OCR text extraction  ->  (if text was found)  local Gemma analysis.

This file does not use Streamlit, so it is easy to test.
Saving to disk or a database is NOT done here yet (that is Stage 3).
"""

from dataclasses import dataclass
from typing import Callable

from app import gemma, ocr

# If the AI step ended with one of these, running it again later may succeed
# (for example after the user starts Ollama).
RETRYABLE_AI_STATUSES = (
    gemma.STATUS_UNAVAILABLE,
    gemma.STATUS_MODEL_MISSING,
    gemma.STATUS_TIMEOUT,
    gemma.STATUS_ERROR,
)


@dataclass
class ScreenshotResult:
    """Everything we learned about one screenshot in this session."""

    filename: str
    ocr: ocr.OcrResult
    ai: gemma.GemmaResult | None = None  # None when OCR found no usable text


def process_image(filename: str, image_bytes: bytes) -> ScreenshotResult:
    """Run OCR and then AI analysis on one image. Never raises."""
    try:
        ocr_result = ocr.extract_text(image_bytes)
    except Exception:  # safety net: one bad image must not stop the others
        ocr_result = ocr.OcrResult(ocr.STATUS_ERROR, message="Something went wrong while reading this image.")

    ai_result = None
    if ocr_result.status == ocr.STATUS_SUCCESS:
        try:
            ai_result = gemma.analyze_text(ocr_result.text)
        except Exception:  # safety net
            ai_result = gemma.GemmaResult(gemma.STATUS_ERROR, message="Something went wrong during AI analysis.")
    return ScreenshotResult(filename=filename, ocr=ocr_result, ai=ai_result)


def needs_processing(result: ScreenshotResult | None) -> bool:
    """True if this screenshot has no result yet, or a result worth retrying."""
    if result is None:
        return True
    if result.ocr.status == ocr.STATUS_ERROR:
        return True
    return result.ai is not None and result.ai.status in RETRYABLE_AI_STATUSES


def process_images(
    items: list[tuple[str, str, bytes]],
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, ScreenshotResult]:
    """Process several screenshots one at a time.

    `items` is a list of (file_id, filename, image_bytes).
    If one image fails the others still run. Returns {file_id: ScreenshotResult}.
    """
    results: dict[str, ScreenshotResult] = {}
    total = len(items)
    for index, (file_id, filename, image_bytes) in enumerate(items):
        if on_progress:
            on_progress(index, total, filename)
        results[file_id] = process_image(filename, image_bytes)
    return results