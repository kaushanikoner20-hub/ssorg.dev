"""Central configuration for ssorg.dev.

Keep settings here so the UI code in main.py stays easy to read.
This file must not import anything from the rest of the app, which
avoids circular imports.
"""

import os
from pathlib import Path

# ----- Brand -----
APP_NAME = "ssorg.dev"
TAGLINE = "Your screenshots, finally searchable."
ASK_FEATURE_NAME = "Ask ssorg"  # reserved for a later stage
CURRENT_STAGE = "Stage 3: local storage, library and duplicate detection"

# ----- Uploads -----
# Extensions are lowercase and include the dot, e.g. ".png".
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
# Pillow reports these format names after it opens a valid image.
SUPPORTED_IMAGE_FORMATS = ("PNG", "JPEG", "WEBP")
MAX_FILE_SIZE_MB = 20
PREVIEW_MAX_PIXELS = 600  # previews are shrunk to this size before display
PREVIEW_COLUMNS = 3
LIBRARY_PAGE_SIZE = 12  # screenshots shown per page in the library

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ----- Optional .env file -----
# The app works without a .env file. If one exists in the project root, its
# KEY=VALUE lines are read here (no extra package needed). Real environment
# variables always win over the file.
def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]  # remove surrounding quotes
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str) -> str:
    """Read a setting from the environment. An empty value counts as 'not set'."""
    return (os.environ.get(name) or "").strip() or default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


_load_env_file(PROJECT_ROOT / ".env")

# ----- Local storage (Stage 3) -----
# Defaults: everything lives in the "data" folder inside the project.
# Relative paths in the environment variables are relative to the project root.
def _env_path(name: str, default: Path) -> Path:
    value = _env(name, "")
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


DATA_DIR = _env_path("SSORG_DATA_DIR", PROJECT_ROOT / "data")
SCREENSHOT_DIR = _env_path("SSORG_SCREENSHOT_DIR", DATA_DIR / "screenshots")
DATABASE_FILENAME = "ssorg.db"
DATABASE_PATH = _env_path("SSORG_DATABASE_PATH", DATA_DIR / DATABASE_FILENAME)

# ----- OCR (Tesseract) -----
# Leave TESSERACT_CMD empty to auto-detect (PATH, then the usual Windows install folders).
TESSERACT_CMD = _env("TESSERACT_CMD", "")
TESSERACT_LANG = _env("TESSERACT_LANG", "eng")
OCR_TIMEOUT_SECONDS = _env_int("OCR_TIMEOUT_SECONDS", 60)
# Fewer letters/digits than this is treated as "no readable text" (OCR noise).
MIN_MEANINGFUL_CHARACTERS = 3

# ----- Local AI (Ollama + Gemma) -----
DEFAULT_OLLAMA_MODEL = "gemma3:4b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = _env("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)


def _normalize_url(value: str) -> str:
    value = value.strip().rstrip("/")
    return value if "://" in value else "http://" + value


OLLAMA_BASE_URL = _normalize_url(_env("OLLAMA_HOST", DEFAULT_OLLAMA_URL))
OLLAMA_CONNECT_TIMEOUT_SECONDS = 5
# The first request after Ollama starts can be slow while the model loads.
OLLAMA_TIMEOUT_SECONDS = _env_int("OLLAMA_TIMEOUT", 120)
OLLAMA_NUM_CONTEXT = 4096  # model context window requested from Ollama
MAX_AI_TEXT_CHARACTERS = 6000  # longer OCR text is shortened before analysis

AI_CATEGORIES = (
    "Receipt", "Invoice", "Shopping", "Food", "Travel",
    "Education", "Work", "Social Media", "Notes", "Other",
)
AI_CONFIDENCE_LEVELS = ("low", "medium", "high")

# ----- Colors (also mirrored in .streamlit/config.toml) -----
COLOR_BACKGROUND = "#0D100F"
COLOR_SURFACE = "#141A17"
COLOR_SURFACE_RAISED = "#1A221E"
COLOR_BORDER = "#24332C"
COLOR_ACCENT = "#0E9F6E"
COLOR_ACCENT_DEEP = "#047857"
COLOR_TEXT = "#E7EEEA"
COLOR_TEXT_MUTED = "#8C9D95"