"""Tests for the Stage 3 workflow in app/processor.py.

OCR and Gemma are mocked, and every test uses temporary folders, so no real
Tesseract, Ollama, model or personal library is needed or touched.
"""

import io
import sqlite3
from contextlib import ExitStack
from unittest.mock import patch

from PIL import Image

from app import database, gemma, ocr, processor, storage


def make_image_bytes(color="white", image_format="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (60, 30), color).save(buffer, image_format)
    return buffer.getvalue()


def good_ocr(text="Green Cafe total 245.50"):
    return ocr.OcrResult(ocr.STATUS_SUCCESS, text=text)


def good_ai():
    metadata = gemma.ScreenshotMetadata(
        category="Receipt",
        short_summary="A cafe receipt.",
        important_dates=["12 Oct 2026"],
        named_entities=["Green Cafe"],
        useful_search_terms=["receipt", "cafe"],
        confidence="high",
    )
    return gemma.GemmaResult(gemma.STATUS_SUCCESS, metadata=metadata)


def pipeline(ocr_result=None, ai_result=None):
    """Replace OCR and Gemma with fakes for the duration of a `with` block."""
    stack = ExitStack()
    fake_ocr = stack.enter_context(patch("app.processor.ocr.extract_text", return_value=ocr_result or good_ocr()))
    fake_ai = stack.enter_context(patch("app.processor.gemma.analyze_text", return_value=ai_result or good_ai()))
    stack.fake_ocr, stack.fake_ai = fake_ocr, fake_ai
    return stack


def folders(tmp_path):
    return tmp_path / "library" / "ssorg.db", tmp_path / "library" / "screenshots"


def stored_files(storage_dir):
    return sorted(storage_dir.iterdir()) if storage_dir.exists() else []


def import_one(tmp_path, name="a.png", data=None, **pipeline_kwargs):
    db_path, storage_dir = folders(tmp_path)
    with pipeline(**pipeline_kwargs):
        return processor.import_screenshot(name, data or make_image_bytes(), db_path=db_path, storage_dir=storage_dir)


# ----- importing a new screenshot -----
def test_new_screenshot_is_saved_analyzed_and_recorded(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    data = make_image_bytes()
    result = import_one(tmp_path, "receipt.png", data)

    assert result.outcome == processor.OUTCOME_IMPORTED
    assert result.processing_status == database.STATUS_COMPLETE
    record = database.get_screenshot_by_id(result.screenshot_id, db_path)
    assert record["original_filename"] == "receipt.png"
    assert record["file_hash"] == storage.hash_bytes(data)
    assert record["file_size"] == len(data)
    assert record["mime_type"] == "image/png"
    assert record["ocr_text"] == "Green Cafe total 245.50"
    assert record["category"] == "Receipt"
    assert record["important_dates"] == ["12 Oct 2026"]
    # the original bytes were saved unchanged under the generated name
    files = stored_files(storage_dir)
    assert len(files) == 1 and files[0].name == record["stored_filename"]
    assert files[0].read_bytes() == data


def test_unsafe_uploaded_filename_is_only_display_text(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    cases = (
        ("../../evil.png", "evil.png", "red"),
        ("C:\\Users\\me\\Desktop\\shot.png", "shot.png", "blue"),
        ("", "screenshot", "green"),
    )
    for uploaded_name, expected_display, color in cases:
        data = make_image_bytes(color=color)
        with pipeline():
            result = processor.import_screenshot(uploaded_name, data, db_path=db_path, storage_dir=storage_dir)
        record = database.get_screenshot_by_id(result.screenshot_id, db_path)
        assert record["original_filename"] == expected_display
        assert storage.resolve_stored_path(record["stored_filename"], storage_dir).is_file()
    assert not (tmp_path / "evil.png").exists()
    assert all(path.parent == storage_dir for path in stored_files(storage_dir))


# ----- duplicate detection -----
def test_same_bytes_with_a_different_filename_is_a_duplicate(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    data = make_image_bytes()
    first = import_one(tmp_path, "one.png", data)
    with pipeline() as fakes:
        second = processor.import_screenshot("copy of one.png", data, db_path=db_path, storage_dir=storage_dir)
    assert second.outcome == processor.OUTCOME_DUPLICATE
    assert second.screenshot_id == first.screenshot_id  # points at the existing record
    assert "already in your library" in second.message
    assert database.get_screenshot_count(db_path) == 1
    assert len(stored_files(storage_dir)) == 1
    fakes.fake_ocr.assert_not_called()  # no repeated OCR or AI work for a duplicate
    fakes.fake_ai.assert_not_called()


def test_duplicate_does_not_overwrite_the_existing_record_or_file(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    data = make_image_bytes()
    first = import_one(tmp_path, "original name.png", data)
    before = database.get_screenshot_by_id(first.screenshot_id, db_path)
    import_one(tmp_path, "different name.png", data)
    after = database.get_screenshot_by_id(first.screenshot_id, db_path)
    assert after == before
    assert (storage_dir / before["stored_filename"]).read_bytes() == data


def test_different_images_are_both_imported(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    first = import_one(tmp_path, "a.png", make_image_bytes(color="red"))
    second = import_one(tmp_path, "b.png", make_image_bytes(color="blue"))
    assert first.outcome == second.outcome == processor.OUTCOME_IMPORTED
    assert first.screenshot_id != second.screenshot_id
    assert database.get_screenshot_count(db_path) == 2
    assert len(stored_files(storage_dir)) == 2


def test_race_between_duplicate_check_and_insert_leaves_no_extra_file(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    data = make_image_bytes()
    first = import_one(tmp_path, "a.png", data)
    existing = database.get_screenshot_by_id(first.screenshot_id, db_path)
    # Pretend the first duplicate check found nothing (someone imported at the same moment).
    with pipeline(), patch(
        "app.processor.database.get_screenshot_by_hash", side_effect=[None, existing]
    ):
        result = processor.import_screenshot("b.png", data, db_path=db_path, storage_dir=storage_dir)
    assert result.outcome == processor.OUTCOME_DUPLICATE
    assert database.get_screenshot_count(db_path) == 1
    assert len(stored_files(storage_dir)) == 1  # the file saved for the failed attempt was removed


# ----- failures keep the screenshot -----
def test_no_readable_text_still_keeps_the_screenshot(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    result = import_one(tmp_path, ocr_result=ocr.OcrResult(ocr.STATUS_NO_TEXT, message=ocr.MESSAGE_NO_TEXT))
    assert result.outcome == processor.OUTCOME_IMPORTED
    assert result.processing_status == database.STATUS_NO_TEXT
    assert database.get_screenshot_count(db_path) == 1 and len(stored_files(storage_dir)) == 1


def test_ocr_failure_keeps_the_screenshot_and_records_the_failure(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    failed = ocr.OcrResult(ocr.STATUS_ERROR, message="Tesseract OCR was not found.")
    result = import_one(tmp_path, ocr_result=failed)
    record = database.get_screenshot_by_id(result.screenshot_id, db_path)
    assert result.outcome == processor.OUTCOME_IMPORTED
    assert record["processing_status"] == database.STATUS_OCR_FAILED
    assert "Tesseract" in record["processing_error"]
    assert len(stored_files(storage_dir)) == 1


def test_ai_failure_keeps_the_screenshot_and_its_ocr_text(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    down = gemma.GemmaResult(gemma.STATUS_UNAVAILABLE, message="Could not reach Ollama.")
    result = import_one(tmp_path, ocr_result=good_ocr("Keep this text"), ai_result=down)
    record = database.get_screenshot_by_id(result.screenshot_id, db_path)
    assert record["processing_status"] == database.STATUS_AI_FAILED
    assert record["ocr_text"] == "Keep this text"
    assert record["category"] is None
    assert "Ollama" in record["processing_error"]
    assert len(stored_files(storage_dir)) == 1


def test_unexpected_crash_in_ocr_still_keeps_the_screenshot(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    with patch("app.processor.ocr.extract_text", side_effect=RuntimeError("boom")):
        result = processor.import_screenshot("a.png", make_image_bytes(), db_path=db_path, storage_dir=storage_dir)
    assert result.outcome == processor.OUTCOME_IMPORTED
    assert result.processing_status == database.STATUS_OCR_FAILED
    assert len(stored_files(storage_dir)) == 1


def test_invalid_upload_saves_nothing(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    with pipeline() as fakes:
        result = processor.import_screenshot("notes.png", b"not an image", db_path=db_path, storage_dir=storage_dir)
    assert result.outcome == processor.OUTCOME_FAILED
    assert stored_files(storage_dir) == []
    assert database.get_screenshot_count(db_path) == 0
    fakes.fake_ocr.assert_not_called()


# ----- cleanup when saving fails -----
def test_file_is_cleaned_up_when_the_database_insert_fails(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    with pipeline() as fakes, patch(
        "app.processor.database.add_screenshot", side_effect=database.DatabaseError("The library is locked.")
    ):
        result = processor.import_screenshot("a.png", make_image_bytes(), db_path=db_path, storage_dir=storage_dir)
    assert result.outcome == processor.OUTCOME_FAILED
    assert stored_files(storage_dir) == []  # no orphaned file
    fakes.fake_ocr.assert_not_called()


def test_nothing_is_recorded_when_the_file_cannot_be_saved(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    with pipeline() as fakes, patch(
        "app.processor.storage.save_image_bytes", side_effect=storage.StorageError("The screenshot could not be saved to disk.")
    ):
        result = processor.import_screenshot("a.png", make_image_bytes(), db_path=db_path, storage_dir=storage_dir)
    assert result.outcome == processor.OUTCOME_FAILED
    assert database.get_screenshot_count(db_path) == 0
    fakes.fake_ocr.assert_not_called()


def test_screenshot_is_kept_as_pending_if_results_cannot_be_saved(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    with pipeline(), patch(
        "app.processor.database.update_screenshot_processing", side_effect=database.DatabaseError("locked")
    ):
        result = processor.import_screenshot("a.png", make_image_bytes(), db_path=db_path, storage_dir=storage_dir)
    assert result.outcome == processor.OUTCOME_IMPORTED
    assert result.processing_status == database.STATUS_PENDING
    assert "Re-run" in result.message
    assert database.get_screenshot_count(db_path) == 1 and len(stored_files(storage_dir)) == 1


# ----- batches -----
def test_one_bad_file_does_not_stop_the_batch(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    good_one, good_two = make_image_bytes(color="red"), make_image_bytes(color="blue")
    items = [("a.png", good_one), ("broken.png", b"junk"), ("b.png", good_two), ("a copy.png", good_one)]
    progress = []
    with pipeline():
        results = processor.import_screenshots(
            items, on_progress=lambda i, n, name: progress.append((i, n)), db_path=db_path, storage_dir=storage_dir
        )
    assert [r.outcome for r in results] == [
        processor.OUTCOME_IMPORTED, processor.OUTCOME_FAILED, processor.OUTCOME_IMPORTED, processor.OUTCOME_DUPLICATE,
    ]
    assert progress == [(0, 4), (1, 4), (2, 4), (3, 4)]
    assert database.get_screenshot_count(db_path) == 2


def test_unexpected_exception_in_one_file_does_not_stop_the_batch(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    real = processor.import_screenshot
    calls = {"n": 0}

    def sometimes_crash(filename, data, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(filename, data, **kwargs)

    with pipeline(), patch("app.processor.import_screenshot", side_effect=sometimes_crash):
        results = processor.import_screenshots(
            [("a.png", make_image_bytes("red")), ("b.png", make_image_bytes("blue"))],
            db_path=db_path, storage_dir=storage_dir,
        )
    assert [r.outcome for r in results] == [processor.OUTCOME_FAILED, processor.OUTCOME_IMPORTED]


# ----- persistence -----
def test_records_and_files_are_still_there_with_a_fresh_connection(tmp_path):
    # Every database call opens a new connection, just like an app that was restarted.
    db_path, storage_dir = folders(tmp_path)
    result = import_one(tmp_path)
    records = database.get_all_screenshots(db_path=db_path)
    assert [r["id"] for r in records] == [result.screenshot_id]
    assert storage.read_stored_file(records[0]["stored_filename"], storage_dir) is not None


# ----- re-running analysis -----
def test_rerun_after_ai_failure_fills_in_the_analysis(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    down = gemma.GemmaResult(gemma.STATUS_UNAVAILABLE, message="Could not reach Ollama.")
    first = import_one(tmp_path, ai_result=down)
    assert database.get_screenshot_by_id(first.screenshot_id, db_path)["processing_status"] == database.STATUS_AI_FAILED
    with pipeline():
        again = processor.reprocess_screenshot(first.screenshot_id, db_path=db_path, storage_dir=storage_dir)
    record = database.get_screenshot_by_id(first.screenshot_id, db_path)
    assert again.outcome == processor.OUTCOME_REPROCESSED
    assert record["processing_status"] == database.STATUS_COMPLETE
    assert record["category"] == "Receipt"
    assert record["processing_error"] is None
    assert database.get_screenshot_count(db_path) == 1  # no new record was created


def test_rerun_with_missing_image_file_fails_cleanly(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    first = import_one(tmp_path)
    for path in stored_files(storage_dir):
        path.unlink()
    with pipeline() as fakes:
        again = processor.reprocess_screenshot(first.screenshot_id, db_path=db_path, storage_dir=storage_dir)
    assert again.outcome == processor.OUTCOME_FAILED
    assert "missing" in again.message
    fakes.fake_ocr.assert_not_called()


def test_rerun_for_unknown_id_fails_cleanly(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    database.initialize_database(db_path)
    assert processor.reprocess_screenshot(42, db_path=db_path, storage_dir=storage_dir).outcome == processor.OUTCOME_FAILED


# ----- deleting -----
def test_delete_removes_record_and_file(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    keep = import_one(tmp_path, "keep.png", make_image_bytes("red"))
    remove = import_one(tmp_path, "remove.png", make_image_bytes("blue"))
    result = processor.delete_screenshot(remove.screenshot_id, db_path=db_path, storage_dir=storage_dir)
    assert result.success and result.record_deleted and result.file_deleted
    assert database.get_screenshot_by_id(remove.screenshot_id, db_path) is None
    assert database.get_screenshot_by_id(keep.screenshot_id, db_path) is not None
    assert len(stored_files(storage_dir)) == 1  # only the other screenshot's file remains


def test_delete_when_the_image_file_is_already_missing_still_removes_the_record(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    first = import_one(tmp_path)
    for path in stored_files(storage_dir):
        path.unlink()
    result = processor.delete_screenshot(first.screenshot_id, db_path=db_path, storage_dir=storage_dir)
    assert result.success and result.record_deleted and not result.file_deleted
    assert "already missing" in result.message
    assert database.get_screenshot_count(db_path) == 0


def test_delete_never_touches_files_outside_the_storage_folder(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    first = import_one(tmp_path)
    decoy = tmp_path / "important.png"
    decoy.write_bytes(b"do not delete")
    # Simulate a tampered database: the stored name now points outside the folder.
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("UPDATE screenshots SET stored_filename = ? WHERE id = ?", ("../../important.png", first.screenshot_id))
        connection.commit()
    finally:
        connection.close()
    result = processor.delete_screenshot(first.screenshot_id, db_path=db_path, storage_dir=storage_dir)
    assert result.success is False  # partial: reported honestly
    assert result.record_deleted is True and result.file_deleted is False
    assert "not safe" in result.message
    assert decoy.read_bytes() == b"do not delete"


def test_delete_reports_partial_failure_when_the_file_cannot_be_removed(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    first = import_one(tmp_path)
    with patch("app.processor.storage.delete_stored_file", side_effect=storage.StorageError("locked")):
        result = processor.delete_screenshot(first.screenshot_id, db_path=db_path, storage_dir=storage_dir)
    assert result.success is False and result.record_deleted is True
    assert "by hand" in result.message


def test_delete_changes_nothing_if_the_record_cannot_be_deleted(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    first = import_one(tmp_path)
    with patch("app.processor.database.delete_screenshot_record", side_effect=database.DatabaseError("locked")):
        result = processor.delete_screenshot(first.screenshot_id, db_path=db_path, storage_dir=storage_dir)
    assert result.success is False and result.record_deleted is False
    assert database.get_screenshot_by_id(first.screenshot_id, db_path) is not None
    assert len(stored_files(storage_dir)) == 1  # the image was not removed


def test_deleting_an_unknown_id_is_harmless(tmp_path):
    db_path, storage_dir = folders(tmp_path)
    database.initialize_database(db_path)
    result = processor.delete_screenshot(999, db_path=db_path, storage_dir=storage_dir)
    assert result.success and not result.record_deleted