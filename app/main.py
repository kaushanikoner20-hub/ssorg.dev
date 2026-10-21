"""ssorg.dev - Stage 3: dashboard UI, OCR, local Gemma analysis and a saved screenshot library.

Run from the project root with:
    streamlit run app/main.py

OCR (Tesseract) and AI analysis (Gemma through local Ollama) work.
Screenshots are saved in data/screenshots and described in data/ssorg.db (SQLite).
Keyword search and Ask ssorg do NOT exist yet.
"""

import html
import io
import re
import sys
from datetime import datetime
from pathlib import Path
from string import Template

import streamlit as st
from PIL import Image

# Streamlit puts the "app" folder on the import path, not the project root.
# Adding the root lets us write "from app import config" everywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import config, database, gemma, ocr, processor, storage  # noqa: E402  (must come after the path fix above)

# ----- Navigation -----
PAGE_DASHBOARD = "Dashboard"
PAGE_ALL = "All Screenshots"
PAGE_SEARCH = "Search"
PAGE_ASK = "Ask ssorg"
PAGE_SETTINGS = "Settings"
PAGES = [PAGE_DASHBOARD, PAGE_ALL, PAGE_SEARCH, PAGE_ASK, PAGE_SETTINGS]
UNFINISHED_PAGES = [PAGE_SEARCH, PAGE_ASK, PAGE_SETTINGS]

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
.ss-label { color: $muted; font-size: 0.85rem; margin: 0.9rem 0 0.15rem 0; }

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


def escape_markdown(text):
    """Make text safe to show with st.markdown, so it is displayed literally.

    OCR text and AI answers are untrusted. Without this, text like
    ![x](http://...) could make the browser load a remote image (a way to leak
    information), and links or emoji codes would be rendered. A backslash before
    any punctuation character turns it into plain text.
    """
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", text).replace("\n", "  \n")


STATUS_LABELS = {
    database.STATUS_COMPLETE: "Analyzed",
    database.STATUS_PENDING: "Analysis pending",
    database.STATUS_NO_TEXT: "No readable text",
    database.STATUS_OCR_FAILED: "OCR failed",
    database.STATUS_AI_FAILED: "AI analysis failed",
}


def status_label(status):
    return STATUS_LABELS.get(status, "Unknown")


def format_import_date(created_at):
    """Show the stored UTC timestamp in the computer's local time."""
    try:
        return datetime.fromisoformat(created_at).astimezone().strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError):
        return "Unknown"


def shorten(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def load_record_image(record, max_pixels=None):
    """Return a PIL image for a library record, or None if the file is missing or unreadable."""
    data = storage.read_stored_file(record["stored_filename"])
    if data is None:
        return None
    try:
        image = Image.open(io.BytesIO(data))
        size = max_pixels or config.PREVIEW_MAX_PIXELS
        image.thumbnail((size, size))
        return image
    except Exception:
        return None


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


# ----- Library state callbacks (they run before the page reruns) -----
def open_screenshot(screenshot_id):
    st.session_state.selected_id = screenshot_id
    st.session_state.confirm_delete_id = None
    st.session_state.page = PAGE_ALL


def close_detail():
    st.session_state.selected_id = None
    st.session_state.confirm_delete_id = None


def show_more_screenshots():
    current = st.session_state.get("library_limit", config.LIBRARY_PAGE_SIZE)
    st.session_state.library_limit = current + config.LIBRARY_PAGE_SIZE


def ask_delete_confirmation(screenshot_id):
    st.session_state.confirm_delete_id = screenshot_id


def cancel_delete():
    st.session_state.confirm_delete_id = None


def confirm_delete(screenshot_id):
    result = processor.delete_screenshot(screenshot_id)
    st.session_state.flash = ("success" if result.success else "warning", result.message)
    st.session_state.selected_id = None
    st.session_state.confirm_delete_id = None


def dismiss_import_results():
    st.session_state.import_results = []


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
            key="page",
            format_func=lambda page: f"{page} (coming soon)" if page in UNFINISHED_PAGES else page,
        )
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            '<div class="ss-privacy">Designed for local-first processing. '
            "Your screenshots and the library database are stored on this computer. "
            "OCR runs locally, and the extracted text goes only to your local Ollama "
            "service. No cloud AI is used.</div>",
            unsafe_allow_html=True,
        )
    return selected_page


# ----- Dashboard sections -----
def render_header():
    st.markdown('<h1 class="ss-title">Welcome to ssorg.dev</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="ss-subtitle">{config.TAGLINE}</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ss-lead">ssorg.dev reads the text in your screenshots with Tesseract OCR, '
        "sorts and summarizes them with a local Gemma model, and keeps them in a library "
        "on your own computer. Exact duplicates are skipped. "
        "Keyword search and Ask ssorg are not available yet.</p>",
        unsafe_allow_html=True,
    )


def render_stat_cards():
    st.markdown('<p class="ss-section">Your library</p>', unsafe_allow_html=True)
    try:
        total = database.get_screenshot_count()
        category_counts = database.get_category_counts()
        recent = database.get_recent_screenshot_count(7)
    except database.DatabaseError:
        st.error("The screenshot library could not be read, so the numbers cannot be shown.")
        return
    st.markdown(
        '<p class="ss-hint">Everything here is stored on this computer, in the data folder.</p>',
        unsafe_allow_html=True,
    )
    if category_counts:
        top = ", ".join(f"{name} ({count})" for name, count in list(category_counts.items())[:3])
        category_note = html.escape(top)
    else:
        category_note = "Categories appear after screenshots are analyzed."
    total_note = "Saved in your library." if total else "Your library is empty. Import a screenshot above."
    col_total, col_categories, col_recent = st.columns(3)
    with col_total:
        st.markdown(stat_card_html("Total screenshots", str(total), total_note), unsafe_allow_html=True)
    with col_categories:
        st.markdown(stat_card_html("Categories", str(len(category_counts)), category_note), unsafe_allow_html=True)
    with col_recent:
        st.markdown(stat_card_html("Recently added", str(recent), "Added in the last 7 days."), unsafe_allow_html=True)


def render_upload_section():
    st.markdown('<p class="ss-section">Add screenshots</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ss-hint">PNG, JPG, JPEG or WEBP, up to '
        f"{config.MAX_FILE_SIZE_MB} MB each. New screenshots are saved to your library when you click Process screenshots.</p>",
        unsafe_allow_html=True,
    )

    # Session state survives Streamlit reruns (every click reruns this script).
    st.session_state.setdefault("removed_file_ids", set())
    st.session_state.setdefault("uploader_key", 0)
    st.session_state.setdefault("import_results", [])  # outcome of the last import, kept across reruns

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
        st.markdown(f"**{len(valid_files)} selected** (selected, not in your library yet)")
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
        process_clicked = st.button(
            "Process screenshots", type="primary", disabled=not valid_files, key="process_button"
        )
    with clear_col:
        st.button("Clear selection", on_click=clear_selection, disabled=not uploaded_files, key="clear_button")
    st.markdown(
        '<div class="ss-privacy">Each new screenshot is saved on this computer (data/screenshots) and '
        "described in a local SQLite database. Text is read with Tesseract. The extracted text "
        f"(not the image) is sent to your local Ollama service, model {config.OLLAMA_MODEL}. "
        "Nothing leaves your computer for a cloud service.</div>",
        unsafe_allow_html=True,
    )

    if process_clicked:
        run_import(valid_files)
    render_import_results()
    render_setup_check()


def run_import(valid_files):
    """Import the selected screenshots into the library, then reset the uploader."""
    items = [(uploaded_file.name, uploaded_file.getvalue()) for _, uploaded_file in valid_files]
    progress_bar = st.progress(0.0, text="Starting...")

    def show_progress(index, total, filename):
        progress_bar.progress(index / total, text=f"Importing {filename} ({index + 1} of {total})")

    st.session_state.import_results = processor.import_screenshots(items, on_progress=show_progress)
    progress_bar.empty()
    clear_selection()  # the files are in the library now; start with a fresh uploader
    st.rerun()


def show_labeled_value(label, value):
    """Show a small label and a literal (escaped) text value."""
    st.markdown(f'<p class="ss-label">{label}</p>', unsafe_allow_html=True)
    st.markdown(escape_markdown(value))


def render_record_details(record, key_prefix):
    """Show the metadata and OCR text of one library record."""
    status = record["processing_status"]
    # Category and status come from fixed lists, but they are escaped anyway because they come from the database.
    badges = f'<span class="ss-badge ss-badge-soon">{html.escape(status_label(status))}</span>'
    if record["category"]:
        badges = f'<span class="ss-badge ss-badge-now">{html.escape(record["category"])}</span> ' + badges
    if record["confidence"]:
        badges += f' <span class="ss-badge ss-badge-soon">Confidence: {html.escape(record["confidence"])}</span>'
    st.markdown(badges, unsafe_allow_html=True)

    if record["processing_error"] and status != database.STATUS_COMPLETE:
        st.warning(record["processing_error"])
    if status == database.STATUS_NO_TEXT:
        st.warning(ocr.MESSAGE_NO_TEXT)

    if record["short_summary"]:
        show_labeled_value("Summary", record["short_summary"])
        show_labeled_value("Important dates", ", ".join(record["important_dates"]) or "None found in the text")
        show_labeled_value("Named entities", ", ".join(record["named_entities"]) or "None found in the text")
        show_labeled_value("Useful search terms", ", ".join(record["useful_search_terms"]) or "None")

    show_labeled_value("Imported", format_import_date(record["created_at"]))
    show_labeled_value("Original filename", record["original_filename"])
    if record["ocr_text"]:
        st.markdown('<p class="ss-label">Extracted text</p>', unsafe_allow_html=True)
        st.text_area(
            "Extracted text",
            value=record["ocr_text"],
            height=180,
            disabled=True,
            label_visibility="collapsed",
            key=f"{key_prefix}_ocr_{record['id']}",
        )


def render_import_result(index, result):
    """Show what happened to one uploaded file."""
    name = escape_markdown(result.filename)
    if result.outcome == processor.OUTCOME_FAILED:
        st.error(f"{name}: {result.message}")
        return
    if result.outcome == processor.OUTCOME_DUPLICATE:
        st.info(f"{name}: {result.message}")
        if result.screenshot_id is not None:
            st.button("View existing screenshot", key=f"view_dup_{index}", on_click=open_screenshot,
                      args=(result.screenshot_id,))
        return

    # A new screenshot was saved. It may still have OCR or AI problems.
    try:
        record = database.get_screenshot_by_id(result.screenshot_id)
    except database.DatabaseError:
        record = None
    label = status_label(result.processing_status)
    with st.expander(f"{name} - saved, {label}", expanded=index == 0):
        if result.processing_status == database.STATUS_COMPLETE:
            st.success("Saved to your library and analyzed locally.")
        else:
            st.warning(f"Saved to your library. {result.message}".strip())
        if record is not None:
            render_record_details(record, key_prefix=f"import{index}")
            st.button("Open in library", key=f"view_new_{index}", on_click=open_screenshot, args=(record["id"],))


def render_import_results():
    results = st.session_state.get("import_results") or []
    if not results:
        return
    st.markdown('<p class="ss-section">Import results</p>', unsafe_allow_html=True)
    imported = sum(r.outcome == processor.OUTCOME_IMPORTED for r in results)
    duplicates = sum(r.outcome == processor.OUTCOME_DUPLICATE for r in results)
    failed = sum(r.outcome == processor.OUTCOME_FAILED for r in results)
    st.caption(f"{imported} saved, {duplicates} already in your library, {failed} failed.")
    for index, result in enumerate(results):
        render_import_result(index, result)
    if duplicates:
        st.caption(
            "Duplicates are found by comparing the exact file contents (SHA-256). Images that look "
            "the same but were saved with a different encoding or metadata may not be detected."
        )
    st.button("Dismiss results", on_click=dismiss_import_results, key="dismiss_import_results")


def render_setup_check():
    """A button that checks Tesseract and Ollama without processing anything."""
    with st.expander("Check OCR and AI setup"):
        st.caption(
            "Checks that Tesseract and your local Ollama model can be reached. "
            "No screenshot is processed."
        )
        if st.button("Run check", key="setup_check_button"):
            for is_ready, message in (ocr.check_tesseract(), gemma.check_ollama()):
                if is_ready:
                    st.success(message)
                else:
                    st.error(message)


def render_how_it_works():
    st.markdown('<p class="ss-section">How it works</p>', unsafe_allow_html=True)
    steps = [
        ("1. Import", "Add screenshots. They are saved locally and exact duplicates are skipped.", "Works now", "now"),
        ("2. Extract", "Read the text inside each image with Tesseract.", "Works now", "now"),
        ("3. Organize", "Categorize and summarize with Gemma through local Ollama.", "Works now", "now"),
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
        ("Keyword search", "Type a word and see the screenshots that contain it."),
        (config.ASK_FEATURE_NAME, "Ask questions about your whole screenshot collection in plain language."),
    ]
    columns = st.columns(2)
    for column, (title, text) in zip(columns, features):
        with column:
            st.markdown(card_html(title, text, "Not implemented yet"), unsafe_allow_html=True)


# ----- Library -----
def show_flash():
    """Show a one-time message left by an action (such as delete)."""
    flash = st.session_state.pop("flash", None)
    if flash:
        kind, message = flash
        (st.success if kind == "success" else st.warning)(message)


def render_library_card(record):
    with st.container(border=True):
        image = load_record_image(record)
        if image is not None:
            st.image(image)
        else:
            st.warning("The image file for this record is missing.")
        st.caption(escape_markdown(record["original_filename"]))
        badges = f'<span class="ss-badge ss-badge-soon">{html.escape(status_label(record["processing_status"]))}</span>'
        if record["category"]:
            badges = f'<span class="ss-badge ss-badge-now">{html.escape(record["category"])}</span> ' + badges
        st.markdown(badges, unsafe_allow_html=True)
        if record["short_summary"]:
            st.markdown(escape_markdown(shorten(record["short_summary"], 110)))
        st.caption(f"Imported {format_import_date(record['created_at'])}")
        st.button("View details", key=f"view_{record['id']}", on_click=open_screenshot, args=(record["id"],))


def render_delete_controls(record):
    """Delete needs a second, explicit confirmation."""
    if st.session_state.get("confirm_delete_id") == record["id"]:
        st.warning(
            "Delete this screenshot permanently? The image file and its saved text and analysis "
            "will be removed from this computer. This cannot be undone."
        )
        yes_column, cancel_column = st.columns(2)
        with yes_column:
            st.button("Yes, delete permanently", type="primary", key=f"confirm_delete_{record['id']}",
                      on_click=confirm_delete, args=(record["id"],))
        with cancel_column:
            st.button("Cancel", key=f"cancel_delete_{record['id']}", on_click=cancel_delete)
    else:
        st.button("Delete screenshot", key=f"delete_{record['id']}", on_click=ask_delete_confirmation,
                  args=(record["id"],))


def show_screenshot_detail(screenshot_id):
    try:
        record = database.get_screenshot_by_id(screenshot_id)
    except database.DatabaseError:
        st.error("The screenshot library could not be read.")
        return
    st.button("Back to library", key="back_to_library", on_click=close_detail)
    if record is None:
        st.session_state.selected_id = None
        st.warning("This screenshot is no longer in the library.")
        return

    image_column, detail_column = st.columns([1, 1])
    with image_column:
        image = load_record_image(record, max_pixels=1000)
        if image is not None:
            st.image(image)
        else:
            st.warning(
                "The image file for this record is missing from the screenshots folder. "
                "The saved text and analysis are still shown. You can delete the record."
            )
    with detail_column:
        render_record_details(record, key_prefix="detail")
        if record["processing_status"] in processor.RERUNNABLE_STATUSES:
            if st.button("Re-run analysis", key=f"rerun_{record['id']}"):
                with st.spinner("Reading and analyzing locally..."):
                    result = processor.reprocess_screenshot(record["id"])
                st.session_state.flash = (
                    "warning" if result.outcome == processor.OUTCOME_FAILED or result.message else "success",
                    result.message or "The analysis was updated.",
                )
                st.rerun()
        render_delete_controls(record)


def show_library():
    st.markdown('<h1 class="ss-title">All Screenshots</h1>', unsafe_allow_html=True)
    st.markdown('<p class="ss-subtitle">Everything you have imported, stored on this computer.</p>', unsafe_allow_html=True)
    show_flash()
    try:
        total = database.get_screenshot_count()
        selected_id = st.session_state.get("selected_id")
        if selected_id is not None:
            show_screenshot_detail(selected_id)
            return
        limit = st.session_state.get("library_limit", config.LIBRARY_PAGE_SIZE)
        records = database.get_all_screenshots(limit=limit)
    except database.DatabaseError:
        st.error("The screenshot library could not be read. Check that the data folder is available.")
        return

    if total == 0:
        st.markdown(
            card_html("Your library is empty",
                      "Go to the Dashboard, choose some screenshots and click Process screenshots. "
                      "They will be saved here."),
            unsafe_allow_html=True,
        )
        return

    st.markdown(f"**{total}** {'screenshot' if total == 1 else 'screenshots'} stored on this computer")
    for row_start in range(0, len(records), config.PREVIEW_COLUMNS):
        columns = st.columns(config.PREVIEW_COLUMNS)
        for column, record in zip(columns, records[row_start:row_start + config.PREVIEW_COLUMNS]):
            with column:
                render_library_card(record)
    if total > len(records):
        st.button("Show more", key="show_more", on_click=show_more_screenshots)


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
            f"Your library is stored in {html.escape(str(config.DATA_DIR))} "
            f"(database file: {html.escape(config.DATABASE_FILENAME)}). "
            "Changing settings here is not available yet. See .env.example for what you can set.",
            "Not implemented yet",
        ),
        unsafe_allow_html=True,
    )


# ----- Entry point -----
def main():
    st.set_page_config(page_title=f"{config.APP_NAME} | {config.TAGLINE}", layout="wide")
    load_css()
    page = render_sidebar()
    try:
        database.initialize_database()  # creates data/ssorg.db the first time
    except database.DatabaseError as error:
        st.error(f"{error} Check that the data folder exists and can be written to.")

    if page == PAGE_DASHBOARD:
        show_dashboard()
    elif page == PAGE_ALL:
        show_library()
    elif page == PAGE_SEARCH:
        show_coming_soon_page("Search", "Find a screenshot by the words inside it.", preview_search)
    elif page == PAGE_ASK:
        show_coming_soon_page(config.ASK_FEATURE_NAME, "Ask questions about your screenshots.", preview_ask)
    else:
        show_coming_soon_page("Settings", "Tune how ssorg.dev works on your computer.", preview_settings)


if __name__ == "__main__":
    main()