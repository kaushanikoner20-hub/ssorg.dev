"""The screenshot workflow: import, analyze, save, re-run and delete.

Stage 2 part (still here):  OCR text extraction -> local Gemma analysis (process_image).
Stage 3 part (new):         validate -> SHA-256 -> duplicate check -> save the file
                            -> save the record -> OCR + Gemma -> update the record.

This file does not use Streamlit, so it is easy to test.
Nothing here ever raises for a normal problem. Functions return a result object
that says what happened, so one bad image cannot stop the others.
"""

import re
from dataclasses import dataclass
from typing import Callable

from app import database, gemma, ocr, storage

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


# =====================================================================
# Stage 3: persistent library
# =====================================================================
OUTCOME_IMPORTED = "imported"      # new screenshot saved (analysis may still have failed)
OUTCOME_DUPLICATE = "duplicate"    # the same file is already in the library
OUTCOME_FAILED = "failed"          # nothing was saved
OUTCOME_REPROCESSED = "reprocessed"

MESSAGE_DUPLICATE = "This screenshot is already in your library."

# Records in these states can be analyzed again from the saved image.
RERUNNABLE_STATUSES = (
    database.STATUS_PENDING,
    database.STATUS_OCR_FAILED,
    database.STATUS_AI_FAILED,
)


@dataclass
class ImportResult:
    """What happened to one uploaded file."""

    filename: str
    outcome: str
    screenshot_id: int | None = None  # the new record, or the existing one for a duplicate
    processing_status: str | None = None
    message: str = ""


@dataclass
class DeleteResult:
    """What happened when deleting one screenshot."""

    success: bool  # True only if nothing was left behind
    message: str
    record_deleted: bool = False
    file_deleted: bool = False


def _display_name(filename: str) -> str:
    """Make an uploaded filename safe to keep as display text (it is never used as a path)."""
    name = re.split(r"[\\/]", filename or "")[-1]
    name = "".join(character for character in name if character.isprintable()).strip()
    return name[:255] or "screenshot"


def _fields_from_result(result: ScreenshotResult) -> dict:
    """Translate OCR + AI results into the arguments of database.update_screenshot_processing."""
    ocr_result = result.ocr
    if ocr_result.status == ocr.STATUS_ERROR:
        return {"processing_status": database.STATUS_OCR_FAILED, "processing_error": ocr_result.message}
    if ocr_result.status == ocr.STATUS_NO_TEXT:
        return {"processing_status": database.STATUS_NO_TEXT}

    fields = {"ocr_text": ocr_result.text}  # OCR text is kept even if the AI step fails
    ai_result = result.ai
    if ai_result is not None and ai_result.status == gemma.STATUS_SUCCESS and ai_result.metadata:
        metadata = ai_result.metadata
        fields.update(
            category=metadata.category,
            short_summary=metadata.short_summary,
            important_dates=metadata.important_dates,
            named_entities=metadata.named_entities,
            useful_search_terms=metadata.useful_search_terms,
            confidence=metadata.confidence,
            processing_status=database.STATUS_COMPLETE,
        )
    else:
        fields.update(
            processing_status=database.STATUS_AI_FAILED,
            processing_error=ai_result.message if ai_result else "The AI analysis did not run.",
        )
    return fields


def _message_for(fields: dict) -> str:
    """A short explanation for the user when something was not fully successful."""
    status = fields["processing_status"]
    if status == database.STATUS_NO_TEXT:
        return ocr.MESSAGE_NO_TEXT
    if status in (database.STATUS_OCR_FAILED, database.STATUS_AI_FAILED):
        return fields.get("processing_error") or ""
    return ""


def _remove_new_file(stored_filename: str, storage_dir) -> None:
    """Undo a file we just saved. Never raises."""
    try:
        storage.delete_stored_file(stored_filename, storage_dir)
    except storage.StorageError:
        pass


def import_screenshot(filename: str, data: bytes, db_path=None, storage_dir=None) -> ImportResult:
    """Import one uploaded screenshot. Never raises.

    Steps: validate -> SHA-256 -> duplicate check -> save file -> add record
    -> OCR + Gemma -> update record.
    The image is kept even if OCR or the AI fails.
    """
    display_name = _display_name(filename)

    # 1-2. Validate the bytes and calculate the hash of the ORIGINAL bytes.
    try:
        image_info = storage.validate_image_bytes(data)
    except storage.InvalidImageError as error:
        return ImportResult(display_name, OUTCOME_FAILED, message=str(error))
    file_hash = storage.hash_bytes(data)

    # 3. Duplicate check (exact same bytes, whatever the filename).
    try:
        existing = database.get_screenshot_by_hash(file_hash, db_path)
    except database.DatabaseError as error:
        return ImportResult(display_name, OUTCOME_FAILED, message=str(error))
    if existing:
        return ImportResult(
            display_name, OUTCOME_DUPLICATE, screenshot_id=existing["id"],
            processing_status=existing["processing_status"], message=MESSAGE_DUPLICATE,
        )

    # 4. Save the original bytes under a generated name (never overwrites).
    stored_filename = storage.generate_stored_filename(image_info.extension)
    try:
        storage.save_image_bytes(data, stored_filename, storage_dir)
    except storage.StorageError as error:
        return ImportResult(display_name, OUTCOME_FAILED, message=str(error))

    # 5. Add the record right away as "pending", so a saved file never exists without a record.
    try:
        screenshot_id = database.add_screenshot(
            original_filename=display_name,
            stored_filename=stored_filename,
            file_hash=file_hash,
            file_size=len(data),
            mime_type=image_info.mime_type,
            db_path=db_path,
        )
    except database.DuplicateScreenshotError:
        # Someone imported the same file between our check and now.
        _remove_new_file(stored_filename, storage_dir)
        existing = database.get_screenshot_by_hash(file_hash, db_path)
        return ImportResult(
            display_name, OUTCOME_DUPLICATE, screenshot_id=existing["id"] if existing else None,
            message=MESSAGE_DUPLICATE,
        )
    except database.DatabaseError as error:
        _remove_new_file(stored_filename, storage_dir)  # no orphan file
        return ImportResult(display_name, OUTCOME_FAILED, message=str(error))

    # 6-7. OCR + Gemma, then save the results. Failures here keep the image.
    fields = _fields_from_result(process_image(display_name, data))
    try:
        saved = database.update_screenshot_processing(screenshot_id, db_path=db_path, **fields)
    except database.DatabaseError:
        saved = False
    if not saved:
        return ImportResult(
            display_name, OUTCOME_IMPORTED, screenshot_id=screenshot_id,
            processing_status=database.STATUS_PENDING,
            message="The screenshot was saved, but its analysis results could not be stored. "
                    "Open it in the library and choose Re-run analysis.",
        )
    return ImportResult(
        display_name, OUTCOME_IMPORTED, screenshot_id=screenshot_id,
        processing_status=fields["processing_status"], message=_message_for(fields),
    )


def import_screenshots(items, on_progress=None, db_path=None, storage_dir=None) -> list[ImportResult]:
    """Import several uploads one at a time. `items` is a list of (filename, bytes).

    If one file fails, the others still run.
    """
    results = []
    total = len(items)
    for index, (filename, data) in enumerate(items):
        if on_progress:
            on_progress(index, total, filename)
        try:
            results.append(import_screenshot(filename, data, db_path=db_path, storage_dir=storage_dir))
        except Exception:  # safety net: an unexpected bug must not stop the batch
            results.append(ImportResult(_display_name(filename), OUTCOME_FAILED, message="Something went wrong while importing this file."))
    return results


def reprocess_screenshot(screenshot_id: int, db_path=None, storage_dir=None) -> ImportResult:
    """Run OCR and the AI again on an already saved screenshot. Never raises."""
    try:
        record = database.get_screenshot_by_id(screenshot_id, db_path)
    except database.DatabaseError as error:
        return ImportResult("", OUTCOME_FAILED, message=str(error))
    if record is None:
        return ImportResult("", OUTCOME_FAILED, message="This screenshot is no longer in the library.")

    name = record["original_filename"]
    data = storage.read_stored_file(record["stored_filename"], storage_dir)
    if data is None:
        return ImportResult(name, OUTCOME_FAILED, screenshot_id=screenshot_id,
                            message="The image file is missing, so it cannot be analyzed again.")

    fields = _fields_from_result(process_image(name, data))
    try:
        saved = database.update_screenshot_processing(screenshot_id, db_path=db_path, **fields)
    except database.DatabaseError as error:
        return ImportResult(name, OUTCOME_FAILED, screenshot_id=screenshot_id, message=str(error))
    if not saved:
        return ImportResult(name, OUTCOME_FAILED, message="This screenshot is no longer in the library.")
    return ImportResult(name, OUTCOME_REPROCESSED, screenshot_id=screenshot_id,
                        processing_status=fields["processing_status"], message=_message_for(fields))


def delete_screenshot(screenshot_id: int, db_path=None, storage_dir=None) -> DeleteResult:
    """Delete a screenshot's record, then its image file. Never raises.

    The file path always goes through storage.resolve_stored_path, so only
    files inside the managed screenshot folder can ever be removed.
    """
    try:
        record = database.get_screenshot_by_id(screenshot_id, db_path)
    except database.DatabaseError:
        return DeleteResult(False, "The library could not be read. Nothing was deleted.")
    if record is None:
        return DeleteResult(True, "This screenshot was already removed from the library.")

    try:
        database.delete_screenshot_record(screenshot_id, db_path)
    except database.DatabaseError:
        return DeleteResult(False, "The record could not be deleted. Nothing was removed.")

    try:
        file_deleted = storage.delete_stored_file(record["stored_filename"], storage_dir)
    except storage.UnsafePathError:
        return DeleteResult(
            False,
            "The record was deleted, but its image file name was not safe, so no file was removed.",
            record_deleted=True,
        )
    except storage.StorageError:
        return DeleteResult(
            False,
            "The record was deleted, but the image file could not be removed. "
            "You can delete it by hand from the screenshots folder.",
            record_deleted=True,
        )
    if file_deleted:
        return DeleteResult(True, "The screenshot was deleted.", record_deleted=True, file_deleted=True)
    return DeleteResult(
        True, "The screenshot record was deleted. Its image file was already missing.", record_deleted=True
    )