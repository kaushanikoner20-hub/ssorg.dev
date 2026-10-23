"""Tests for app/ocr.py. The Tesseract engine is mocked, so Tesseract does not need to be installed."""

import io
from unittest.mock import patch

from PIL import Image

from app import config, ocr


def make_png_bytes(mode="RGB", size=(60, 30), color="white"):
    """Build a small valid PNG in memory."""
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, "PNG")
    return buffer.getvalue()


def fake_engine(text):
    """Replace the real OCR engine with one that returns `text`."""
    return patch("app.ocr.pytesseract.image_to_string", return_value=text)


def test_successful_extraction():
    with patch.object(config, "TESSERACT_CMD", ""), fake_engine("Hello from the screenshot\n\n\n\nSecond line  "):
        result = ocr.extract_text(make_png_bytes())
    assert result.status == ocr.STATUS_SUCCESS
    assert result.text == "Hello from the screenshot\n\nSecond line"


def test_empty_text_is_no_text():
    with patch.object(config, "TESSERACT_CMD", ""), fake_engine("   \n\n "):
        result = ocr.extract_text(make_png_bytes())
    assert result.status == ocr.STATUS_NO_TEXT
    assert result.text == ""
    assert "blurry" in result.message


def test_only_symbols_is_no_text():
    with patch.object(config, "TESSERACT_CMD", ""), fake_engine("| -- ~ ."):
        result = ocr.extract_text(make_png_bytes())
    assert result.status == ocr.STATUS_NO_TEXT


def test_invalid_image_is_error_and_engine_not_called():
    with patch.object(config, "TESSERACT_CMD", ""), fake_engine("never used") as engine:
        result = ocr.extract_text(b"this is not an image")
    assert result.status == ocr.STATUS_ERROR
    engine.assert_not_called()


def test_unsupported_input_type_is_error():
    result = ocr.extract_text(12345)
    assert result.status == ocr.STATUS_ERROR


def test_unsupported_image_format_is_error():
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, "GIF")
    result = ocr.extract_text(buffer.getvalue())
    assert result.status == ocr.STATUS_ERROR


def test_tesseract_not_installed_gives_clear_message():
    error = ocr.pytesseract.TesseractNotFoundError()
    with patch.object(config, "TESSERACT_CMD", ""), patch("app.ocr.pytesseract.image_to_string", side_effect=error):
        result = ocr.extract_text(make_png_bytes())
    assert result.status == ocr.STATUS_ERROR
    assert "Tesseract" in result.message


def test_missing_pytesseract_package_does_not_crash_ocr_call(monkeypatch):
    monkeypatch.setattr(ocr, "pytesseract", None)
    result = ocr.extract_text(b"not decoded")
    assert result.status == ocr.STATUS_ERROR
    assert "pytesseract" in result.message


def test_tesseract_failure_is_error():
    error = ocr.pytesseract.TesseractError(1, "something broke")
    with patch.object(config, "TESSERACT_CMD", ""), patch("app.ocr.pytesseract.image_to_string", side_effect=error):
        result = ocr.extract_text(make_png_bytes())
    assert result.status == ocr.STATUS_ERROR
    assert "something broke" not in result.message  # raw engine output is not shown


def test_ocr_timeout_is_error():
    with patch.object(config, "TESSERACT_CMD", ""), patch(
        "app.ocr.pytesseract.image_to_string", side_effect=RuntimeError("Tesseract process timeout")
    ):
        result = ocr.extract_text(make_png_bytes())
    assert result.status == ocr.STATUS_ERROR
    assert "seconds" in result.message


def test_unexpected_exception_is_error_not_crash():
    with patch.object(config, "TESSERACT_CMD", ""), patch(
        "app.ocr.pytesseract.image_to_string", side_effect=ValueError("boom")
    ):
        result = ocr.extract_text(make_png_bytes())
    assert result.status == ocr.STATUS_ERROR


def test_transparent_image_is_converted_and_original_unchanged():
    original = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    seen_modes = []

    def capture(image, **kwargs):
        seen_modes.append(image.mode)
        return "Some text here"

    with patch.object(config, "TESSERACT_CMD", ""), patch("app.ocr.pytesseract.image_to_string", side_effect=capture):
        result = ocr.extract_text(original)
    assert result.status == ocr.STATUS_SUCCESS
    assert seen_modes == ["RGB"]  # the engine received an RGB copy
    assert original.mode == "RGBA"  # the caller's image was not modified


def test_other_image_modes_are_converted():
    seen_modes = []

    def capture(image, **kwargs):
        seen_modes.append(image.mode)
        return "Some text here"

    for mode in ("L", "P", "CMYK"):
        with patch.object(config, "TESSERACT_CMD", ""), patch("app.ocr.pytesseract.image_to_string", side_effect=capture):
            ocr.extract_text(Image.new(mode, (30, 30)))
    assert seen_modes == ["RGB", "RGB", "RGB"]


def test_uploaded_file_like_object_is_accepted():
    class FakeUpload:
        def getvalue(self):
            return make_png_bytes()

    with patch.object(config, "TESSERACT_CMD", ""), fake_engine("Upload text"):
        result = ocr.extract_text(FakeUpload())
    assert result.status == ocr.STATUS_SUCCESS


def test_configured_tesseract_path_is_used():
    with patch.object(config, "TESSERACT_CMD", "C:/somewhere/tesseract.exe"):
        assert ocr.find_tesseract_command() == "C:/somewhere/tesseract.exe"


def test_configured_path_that_does_not_exist_is_a_clear_error():
    missing_path = "Z:/definitely/missing/tesseract.exe"
    with patch.object(config, "TESSERACT_CMD", missing_path), fake_engine("x") as engine:
        result = ocr.extract_text(make_png_bytes())
    assert result.status == ocr.STATUS_ERROR
    assert "TESSERACT_CMD" in result.message
    assert missing_path not in result.message
    engine.assert_not_called()


def test_auto_detect_uses_path_when_nothing_configured():
    with patch.object(config, "TESSERACT_CMD", ""), patch("app.ocr.shutil.which", return_value="/usr/bin/tesseract"):
        assert ocr.find_tesseract_command() == "/usr/bin/tesseract"


def test_has_meaningful_text():
    assert ocr.has_meaningful_text("Total 45")
    assert not ocr.has_meaningful_text("-- | ..")
    assert not ocr.has_meaningful_text("")
