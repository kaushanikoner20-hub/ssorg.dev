"""Stage 2: read text from screenshots with Tesseract OCR.

Main function: extract_text(image) -> OcrResult
It never raises for normal problems. Instead it returns a result whose
`status` says what happened:
    "success"  - readable text was found
    "no_text"  - the image was fine but no readable text was found
    "error"    - the image or Tesseract could not be used

Privacy: screenshot text is never logged or printed here.
"""

import io
import importlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from app import config

STATUS_SUCCESS = "success"
STATUS_NO_TEXT = "no_text"
STATUS_ERROR = "error"

MESSAGE_TESSERACT_MISSING = (
    "Tesseract OCR was not found. Install it, then either add it to your PATH "
    "or set TESSERACT_CMD in your .env file. See the README for the steps."
)
MESSAGE_NO_TEXT = (
    "No readable text was found. The screenshot may contain very small, blurry, "
    "handwritten or unsupported text."
)
MESSAGE_PYTESSERACT_MISSING = (
    "The pytesseract Python package is not installed. Install it with: pip install pytesseract."
)


@dataclass
class OcrResult:
    """The outcome of reading one image."""

    status: str
    text: str = ""
    message: str = ""


try:
    pytesseract = importlib.import_module("pytesseract")
except ImportError:
    pytesseract = None


# ----- Finding Tesseract -----
def find_tesseract_command() -> str | None:
    """Return the path to the Tesseract program, or None if we cannot find it.

    Order: the TESSERACT_CMD setting, then the system PATH, then the folders
    the Windows installer normally uses. Nothing here is specific to one computer.
    """
    if config.TESSERACT_CMD:
        return config.TESSERACT_CMD
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    candidates = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / "Tesseract-OCR" / "tesseract.exe")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _configure_tesseract() -> None:
    """Tell pytesseract which Tesseract program to run."""
    pytesseract.pytesseract.tesseract_cmd = find_tesseract_command() or "tesseract"


def check_tesseract() -> tuple[bool, str]:
    """Quick setup check for the UI. Returns (is_ready, message)."""
    if pytesseract is None:
        return False, MESSAGE_PYTESSERACT_MISSING
    if config.TESSERACT_CMD and not Path(config.TESSERACT_CMD).is_file():
        return False, f"TESSERACT_CMD points to a file that does not exist: {config.TESSERACT_CMD}"
    _configure_tesseract()
    try:
        version = pytesseract.get_tesseract_version()
        languages = pytesseract.get_languages(config="")
    except pytesseract.TesseractNotFoundError:
        return False, MESSAGE_TESSERACT_MISSING
    except Exception:
        return False, "Tesseract was found but did not respond correctly."
    if config.TESSERACT_LANG not in languages:
        return False, f"Tesseract is installed, but the '{config.TESSERACT_LANG}' language data is missing."
    return True, f"Tesseract {version} is ready."


# ----- Preparing the image -----
def _load_image(source: Any) -> Image.Image:
    """Turn bytes, a file-like object, an uploaded file or a PIL image into a PIL image.

    Always returns a COPY, so the caller's original image is never changed.
    """
    if isinstance(source, Image.Image):
        return source.copy()
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    elif hasattr(source, "getvalue"):  # Streamlit UploadedFile, BytesIO
        data = source.getvalue()
    elif hasattr(source, "read"):
        data = source.read()
    else:
        raise TypeError("Unsupported image input.")
    image = Image.open(io.BytesIO(data))
    if image.format not in config.SUPPORTED_IMAGE_FORMATS:
        raise ValueError("Unsupported image format.")
    image.load()  # read the pixels now so broken files fail here
    return image


def _prepare_for_ocr(image: Image.Image) -> Image.Image:
    """Return an RGB copy that Tesseract can read.

    Transparent images are placed on a white background; otherwise dark text
    on a transparent PNG would turn into black-on-black.
    """
    image = ImageOps.exif_transpose(image)  # respect phone rotation info
    has_transparency = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_transparency:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _clean_text(raw_text: str) -> str:
    """Trim spaces and squeeze long runs of blank lines."""
    lines = [line.rstrip() for line in raw_text.replace("\x0c", "").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def has_meaningful_text(text: str) -> bool:
    """True if the text has enough letters or digits to be worth analyzing."""
    letters_and_digits = sum(character.isalnum() for character in text)
    return letters_and_digits >= config.MIN_MEANINGFUL_CHARACTERS


# ----- The main function -----
def extract_text(source: Any) -> OcrResult:
    """Read the text in one image. `source` can be bytes, an uploaded file or a PIL image."""
    if pytesseract is None:
        return OcrResult(STATUS_ERROR, message=MESSAGE_PYTESSERACT_MISSING)
    try:
        image = _load_image(source)
    except Exception:  # Pillow can raise several error types for broken files
        return OcrResult(STATUS_ERROR, message="This file could not be read as a supported image.")

    if config.TESSERACT_CMD and not Path(config.TESSERACT_CMD).is_file():
        return OcrResult(
            STATUS_ERROR,
            message=f"TESSERACT_CMD points to a file that does not exist: {config.TESSERACT_CMD}",
        )
    _configure_tesseract()

    try:
        prepared = _prepare_for_ocr(image)
        raw_text = pytesseract.image_to_string(
            prepared,
            lang=config.TESSERACT_LANG,
            timeout=config.OCR_TIMEOUT_SECONDS,
        )
    except pytesseract.TesseractNotFoundError:
        return OcrResult(STATUS_ERROR, message=MESSAGE_TESSERACT_MISSING)
    except pytesseract.TesseractError:
        return OcrResult(
            STATUS_ERROR,
            message=(
                "Tesseract could not process this image. Check that the "
                f"'{config.TESSERACT_LANG}' language data is installed."
            ),
        )
    except RuntimeError:  # pytesseract raises RuntimeError when the timeout is hit
        return OcrResult(
            STATUS_ERROR,
            message=f"Reading this image took longer than {config.OCR_TIMEOUT_SECONDS} seconds and was stopped.",
        )
    except Exception:
        return OcrResult(STATUS_ERROR, message="Something went wrong while reading this image.")

    text = _clean_text(raw_text or "")
    if not has_meaningful_text(text):
        return OcrResult(STATUS_NO_TEXT, message=MESSAGE_NO_TEXT)
    return OcrResult(STATUS_SUCCESS, text=text)