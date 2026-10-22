"""Tests for keyword search (app/search.py and database.search_screenshot_rows).

Every test uses a temporary database. OCR, Gemma and the network are never used.
"""

import sqlite3
from datetime import date, timedelta
from unittest.mock import patch

from app import config, database, search


def db_path(tmp_path):
    return tmp_path / "library" / "ssorg.db"


def add(path, number, **fields):
    """Add a record. Keyword arguments set any database field."""
    values = dict(
        original_filename=f"shot{number}.png",
        stored_filename=f"{number:032x}.png",
        file_hash=f"hash{number}",
        file_size=100,
        mime_type="image/png",
        processing_status=database.STATUS_COMPLETE,
        db_path=path,
    )
    values.update(fields)
    return database.add_screenshot(**values)


def set_created_at(path, screenshot_id, timestamp):
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE screenshots SET created_at = ? WHERE id = ?", (timestamp, screenshot_id))
        connection.commit()
    finally:
        connection.close()


def names(response):
    return [hit.record["original_filename"] for hit in response.hits]


def library(tmp_path):
    """A small library with one distinctive record per field."""
    path = db_path(tmp_path)
    add(path, 1, original_filename="receipt-cafe.png", ocr_text="Espresso 3.50 total 3.50", category="Receipt",
        short_summary="A coffee shop receipt.", named_entities=["Green Cafe"], useful_search_terms=["coffee", "bill"],
        important_dates=["12 Oct 2026"])
    add(path, 2, original_filename="flight.png", ocr_text="Boarding pass gate 14", category="Travel",
        short_summary="A flight boarding pass.", named_entities=["Air Nova"], useful_search_terms=["flight", "airport"])
    add(path, 3, original_filename="notes.png", ocr_text="Buy milk and eggs", category="Notes",
        short_summary="A shopping list.", useful_search_terms=["groceries"])
    return path


# ----- which fields are searched -----
def test_matches_ocr_text(tmp_path):
    assert names(search.search_screenshots("espresso", db_path=library(tmp_path))) == ["receipt-cafe.png"]


def test_matches_summary(tmp_path):
    path = library(tmp_path)
    assert names(search.search_screenshots("boarding pass", db_path=path)) == ["flight.png"]
    assert names(search.search_screenshots("shopping list", db_path=path)) == ["notes.png"]


def test_matches_category(tmp_path):
    assert names(search.search_screenshots("travel", db_path=library(tmp_path))) == ["flight.png"]


def test_matches_keywords_entities_filename_and_dates(tmp_path):
    path = library(tmp_path)
    assert names(search.search_screenshots("groceries", db_path=path)) == ["notes.png"]      # search terms
    assert names(search.search_screenshots("air nova", db_path=path)) == ["flight.png"]      # entities
    assert names(search.search_screenshots("receipt-cafe", db_path=path)) == ["receipt-cafe.png"]  # filename
    assert names(search.search_screenshots("12 Oct 2026", db_path=path)) == ["receipt-cafe.png"]   # dates


def test_search_is_case_insensitive(tmp_path):
    path = library(tmp_path)
    assert names(search.search_screenshots("ESPRESSO", db_path=path)) == ["receipt-cafe.png"]
    assert names(search.search_screenshots("green CAFE", db_path=path)) == ["receipt-cafe.png"]


def test_all_words_must_match_but_in_any_field(tmp_path):
    path = library(tmp_path)
    assert names(search.search_screenshots("coffee espresso", db_path=path)) == ["receipt-cafe.png"]  # search term + OCR
    assert search.search_screenshots("coffee boarding", db_path=path).total == 0                      # different records


def test_quoted_phrase_must_match_together(tmp_path):
    path = library(tmp_path)
    assert names(search.search_screenshots('"buy milk"', db_path=path)) == ["notes.png"]
    assert search.search_screenshots('"milk buy"', db_path=path).total == 0


# ----- empty and no-match queries -----
def test_empty_query_lists_everything_newest_first(tmp_path):
    path = library(tmp_path)
    for query in ("", "   ", None, '""'):
        response = search.search_screenshots(query, db_path=path)
        assert response.total == 3 and response.terms == []
        assert names(response) == ["notes.png", "flight.png", "receipt-cafe.png"]
        assert all(hit.snippet == "" for hit in response.hits)


def test_empty_library_and_no_matches(tmp_path):
    path = db_path(tmp_path)
    empty = search.search_screenshots("anything", db_path=path)
    assert empty.total == 0 and empty.hits == []
    assert search.search_screenshots("zebra", db_path=library(tmp_path)).hits == []


# ----- special characters -----
def test_percent_and_underscore_are_matched_literally(tmp_path):
    path = db_path(tmp_path)
    add(path, 1, ocr_text="Sale 50% off today")
    add(path, 2, ocr_text="Sale 5000 off today")
    add(path, 3, ocr_text="file_name.txt here")
    add(path, 4, ocr_text="fileXname.txt here")
    assert names(search.search_screenshots("50%", db_path=path)) == ["shot1.png"]
    assert names(search.search_screenshots("%", db_path=path)) == ["shot1.png"]   # not "match everything"
    assert names(search.search_screenshots("file_name", db_path=path)) == ["shot3.png"]
    assert names(search.search_screenshots("_", db_path=path)) == ["shot3.png"]


def test_hostile_and_odd_queries_are_harmless(tmp_path):
    path = library(tmp_path)
    odd = ["x'); DROP TABLE screenshots; --", "' OR '1'='1", '"unclosed', "back\\slash", "*", "(", ")", "a" * 5000,
           "emoji \U0001F600", "tab\tand\nnewline", "NULL", "\\"]
    for query in odd:
        response = search.search_screenshots(query, db_path=path)  # must not raise
        assert isinstance(response.total, int)
    assert database.get_screenshot_count(path) == 3  # nothing was dropped or changed
    assert search.search_screenshots("' OR '1'='1", db_path=path).total == 0  # not treated as SQL


def test_unicode_text_is_found(tmp_path):
    path = db_path(tmp_path)
    add(path, 1, ocr_text="Caf\u00e9 \u20b9250 total", named_entities=["Zo\u00eb"])
    assert search.search_screenshots("caf\u00e9", db_path=path).total == 1
    assert search.search_screenshots("\u20b9250", db_path=path).total == 1
    assert search.search_screenshots("zo\u00eb", db_path=path).total == 1


# ----- filters and sorting -----
def test_category_filter(tmp_path):
    path = library(tmp_path)
    assert names(search.filter_screenshots(category="Travel", db_path=path)) == ["flight.png"]
    assert names(search.search_screenshots("", category="Notes", db_path=path)) == ["notes.png"]
    assert search.search_screenshots("espresso", category="Travel", db_path=path).total == 0  # query + filter
    assert search.filter_screenshots(category="Nonexistent", db_path=path).total == 0


def test_date_range_filter_uses_import_date(tmp_path):
    path = db_path(tmp_path)
    ids = [add(path, n) for n in (1, 2, 3)]
    for screenshot_id, stamp in zip(ids, ("2026-01-05T12:00:00+00:00", "2026-02-15T12:00:00+00:00", "2026-03-25T12:00:00+00:00")):
        set_created_at(path, screenshot_id, stamp)
    feb = (date(2026, 2, 1), date(2026, 2, 28))
    assert names(search.filter_screenshots(date_range=feb, db_path=path)) == ["shot2.png"]
    assert names(search.filter_screenshots(date_range=(date(2026, 2, 1), None), db_path=path)) == ["shot3.png", "shot2.png"]
    assert names(search.filter_screenshots(date_range=(None, date(2026, 2, 28)), db_path=path)) == ["shot2.png", "shot1.png"]
    assert search.filter_screenshots(date_range=(date(2025, 1, 1), date(2025, 12, 31)), db_path=path).total == 0
    # the end date itself is included
    assert names(search.filter_screenshots(date_range=(date(2026, 2, 15), date(2026, 2, 15)), db_path=path)) == ["shot2.png"]


def test_sorting(tmp_path):
    path = db_path(tmp_path)
    first = add(path, 1, category="Travel")
    second = add(path, 2, category="Receipt")
    third = add(path, 3, category=None)
    for screenshot_id, stamp in ((first, "2026-01-01T10:00:00+00:00"), (second, "2026-02-01T10:00:00+00:00"), (third, "2026-03-01T10:00:00+00:00")):
        set_created_at(path, screenshot_id, stamp)
    assert names(search.filter_screenshots(sort="newest", db_path=path)) == ["shot3.png", "shot2.png", "shot1.png"]
    assert names(search.filter_screenshots(sort="oldest", db_path=path)) == ["shot1.png", "shot2.png", "shot3.png"]
    assert names(search.filter_screenshots(sort="category", db_path=path)) == ["shot2.png", "shot1.png", "shot3.png"]  # A-Z, no category last
    assert names(search.filter_screenshots(sort="nonsense", db_path=path)) == names(search.filter_screenshots(sort="relevance", db_path=path))


def test_relevance_ranks_important_fields_above_plain_ocr_text(tmp_path):
    path = db_path(tmp_path)
    ocr_only = add(path, 1, ocr_text="Mentions headphones once in a long text", category="Notes")
    keyword = add(path, 2, ocr_text="Something else", useful_search_terms=["headphones"], category="Shopping")
    set_created_at(path, ocr_only, "2026-06-01T10:00:00+00:00")  # the OCR-only record is newer
    set_created_at(path, keyword, "2026-05-01T10:00:00+00:00")
    response = search.search_screenshots("headphones", db_path=path)
    assert names(response) == ["shot2.png", "shot1.png"]
    assert response.hits[0].score > response.hits[1].score
    assert names(search.search_screenshots("headphones", sort="newest", db_path=path)) == ["shot1.png", "shot2.png"]


# ----- pagination and limits -----
def test_pagination(tmp_path):
    path = db_path(tmp_path)
    for number in range(1, 26):
        add(path, number, ocr_text="coffee")
    pages = [search.search_screenshots("coffee", limit=10, offset=offset, db_path=path) for offset in (0, 10, 20)]
    assert [page.total for page in pages] == [25, 25, 25]
    assert [len(page.hits) for page in pages] == [10, 10, 5]
    all_names = [name for page in pages for name in names(page)]
    assert len(set(all_names)) == 25  # no record repeated across pages
    assert search.search_screenshots("coffee", limit=10, offset=100, db_path=path).hits == []


def test_default_page_size_and_hard_limit(tmp_path):
    path = db_path(tmp_path)
    for number in range(1, 16):
        add(path, number)
    assert len(search.search_screenshots("", db_path=path).hits) == config.SEARCH_PAGE_SIZE
    rows, total = database.search_screenshot_rows(limit=10**9, db_path=path)
    assert total == 15 and len(rows) == 15 and len(rows) <= config.SEARCH_MAX_LIMIT
    rows, _ = database.search_screenshot_rows(limit=0, db_path=path)
    assert len(rows) == 1  # a silly limit is raised to 1, never "everything"


def test_one_record_is_never_returned_twice(tmp_path):
    path = db_path(tmp_path)
    add(path, 1, original_filename="coffee.png", ocr_text="coffee coffee coffee", category="Coffee",
        short_summary="coffee", named_entities=["coffee"], useful_search_terms=["coffee"], important_dates=["coffee"])
    response = search.search_screenshots("coffee", db_path=path)
    assert response.total == 1 and len(response.hits) == 1


# ----- local only -----
def test_search_works_when_image_files_are_missing(tmp_path):
    path = library(tmp_path)  # no image files exist anywhere
    response = search.search_screenshots("espresso", db_path=path)
    assert names(response) == ["receipt-cafe.png"]


def test_search_never_runs_ocr_ai_or_network(tmp_path):
    path = library(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("search must not call OCR, the AI or the network")

    with patch("app.ocr.extract_text", side_effect=forbidden), patch(
        "app.gemma.analyze_text", side_effect=forbidden
    ), patch("app.gemma.answer_question", side_effect=forbidden), patch(
        "app.gemma.requests.post", side_effect=forbidden
    ), patch("app.gemma.requests.get", side_effect=forbidden):
        assert search.search_screenshots("espresso", db_path=path).total == 1
        assert search.filter_screenshots(category="Travel", db_path=path).total == 1


def test_unreadable_library_raises_database_error_with_a_plain_message(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder")
    error = None
    try:
        search.search_screenshots("x", db_path=blocker / "ssorg.db")
    except database.DatabaseError as caught:
        error = caught
    assert error is not None and "Traceback" not in str(error)


def test_recent_screenshots(tmp_path):
    path = library(tmp_path)
    assert [r["original_filename"] for r in search.get_recent_screenshots(2, db_path=path)] == ["notes.png", "flight.png"]


# ----- snippets, highlighting, parsing -----
def test_snippet_comes_from_ocr_text_with_ellipses(tmp_path):
    long_text = "word " * 100 + "the invoice number is 4471 for you " + "more " * 100
    record = {"ocr_text": long_text, "short_summary": "", "original_filename": "a.png"}
    snippet, label = search.make_snippet(record, ["4471"], width=80)
    assert "4471" in snippet and label == "extracted text"
    assert snippet.startswith("...") and snippet.endswith("...") and len(snippet) <= 90


def test_snippet_falls_back_to_other_fields():
    record = {"ocr_text": "nothing relevant", "short_summary": "A flight boarding pass.", "original_filename": "x.png"}
    assert search.make_snippet(record, ["boarding"]) == ("A flight boarding pass.", "summary")
    assert search.make_snippet(record, ["zzz"]) == ("", "")
    assert search.make_snippet(record, []) == ("", "")


def test_hits_say_where_they_matched(tmp_path):
    response = search.search_screenshots("coffee", db_path=library(tmp_path))
    hit = response.hits[0]
    assert "search terms" in hit.matched_fields and "summary" in hit.matched_fields
    assert hit.snippet_field in ("summary", "search terms")


def test_highlight_segments():
    segments = search.highlight_segments("Total 245.50 at Green Cafe", ["green cafe", "total"])
    assert segments == [("Total", True), (" 245.50 at ", False), ("Green Cafe", True)]  # original capitalization kept
    assert "".join(text for text, _ in segments) == "Total 245.50 at Green Cafe"
    assert search.highlight_segments("abc", []) == [("abc", False)]
    assert search.highlight_segments("", ["x"]) == []
    assert search.highlight_segments("a.b", ["."]) == [("a", False), (".", True), ("b", False)]  # regex characters are literal
    assert search.highlight_segments("ab", ["a", "ab"]) == [("ab", True)]  # the longest term wins


def test_parse_query():
    assert search.parse_query("green cafe") == (["green", "cafe"], False)
    assert search.parse_query('green "total price" cafe') == (["green", "total price", "cafe"], False)
    assert search.parse_query("a A a") == (["a"], False)  # repeats removed
    assert search.parse_query("   ") == ([], False) and search.parse_query(None) == ([], False)
    many = " ".join(f"w{n}" for n in range(config.SEARCH_MAX_TERMS + 3))
    terms, cut = search.parse_query(many)
    assert len(terms) == config.SEARCH_MAX_TERMS and cut is True
    assert len(" ".join(search.parse_query("x" * 5000)[0])) <= config.SEARCH_MAX_QUERY_CHARS


def test_local_date_bounds():
    assert search.local_date_bounds(None, None) == (None, None)
    start, end = search.local_date_bounds(date(2026, 6, 15), date(2026, 6, 15))
    from datetime import datetime
    assert datetime.fromisoformat(end) - datetime.fromisoformat(start) == timedelta(days=1)
    assert start.endswith("+00:00")  # same text format as the stored timestamps