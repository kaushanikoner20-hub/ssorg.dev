"""ssorg.dev - Stage 1: project foundation, dashboard UI and upload preview.

Run from the project root with:
    streamlit run app/main.py

Stage 1 does NOT do OCR, AI, database storage or search.
Uploaded images are only held in memory for the current session.
"""

import io
import sys
from pathlib import Path
from string import Template

import streamlit as st
from PIL import Image

# Streamlit puts the "app" folder on the import path, not the project root.
# Adding the root lets us write "from app import config" everywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import config  # noqa: E402  (must come after the path fix above)

# ----- Navigation -----
PAGE_DASHBOARD = "Dashboard"
PAGE_ALL = "All Screenshots"
PAGE_SEARCH = "Search"
PAGE_ASK = "Ask ssorg"
PAGE_SETTINGS = "Settings"
PAGES = [PAGE_DASHBOARD, PAGE_ALL, PAGE_SEARCH, PAGE_ASK, PAGE_SETTINGS]
UNFINISHED_PAGES = [PAGE_ALL, PAGE_SEARCH, PAGE_ASK, PAGE_SETTINGS]

# ----- Styling -----
# $name placeholders are filled from config.py by string.Template.
CSS_TEMPLATE = Template("""
<style>
.block-container { max-width: 1080px; padding-top: 2.5rem; padding-bottom: 4rem; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { border-right: 1px solid $border; }

h1, h2, h3 { letter-spacing: -0.02em; }
.ss-title { font-size: 2.6rem; font-weight: 650; line-height: 1.15; margin: 0; }
.ss-subtitle { font-size: 1.2rem; color: $muted; margin: 0.4rem 0 1.6rem 0; }
.ss-lead { color: $muted; max-width: 62ch; line-height: 1.65; }
.ss-section { font-size: 1.25rem; font-weight: 600; margin: 2.4rem 0 0.4rem 0; }
.ss-hint { color: $muted; font-size: 0.92rem; margin-bottom: 0.8rem; }

.ss-logo { font-family: "Cascadia Code", Consolas, monospace; font-size: 1.35rem;
           font-weight: 700; margin: 0; }
.ss-logo span { color: $accent; }
.ss-logo-tag { color: $muted; font-size: 0.85rem; margin: 0.15rem 0 1.2rem 0; }

.ss-card { background: $surface; border: 1px solid $border; border-radius: 14px;
           padding: 1.2rem 1.35rem; height: 100%; }
.ss-card-title { font-weight: 600; margin: 0 0 0.35rem 0; }
.ss-card-text { color: $muted; font-size: 0.93rem; line-height: 1.55; margin: 0; }
.ss-stat-label { color: $muted; font-size: 0.9rem; margin: 0; }
.ss-stat-value { font-size: 2.2rem; font-weight: 650; margin: 0.2rem 0; }

.ss-badge { display: inline-block; font-size: 0.78rem; padding: 0.12rem 0.6rem;
            border-radius: 999px; margin-bottom: 0.6rem; }
.ss-badge-now { background: rgba(14, 159, 110, 0.15); color: #34d399;
                border: 1px solid $accent_deep; }
.ss-badge-soon { background: transparent; color: $muted; border: 1px solid $border; }

.ss-privacy { background: $surface_raised; border: 1px solid $border;
              border-left: 3px solid $accent; border-radius: 10px;
              padding: 0.7rem 0.85rem; color: $muted; font-size: 0.85rem; }

[data-testid="stFileUploaderDropzone"] { border: 1.5px dashed $accent_deep;
              border-radius: 14px; background: $surface; padding: 1.6rem; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: $accent; }
.stButton > button { border-radius: 10px; }

@media (max-width: 640px) {
  .ss-title { font-size: 2rem; }
  .block-container { padding-top: 1.5rem; }
}
</style>
""")


def load_css():
    """Inject the custom CSS, filling in colors from config.py."""
    css = CSS_TEMPLATE.substitute(
        border=config.COLOR_BORDER,
        muted=config.COLOR_TEXT_MUTED,
        accent=config.COLOR_ACCENT,
        accent_deep=config.COLOR_ACCENT_DEEP,
        surface=config.COLOR_SURFACE,
        surface_raised=config.COLOR_SURFACE_RAISED,
    )
    st.markdown(css, unsafe_allow_html=True)


# ----- Small HTML helpers -----
# Only fixed text written in this file goes through these helpers.
# File names from users are shown with st.caption, never as raw HTML.
def card_html(title, text, badge=None, badge_style="soon"):
    """Return the HTML for a simple rounded card with an optional badge."""
    badge_html = f'<span class="ss-badge ss-badge-{badge_style}">{badge}</span><br>' if badge else ""
    return (
        f'<div class="ss-card">{badge_html}'
        f'<p class="ss-card-title">{title}</p>'
        f'<p class="ss-card-text">{text}</p></div>'
    )


def stat_card_html(label, value, note):
    """Return the HTML for a dashboard stat card."""
    return (
        f'<div class="ss-card"><p class="ss-stat-label">{label}</p>'
        f'<p class="ss-stat-value">{value}</p>'
        f'<p class="ss-card-text">{note}</p></div>'
    )


# ----- Upload helpers -----
def get_file_id(uploaded_file):
    """Give each uploaded file a stable id so we can track removals."""
    return getattr(uploaded_file, "file_id", f"{uploaded_file.name}-{uploaded_file.size}")


def check_uploaded_image(uploaded_file):
    """Check one uploaded file. Returns (is_valid, friendly_message)."""
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in config.SUPPORTED_EXTENSIONS:
        supported = ", ".join(config.SUPPORTED_EXTENSIONS)
        return False, f"This file type is not supported. Please use one of: {supported}."

    size_in_mb = uploaded_file.size / (1024 * 1024)
    if size_in_mb > config.MAX_FILE_SIZE_MB:
        return False, f"This file is {size_in_mb:.1f} MB. The limit is {config.MAX_FILE_SIZE_MB} MB."

    try:
        with Image.open(io.BytesIO(uploaded_file.getvalue())) as image:
            image.verify()  # catches corrupted or fake image files
            image_format = image.format
    except Exception:  # Pillow can raise several error types for broken files
        return False, "This file could not be read as an image. It may be corrupted."

    if image_format not in config.SUPPORTED_IMAGE_FORMATS:
        return False, f"The image format ({image_format}) is not supported."
    return True, ""


def make_preview(uploaded_file):
    """Return a small copy of the image for display."""
    image = Image.open(io.BytesIO(uploaded_file.getvalue()))
    image.thumbnail((config.PREVIEW_MAX_PIXELS, config.PREVIEW_MAX_PIXELS))
    return image


def remove_file(file_id):
    """Hide one file from the current selection."""
    st.session_state.removed_file_ids.add(file_id)


def clear_selection():
    """Reset the uploader and forget removals. A new key makes a fresh uploader."""
    st.session_state.uploader_key += 1
    st.session_state.removed_file_ids = set()


# ----- Sidebar -----
def render_sidebar():
    """Draw the sidebar and return the selected page name."""
    with st.sidebar:
        st.markdown(
            '<p class="ss-logo">ssorg<span>.dev</span></p>'
            f'<p class="ss-logo-tag">{config.TAGLINE}</p>',
            unsafe_allow_html=True,
        )
        selected_page = st.radio(
            "Navigation",
            PAGES,
            label_visibility="collapsed",
            format_func=lambda page: f"{page} (coming soon)" if page in UNFINISHED_PAGES else page,
        )
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            '<div class="ss-privacy">Designed for local-first processing. '
            "In Stage 1, selected images stay in memory for this session only "
            "and are not saved.</div>",
            unsafe_allow_html=True,
        )
    return selected_page


# ----- Dashboard sections -----
def render_header():
    st.markdown('<h1 class="ss-title">Welcome to ssorg.dev</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="ss-subtitle">{config.TAGLINE}</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ss-lead">ssorg.dev is being built to read the text in your screenshots, '
        "sort them into categories, and let you search or ask questions about them, "
        "all on your own computer. Right now you can add screenshots and preview them. "
        "Nothing else works yet.</p>",
        unsafe_allow_html=True,
    )


def render_stat_cards():
    st.markdown('<p class="ss-section">Your library</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ss-hint">No database exists yet, so these are empty on purpose.</p>',
        unsafe_allow_html=True,
    )
    col_total, col_categories, col_recent = st.columns(3)
    with col_total:
        st.markdown(stat_card_html("Total screenshots", "0", "Nothing stored yet. Saving arrives in a later stage."), unsafe_allow_html=True)
    with col_categories:
        st.markdown(stat_card_html("Categories", "0", "Categories appear after AI categorization is built."), unsafe_allow_html=True)
    with col_recent:
        st.markdown(stat_card_html("Recently added", "None", "Your recent imports will be listed here."), unsafe_allow_html=True)


def render_upload_section():
    st.markdown('<p class="ss-section">Add screenshots</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ss-hint">PNG, JPG, JPEG or WEBP, up to '
        f"{config.MAX_FILE_SIZE_MB} MB each. Files are previewed here and are not saved.</p>",
        unsafe_allow_html=True,
    )

    # Session state survives Streamlit reruns (every click reruns this script).
    st.session_state.setdefault("removed_file_ids", set())
    st.session_state.setdefault("uploader_key", 0)

    uploaded_files = st.file_uploader(
        "Drop screenshots here or browse",
        type=[extension.lstrip(".") for extension in config.SUPPORTED_EXTENSIONS],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}",
    )

    # Validate every file that has not been removed from the selection.
    valid_files = []
    for uploaded_file in uploaded_files or []:
        file_id = get_file_id(uploaded_file)
        if file_id in st.session_state.removed_file_ids:
            continue
        is_valid, message = check_uploaded_image(uploaded_file)
        if is_valid:
            valid_files.append((file_id, uploaded_file))
        else:
            st.warning(f"**{uploaded_file.name}** was skipped. {message}")

    if valid_files:
        st.markdown(f"**{len(valid_files)} selected** (preview only, not saved)")
        for row_start in range(0, len(valid_files), config.PREVIEW_COLUMNS):
            columns = st.columns(config.PREVIEW_COLUMNS)
            row_files = valid_files[row_start:row_start + config.PREVIEW_COLUMNS]
            for column, (file_id, uploaded_file) in zip(columns, row_files):
                with column, st.container(border=True):
                    st.image(make_preview(uploaded_file))
                    st.caption(uploaded_file.name)
                    st.button("Remove", key=f"remove_{file_id}", on_click=remove_file, args=(file_id,))

    process_col, clear_col = st.columns([2, 1])
    with process_col:
        st.button("Process screenshots", type="primary", disabled=True, key="process_button")
    with clear_col:
        st.button("Clear selection", on_click=clear_selection, disabled=not uploaded_files, key="clear_button")
    st.info(
        "Processing is not available in Stage 1. It will be added in a later stage. "
        "Your selected images are not saved anywhere."
    )


def render_how_it_works():
    st.markdown('<p class="ss-section">How it works</p>', unsafe_allow_html=True)
    steps = [
        ("1. Import", "Add screenshots from your computer.", "Preview works now", "now"),
        ("2. Extract", "Read the text inside each image.", "Coming soon", "soon"),
        ("3. Organize", "Categorize and summarize with a local AI model.", "Coming soon", "soon"),
        ("4. Search", "Find screenshots by keyword or ask questions.", "Coming soon", "soon"),
    ]
    columns = st.columns(4)
    for column, (title, text, badge, style) in zip(columns, steps):
        with column:
            st.markdown(card_html(title, text, badge, style), unsafe_allow_html=True)


def render_coming_soon_cards():
    st.markdown('<p class="ss-section">Coming soon</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ss-hint">These features are not implemented yet. The cards below are previews of the plan.</p>',
        unsafe_allow_html=True,
    )
    features = [
        ("OCR text extraction", "Pull readable text out of every screenshot using Tesseract on your machine."),
        ("Gemma AI categorization", "Sort and summarize screenshots with Gemma running locally through Ollama."),
        ("Keyword search", "Type a word and see the screenshots that contain it."),
        (config.ASK_FEATURE_NAME, "Ask questions about your whole screenshot collection in plain language."),
    ]
    for row_start in (0, 2):
        columns = st.columns(2)
        for column, (title, text) in zip(columns, features[row_start:row_start + 2]):
            with column:
                st.markdown(card_html(title, text, "Not implemented yet"), unsafe_allow_html=True)
        st.markdown("<div style='height: 0.8rem'></div>", unsafe_allow_html=True)


# ----- Pages -----
def show_dashboard():
    render_header()
    render_upload_section()
    render_stat_cards()
    render_how_it_works()
    render_coming_soon_cards()


def show_coming_soon_page(title, description, preview_function=None):
    """Shared layout for pages that are not built yet."""
    st.markdown(f'<h1 class="ss-title">{title}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="ss-subtitle">{description}</p>', unsafe_allow_html=True)
    st.info(f"{title} is not implemented yet. This page is a non-functional preview.")
    if preview_function:
        preview_function()


def preview_all_screenshots():
    st.markdown(
        stat_card_html("Your screenshots", "0", "A browsable gallery will appear here once screenshots can be saved."),
        unsafe_allow_html=True,
    )


def preview_search():
    st.text_input("Search your screenshots", placeholder="Search will be available in a later stage", disabled=True)


def preview_ask():
    st.text_input(
        f"{config.ASK_FEATURE_NAME}",
        placeholder="For example: which screenshot has my flight confirmation?",
        disabled=True,
    )
    st.caption("Example only. Asking questions is not implemented yet.")


def preview_settings():
    st.markdown(
        card_html(
            "Planned configuration",
            f"Database file: {config.DATABASE_FILENAME} (not created yet). "
            "OCR and local AI model settings will be added in later stages.",
            "Not implemented yet",
        ),
        unsafe_allow_html=True,
    )


# ----- Entry point -----
def main():
    st.set_page_config(page_title=f"{config.APP_NAME} | {config.TAGLINE}", layout="wide")
    load_css()
    page = render_sidebar()

    if page == PAGE_DASHBOARD:
        show_dashboard()
    elif page == PAGE_ALL:
        show_coming_soon_page("All Screenshots", "Browse everything you have imported.", preview_all_screenshots)
    elif page == PAGE_SEARCH:
        show_coming_soon_page("Search", "Find a screenshot by the words inside it.", preview_search)
    elif page == PAGE_ASK:
        show_coming_soon_page(config.ASK_FEATURE_NAME, "Ask questions about your screenshots.", preview_ask)
    else:
        show_coming_soon_page("Settings", "Tune how ssorg.dev works on your computer.", preview_settings)


if __name__ == "__main__":
    main()