# Architecture

How ssorg.dev is put together today (Stages 1–5).

## Data flow

```
Upload -> Validate -> SHA-256 -> Duplicate check -> Local image storage
       -> (record saved as "pending") -> OCR -> Local Gemma -> SQLite update -> Screenshot library
```

1. **Upload:** the user picks files in Streamlit. They are held in memory until processed.
2. **Validate:** `storage.validate_image_bytes` checks the 20 MB file-size limit, a 40-million-pixel limit, and the content format with Pillow (PNG, JPEG or WEBP). The filename and extension are not trusted for storage or type detection.
3. **SHA-256:** `storage.hash_bytes` hashes the original bytes.
4. **Duplicate check:** `database.get_screenshot_by_hash`. If the hash exists, nothing is saved or analyzed and the user is pointed to the existing record. The `file_hash` column is also `UNIQUE`, so the database refuses a duplicate even if two imports race.
5. **Local image storage:** the bytes are written to `data/screenshots/` under a generated name, never overwriting a file.
6. **Record added:** a row with status `pending` is inserted right away, so a saved file never exists without a record. If the insert fails, the new file is removed again.
7. **OCR:** `ocr.extract_text` (Tesseract).
8. **Local Gemma:** `gemma.analyze_text` sends only the OCR text to the configured Ollama host using the fixed model `gemma3:4b`.
9. **SQLite update:** `database.update_screenshot_processing` stores the OCR text, metadata and a status: `complete`, `no_text`, `ocr_failed` or `ai_failed`. The image is kept in every case.
10. **Library:** the "All Screenshots" page reads records from SQLite and shows images from `data/screenshots/`.

## Search flow (Stage 4)

```
Search box + filters -> parse words -> SQLite LIKE query (parameterized) -> ranked page of records
                     -> snippets and highlighting -> Search page
```

No OCR and no AI are involved. `search.search_screenshots` splits the query into words (quotes keep a phrase together) and calls `database.search_screenshot_rows`, which builds one parameterized query. Every word must match at least one of: filename, OCR text, summary, category, entities, search terms and dates. Wildcards `%` and `_` in the user's text are escaped. The relevance score adds field weights (category, search terms and entities count most, OCR text least). Filters and sorting use a fixed list of allowed options. One screenshot is one row, so there are no duplicate results. No schema change or full-text index was needed.

## Ask ssorg flow (Stage 4)

```
Question -> keywords (local) -> SQLite search (any keyword) -> rank and keep the best 5 -> trim excerpts
         -> [nothing found: STOP, no AI call]
         -> local Gemma (gemma3:4b) with only that evidence -> validate in Python -> answer + sources
```

1. `search.extract_keywords` drops common words and keeps the useful ones (numbers included).
2. `search.retrieve_evidence` fetches candidates with an OR search, ranks them by how many keywords matched, then by the field-weighted score, then by newest, and keeps `ASK_MAX_EVIDENCE` (5). Each record becomes an `EvidenceItem` (id, filename, category, import date, summary and an OCR excerpt around the matches). Excerpts are trimmed so the whole evidence stays under `ASK_CONTEXT_CHARS` (4000).
3. If there are no items, `ask.ask_question` returns "no evidence" without calling Ollama.
4. `gemma.answer_question` sends the question and the evidence, asks for JSON (`answer`, `evidence_ids`, `support`), and `validate_answer` enforces the rules in Python: cited ids must be retrieved ids, an answer with no valid citation is refused, `support: none` shows no answer, and numbers absent from the cited text are flagged.
5. The interface builds its links from the trusted database ids of the retrieved screenshots, never from anything the model wrote.

## Modules

- `app/main.py`: all Streamlit UI (dashboard, upload, import results, library, detail view, delete confirmation).
- `app/config.py`: settings, environment variables and the optional `.env` file, including the data, screenshot and database paths.
- `app/processor.py`: the workflow (`import_screenshot`, `import_screenshots`, `reprocess_screenshot`, `delete_screenshot`) plus the Stage 2 `process_image`. No Streamlit code.
- `app/storage.py`: hashing, image validation, generated filenames, path-traversal protection, saving and deleting files.
- `app/database.py`: the SQLite layer. One short connection per call, parameterized SQL only.
- `app/ocr.py`, `app/gemma.py`: Tesseract and Ollama, unchanged from Stage 2.
- `app/search.py`: query parsing, keyword search, snippets and highlighting, plus keyword extraction and evidence retrieval for Ask. No AI and no network.
- `app/ask.py`: runs retrieval, then the model, and turns the outcome into one `AskResult` for the interface.

Imports go one way: `main` -> `processor` / `ask` -> `search` / `storage` / `database` / `ocr` / `gemma` -> `config`. `gemma` does not import `search`; it only reads fields of the evidence objects it is given. Nothing imports `main`.

## Database

One table, `screenshots`: id, original_filename (display only), stored_filename (unique), file_hash (unique SHA-256), file_size, mime_type, created_at (UTC), ocr_text, category, short_summary, three JSON-text list columns (dates, entities, search terms), confidence, processing_status and processing_error. Indexes exist for created_at, category and status.

## Testing and evaluation (Stage 5)

The pytest suite uses temporary databases and screenshot folders, and mocks Tesseract and Ollama. It checks upload validation, import and failure paths, SQL behavior, retrieval, citations and privacy boundaries without reading the user's library. `EVALUATION.md` describes an optional manual check using fictional examples; no OCR or model accuracy has been measured. See `TESTING.md` for Windows commands.

## Planned

Possible later work: semantic search, better ranking, and exporting your library.
