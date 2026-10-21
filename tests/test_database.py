"""Tests for app/database.py. Every test uses a temporary database file."""

import sqlite3

from app import config, database


def make_db_path(tmp_path):
    return tmp_path / "library" / "ssorg.db"  # the "library" folder does not exist yet


def add_sample(db_path, number=1, **overrides):
    values = dict(
        original_filename=f"shot{number}.png",
        stored_filename=f"{number:032x}.png",
        file_hash=f"hash{number}",
        file_size=1234,
        mime_type="image/png",
        db_path=db_path,
    )
    values.update(overrides)
    return database.add_screenshot(**values)


def test_tests_never_use_the_real_library():
    real_database = config.PROJECT_ROOT / "data" / "ssorg.db"
    assert config.DATABASE_PATH != real_database
    assert "screenshot_sloth" not in str(config.DATABASE_PATH)


def test_database_filename_is_ssorg_db_and_not_in_app_folder():
    assert config.DATABASE_FILENAME == "ssorg.db"
    assert (config.PROJECT_ROOT / "app") not in config.DATABASE_PATH.parents


def test_initialize_creates_folder_file_table_and_indexes(tmp_path):
    db_path = make_db_path(tmp_path)
    assert not db_path.exists()
    database.initialize_database(db_path)
    assert db_path.is_file()
    connection = sqlite3.connect(db_path)
    try:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        indexes = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")]
        columns = [row[1] for row in connection.execute("PRAGMA table_info(screenshots)")]
    finally:
        connection.close()
    assert "screenshots" in tables
    assert "idx_screenshots_created_at" in indexes and "idx_screenshots_status" in indexes
    for name in ("id", "original_filename", "stored_filename", "file_hash", "file_size", "mime_type",
                 "created_at", "ocr_text", "category", "short_summary", "important_dates_json",
                 "named_entities_json", "useful_search_terms_json", "confidence",
                 "processing_status", "processing_error"):
        assert name in columns


def test_initialize_twice_is_harmless(tmp_path):
    db_path = make_db_path(tmp_path)
    database.initialize_database(db_path)
    add_sample(db_path)
    database.initialize_database(db_path)
    assert database.get_screenshot_count(db_path) == 1


def test_default_path_comes_from_config(tmp_path):
    database.initialize_database()  # no path given: uses the (temporary) config path
    assert config.DATABASE_PATH.is_file()


def test_add_and_get_by_id(tmp_path):
    db_path = make_db_path(tmp_path)
    new_id = add_sample(db_path, ocr_text="hello", category="Notes", confidence="high")
    record = database.get_screenshot_by_id(new_id, db_path)
    assert record["id"] == new_id
    assert record["original_filename"] == "shot1.png"
    assert record["ocr_text"] == "hello"
    assert record["category"] == "Notes"
    assert record["processing_status"] == database.STATUS_PENDING
    assert record["created_at"]  # an import timestamp was stored
    assert record["important_dates"] == []


def test_get_missing_id_returns_none(tmp_path):
    assert database.get_screenshot_by_id(999, make_db_path(tmp_path)) is None


def test_get_by_hash(tmp_path):
    db_path = make_db_path(tmp_path)
    add_sample(db_path, 1)
    add_sample(db_path, 2)
    assert database.get_screenshot_by_hash("hash2", db_path)["original_filename"] == "shot2.png"
    assert database.get_screenshot_by_hash("nope", db_path) is None


def test_same_hash_cannot_be_added_twice(tmp_path):
    db_path = make_db_path(tmp_path)
    add_sample(db_path, 1)
    raised = False
    try:
        add_sample(db_path, 2, file_hash="hash1")  # different name, same hash
    except database.DuplicateScreenshotError:
        raised = True
    assert raised
    assert database.get_screenshot_count(db_path) == 1


def test_duplicate_stored_filename_is_a_database_error_not_a_duplicate(tmp_path):
    db_path = make_db_path(tmp_path)
    add_sample(db_path, 1)
    error = None
    try:
        add_sample(db_path, 2, stored_filename=f"{1:032x}.png")
    except database.DatabaseError as caught:
        error = caught
    assert error is not None
    assert not isinstance(error, database.DuplicateScreenshotError)


def test_update_processing_results(tmp_path):
    db_path = make_db_path(tmp_path)
    new_id = add_sample(db_path)
    updated = database.update_screenshot_processing(
        new_id,
        processing_status=database.STATUS_COMPLETE,
        ocr_text="Total 45",
        category="Receipt",
        short_summary="A receipt.",
        important_dates=["12 Oct 2026"],
        named_entities=["Green Cafe"],
        useful_search_terms=["receipt", "cafe"],
        confidence="high",
        db_path=db_path,
    )
    assert updated is True
    record = database.get_screenshot_by_id(new_id, db_path)
    assert record["processing_status"] == database.STATUS_COMPLETE
    assert record["category"] == "Receipt"
    assert record["important_dates"] == ["12 Oct 2026"]
    assert record["named_entities"] == ["Green Cafe"]
    assert record["useful_search_terms"] == ["receipt", "cafe"]
    assert record["processing_error"] is None


def test_update_missing_id_returns_false(tmp_path):
    db_path = make_db_path(tmp_path)
    database.initialize_database(db_path)
    assert database.update_screenshot_processing(5, processing_status=database.STATUS_COMPLETE, db_path=db_path) is False


def test_invalid_status_is_rejected(tmp_path):
    db_path = make_db_path(tmp_path)
    new_id = add_sample(db_path)
    raised = False
    try:
        database.update_screenshot_processing(new_id, processing_status="banana", db_path=db_path)
    except database.DatabaseError:
        raised = True
    assert raised
    assert database.get_screenshot_by_id(new_id, db_path)["processing_status"] == database.STATUS_PENDING


def test_delete_record(tmp_path):
    db_path = make_db_path(tmp_path)
    keep = add_sample(db_path, 1)
    remove = add_sample(db_path, 2)
    assert database.delete_screenshot_record(remove, db_path) is True
    assert database.get_screenshot_by_id(remove, db_path) is None
    assert database.get_screenshot_by_id(keep, db_path) is not None
    assert database.delete_screenshot_record(remove, db_path) is False  # already gone


def test_count_and_ordering_newest_first(tmp_path):
    db_path = make_db_path(tmp_path)
    assert database.get_screenshot_count(db_path) == 0
    first, second, third = (add_sample(db_path, n) for n in (1, 2, 3))
    assert database.get_screenshot_count(db_path) == 3
    ids = [record["id"] for record in database.get_all_screenshots(db_path=db_path)]
    assert ids == [third, second, first]
    assert [r["id"] for r in database.get_all_screenshots(limit=2, db_path=db_path)] == [third, second]
    assert [r["id"] for r in database.get_all_screenshots(limit=2, offset=2, db_path=db_path)] == [first]


def test_list_fields_round_trip_including_unicode_and_quotes(tmp_path):
    db_path = make_db_path(tmp_path)
    tricky = ['He said "hi"', "café ₹250", "line, with, commas", "it's"]
    new_id = add_sample(db_path, important_dates=tricky, named_entities=["Zoë"], useful_search_terms=[])
    record = database.get_screenshot_by_id(new_id, db_path)
    assert record["important_dates"] == tricky
    assert record["named_entities"] == ["Zoë"]
    assert record["useful_search_terms"] == []


def test_list_fields_are_stored_as_json_text(tmp_path):
    db_path = make_db_path(tmp_path)
    add_sample(db_path, named_entities=["A", "B"])
    connection = sqlite3.connect(db_path)
    try:
        raw = connection.execute("SELECT named_entities_json FROM screenshots").fetchone()[0]
    finally:
        connection.close()
    assert raw == '["A", "B"]'


def test_damaged_json_in_database_reads_as_empty_list(tmp_path):
    db_path = make_db_path(tmp_path)
    new_id = add_sample(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("UPDATE screenshots SET important_dates_json = ?, named_entities_json = ?, "
                           "useful_search_terms_json = ?", ("{not json", '{"a": 1}', '[1, 2, "ok"]'))
        connection.commit()
    finally:
        connection.close()
    record = database.get_screenshot_by_id(new_id, db_path)
    assert record["important_dates"] == []
    assert record["named_entities"] == []
    assert record["useful_search_terms"] == ["ok"]  # non-text items are ignored


def test_sql_in_user_text_is_stored_as_plain_text(tmp_path):
    db_path = make_db_path(tmp_path)
    nasty = "x'); DROP TABLE screenshots; --"
    new_id = add_sample(db_path, original_filename=nasty, ocr_text=nasty)
    record = database.get_screenshot_by_id(new_id, db_path)
    assert record["original_filename"] == nasty
    assert database.get_screenshot_count(db_path) == 1  # the table still exists


def test_failed_insert_is_rolled_back(tmp_path):
    db_path = make_db_path(tmp_path)
    add_sample(db_path, 1)
    try:
        add_sample(db_path, 2, file_hash="hash1")
    except database.DatabaseError:
        pass
    assert database.get_screenshot_count(db_path) == 1


def test_category_counts_and_recent_count(tmp_path):
    db_path = make_db_path(tmp_path)
    for number, category in ((1, "Receipt"), (2, "Receipt"), (3, "Notes"), (4, None)):
        add_sample(db_path, number, category=category)
    assert database.get_category_counts(db_path) == {"Receipt": 2, "Notes": 1}
    assert database.get_recent_screenshot_count(7, db_path) == 4


def test_unusable_database_path_gives_database_error(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a folder")
    error = None
    try:
        database.initialize_database(blocker / "ssorg.db")
    except database.DatabaseError as caught:
        error = caught
    assert error is not None
    assert "Traceback" not in str(error)  # a plain message, not a stack trace