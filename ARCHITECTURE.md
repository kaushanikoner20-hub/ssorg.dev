# Architecture

How ssorg.dev is put together today (Stage 3).

## Data flow

```
Upload -> Validate -> SHA-256 -> Duplicate check -> Local image storage
       -> (record saved as "pending") -> OCR -> Local Gemma -> SQLite update -> Screenshot library
```

1. **Upload:** the user picks files in Streamlit. They are held in memory until processed.
2. **Validate:** `storage.validate_image_bytes` checks size and looks inside the bytes with Pillow (PNG, JPEG or WEBP). The filename and extension are not trusted.
3. **SHA-256:** `storage.hash_bytes` hashes the original bytes.
4. **Duplicate check:** `database.get_screenshot_by_hash`. If the hash exists, nothing is saved or analyzed and the user is pointed to the existing record. The `file_hash` column is also `UNIQUE`, so the database refuses a duplicate even if two imports race.
5. **Local image storage:** the bytes are written to `data/screenshots/` under a generated name, never overwriting a file.
6. **Record added:** a row with status `pending` is inserted right away, so a saved file never exists without a record. If the insert fails, the new file is removed again.
7. **OCR:** `ocr.extract_text` (Tesseract).
8. **Local Gemma:** `gemma.analyze_text` sends only the OCR text to local Ollama (`gemma3:4b`).
9. **SQLite update:** `database.update_screenshot_processing` stores the OCR text, metadata and a status: `complete`, `no_text`, `ocr_failed` or `ai_failed`. The image is kept in every case.
10. **Library:** the "All Screenshots" page reads records from SQLite and shows images from `data/screenshots/`.

## Modules

- `app/main.py`: all Streamlit UI (dashboard, upload, import results, library, detail view, delete confirmation).
- `app/config.py`: settings, environment variables and the optional `.env` file, including the data, screenshot and database paths.
- `app/processor.py`: the workflow (`import_screenshot`, `import_screenshots`, `reprocess_screenshot`, `delete_screenshot`) plus the Stage 2 `process_image`. No Streamlit code.
- `app/storage.py`: hashing, image validation, generated filenames, path-traversal protection, saving and deleting files.
- `app/database.py`: the SQLite layer. One short connection per call, parameterized SQL only.
- `app/ocr.py`, `app/gemma.py`: Tesseract and Ollama, unchanged from Stage 2.
- `app/search.py`: placeholder for a later stage.

Imports go one way: `main` -> `processor` -> `storage` / `database` / `ocr` / `gemma` -> `config`. Nothing imports `main`.

## Database

One table, `screenshots`: id, original_filename (display only), stored_filename (unique), file_hash (unique SHA-256), file_size, mime_type, created_at (UTC), ocr_text, category, short_summary, three JSON-text list columns (dates, entities, search terms), confidence, processing_status and processing_error. Indexes exist for created_at, category and status.

## Planned

Keyword search over the stored text and metadata, then Ask ssorg.