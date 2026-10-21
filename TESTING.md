# Testing

## Run the automated tests

From the project root, with the virtual environment active:

```powershell
python -m pytest
```

## What the tests cover

- `tests/test_database.py`: creating the database, adding and reading records, updating results, deleting, JSON list fields (including damaged JSON), the unique hash rule, SQL text stored literally, rollback, counts and ordering.
- `tests/test_storage.py`: SHA-256 hashing, validating images by content, generated filenames, path-traversal protection (including symlinks where the computer allows them), no-overwrite saving, deleting only managed files.
- `tests/test_import_workflow.py`: importing a new screenshot, exact duplicates, different images, cleanup when the database insert or the file save fails, keeping the screenshot when OCR or Gemma fails, batches where one file fails, re-running analysis, and deleting (including a missing image file and a tampered filename that points outside the folder).
- `tests/test_ocr.py`, `tests/test_gemma.py`, `tests/test_workflow.py`: the Stage 2 tests for OCR, Gemma and the analysis step.

## Safety for your real data

`tests/conftest.py` redirects the data folder, screenshot folder and database to a temporary folder for **every** test. Tests never read or write your real `data/ssorg.db` or `data/screenshots/`. OCR and Ollama are mocked, so no Tesseract, Ollama or model is needed.

## What the automated tests do not cover

- Real Tesseract accuracy and real Gemma answers.
- The Streamlit interface itself.

## Manual test: import, restart, duplicate, delete

1. Start Ollama and the app: `python -m streamlit run app/main.py`.
2. **Import:** upload one screenshot that contains text and click **Process screenshots**. Open its result under "Import results".
3. **Restart:** stop the app with `Ctrl+C`, start it again, and open **All Screenshots**. The screenshot should still be there with its text and analysis.
4. **Duplicate:** upload the same file again, or a copy renamed in File Explorer, and click Process. You should see "This screenshot is already in your library." and the total should not change.
5. **Failure handling:** stop Ollama (quit it from the system tray), import a different screenshot, and check that it is saved with "AI analysis failed" and its OCR text. Start Ollama again and click **Re-run analysis** in its detail view.
6. **Delete:** open a screenshot, click **Delete screenshot**, then confirm. It should disappear from the library and its file should disappear from `data/screenshots/`.