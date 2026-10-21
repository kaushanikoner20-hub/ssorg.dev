"""Central configuration for ssorg.dev.

Keep settings here so the UI code in main.py stays easy to read.
This file must not import anything from the rest of the app, which
avoids circular imports.
"""

from pathlib import Path

# ----- Brand -----
APP_NAME = "ssorg.dev"
TAGLINE = "Your screenshots, finally searchable."
ASK_FEATURE_NAME = "Ask ssorg"  # reserved for a later stage
CURRENT_STAGE = "Stage 1: UI and upload preview"

# ----- Uploads -----
# Extensions are lowercase and include the dot, e.g. ".png".
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
# Pillow reports these format names after it opens a valid image.
SUPPORTED_IMAGE_FORMATS = ("PNG", "JPEG", "WEBP")
MAX_FILE_SIZE_MB = 20
PREVIEW_MAX_PIXELS = 600  # previews are shrunk to this size before display
PREVIEW_COLUMNS = 3

# ----- Paths (planned for later stages; nothing is created in Stage 1) -----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "data" / "screenshots"
DATABASE_FILENAME = "ssorg.db"  # planned SQLite file, not created yet
DATABASE_PATH = PROJECT_ROOT / "data" / DATABASE_FILENAME

# ----- Colors (also mirrored in .streamlit/config.toml) -----
COLOR_BACKGROUND = "#0D100F"
COLOR_SURFACE = "#141A17"
COLOR_SURFACE_RAISED = "#1A221E"
COLOR_BORDER = "#24332C"
COLOR_ACCENT = "#0E9F6E"
COLOR_ACCENT_DEEP = "#047857"
COLOR_TEXT = "#E7EEEA"
COLOR_TEXT_MUTED = "#8C9D95"