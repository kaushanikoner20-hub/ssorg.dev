"""Tests for app/processor.py: OCR then AI for each screenshot, with both steps mocked."""

from unittest.mock import patch

from app import gemma, ocr, processor


def ocr_ok(text="Some readable text"):
    return ocr.OcrResult(ocr.STATUS_SUCCESS, text=text)


def ai_ok():
    metadata = gemma.ScreenshotMetadata(category="Notes", short_summary="A note.", confidence="medium")
    return gemma.GemmaResult(gemma.STATUS_SUCCESS, metadata=metadata)


def test_text_found_runs_ai_analysis():
    with patch("app.processor.ocr.extract_text", return_value=ocr_ok()) as fake_ocr, patch(
        "app.processor.gemma.analyze_text", return_value=ai_ok()
    ) as fake_ai:
        result = processor.process_image("a.png", b"bytes")
    fake_ocr.assert_called_once()
    fake_ai.assert_called_once_with("Some readable text")
    assert result.filename == "a.png"
    assert result.ai.metadata.category == "Notes"


def test_no_text_skips_ai():
    no_text = ocr.OcrResult(ocr.STATUS_NO_TEXT, message="nothing")
    with patch("app.processor.ocr.extract_text", return_value=no_text), patch(
        "app.processor.gemma.analyze_text"
    ) as fake_ai:
        result = processor.process_image("a.png", b"bytes")
    fake_ai.assert_not_called()
    assert result.ai is None


def test_ocr_error_skips_ai():
    failed = ocr.OcrResult(ocr.STATUS_ERROR, message="broken")
    with patch("app.processor.ocr.extract_text", return_value=failed), patch(
        "app.processor.gemma.analyze_text"
    ) as fake_ai:
        result = processor.process_image("a.png", b"bytes")
    fake_ai.assert_not_called()
    assert result.ocr.status == ocr.STATUS_ERROR


def test_ai_unavailable_still_keeps_ocr_text():
    down = gemma.GemmaResult(gemma.STATUS_UNAVAILABLE, message="Ollama is not running")
    with patch("app.processor.ocr.extract_text", return_value=ocr_ok("Keep me")), patch(
        "app.processor.gemma.analyze_text", return_value=down
    ):
        result = processor.process_image("a.png", b"bytes")
    assert result.ocr.text == "Keep me"
    assert result.ai.status == gemma.STATUS_UNAVAILABLE


def test_unexpected_exceptions_do_not_escape():
    with patch("app.processor.ocr.extract_text", side_effect=RuntimeError("boom")):
        result = processor.process_image("a.png", b"bytes")
    assert result.ocr.status == ocr.STATUS_ERROR

    with patch("app.processor.ocr.extract_text", return_value=ocr_ok()), patch(
        "app.processor.gemma.analyze_text", side_effect=RuntimeError("boom")
    ):
        result = processor.process_image("a.png", b"bytes")
    assert result.ocr.status == ocr.STATUS_SUCCESS
    assert result.ai.status == gemma.STATUS_ERROR


def test_one_failed_image_does_not_stop_the_batch():
    def fake_extract(image_bytes):
        if image_bytes == b"bad":
            raise RuntimeError("boom")
        return ocr_ok(image_bytes.decode())

    items = [("1", "one.png", b"first"), ("2", "two.png", b"bad"), ("3", "three.png", b"third")]
    progress_calls = []
    with patch("app.processor.ocr.extract_text", side_effect=fake_extract), patch(
        "app.processor.gemma.analyze_text", return_value=ai_ok()
    ):
        results = processor.process_images(items, on_progress=lambda i, n, name: progress_calls.append((i, n, name)))

    assert set(results) == {"1", "2", "3"}
    assert results["1"].ocr.status == ocr.STATUS_SUCCESS
    assert results["2"].ocr.status == ocr.STATUS_ERROR
    assert results["3"].ocr.text == "third"
    assert progress_calls == [(0, 3, "one.png"), (1, 3, "two.png"), (2, 3, "three.png")]


def test_images_are_processed_independently():
    texts = {b"a": "text a", b"b": "text b"}
    seen = []

    def fake_analyze(text):
        seen.append(text)
        return ai_ok()

    with patch("app.processor.ocr.extract_text", side_effect=lambda data: ocr_ok(texts[data])), patch(
        "app.processor.gemma.analyze_text", side_effect=fake_analyze
    ):
        processor.process_images([("1", "a.png", b"a"), ("2", "b.png", b"b")])
    assert seen == ["text a", "text b"]


def test_needs_processing_rules():
    assert processor.needs_processing(None) is True
    good = processor.ScreenshotResult("a.png", ocr_ok(), ai_ok())
    assert processor.needs_processing(good) is False

    no_text = processor.ScreenshotResult("a.png", ocr.OcrResult(ocr.STATUS_NO_TEXT), None)
    assert processor.needs_processing(no_text) is False  # re-running would not help

    ocr_failed = processor.ScreenshotResult("a.png", ocr.OcrResult(ocr.STATUS_ERROR), None)
    assert processor.needs_processing(ocr_failed) is True

    ollama_down = processor.ScreenshotResult("a.png", ocr_ok(), gemma.GemmaResult(gemma.STATUS_UNAVAILABLE))
    assert processor.needs_processing(ollama_down) is True  # worth retrying after starting Ollama

    bad_answer = processor.ScreenshotResult("a.png", ocr_ok(), gemma.GemmaResult(gemma.STATUS_INVALID_RESPONSE))
    assert processor.needs_processing(bad_answer) is False