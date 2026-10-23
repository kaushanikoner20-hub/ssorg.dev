# Testing

These steps are for Windows 11 using PowerShell in the VS Code terminal. Run commands from the project root, the folder containing `requirements.txt`.

## Set up the Python environment

Create a virtual environment and activate it:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use this for the current terminal only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

Install project and test dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The requirements file includes pytest. The app also needs Tesseract installed separately for live OCR and Ollama installed separately with the exact `gemma3:4b` model for live AI use. Neither is required for automated tests.

## Run automated tests and syntax checks

```powershell
python -m pytest
python -m compileall app tests
```

`pytest` prints a failure location and assertion when a check fails. Fix the code or test setup responsible for that failure, then rerun the same command. `compileall` checks Python files for syntax errors; it does not prove that runtime behavior is correct.

Tests use pytest's `tmp_path` and an autouse fixture in `tests/conftest.py` that redirects the configured database and screenshot folder to temporary locations. Tests mock Tesseract and Ollama calls. They do not open or delete `data/ssorg.db` or files in `data/screenshots/`, and they do not call a cloud AI service.

## What the automated tests cover

- `tests/test_ocr.py`, `tests/test_workflow.py`: OCR success, empty text, bad images, unavailable Tesseract, mocked errors, and one failed image not stopping a batch.
- `tests/test_config.py`: fixed model, Ollama URL/timeout parsing, optional Tesseract configuration, and ignored private runtime files.
- `tests/test_gemma.py`: the fixed `gemma3:4b` model, local Ollama request, metadata validation, malformed responses, untrusted OCR text, timeouts, missing model and no cloud fallback.
- `tests/test_storage.py`, `tests/test_database.py`, `tests/test_import_workflow.py`: image validation, SHA-256 duplicates, temporary file storage, SQLite schema and transactions, cleanup on failed inserts, safe deletion and partial failures.
- `tests/test_search.py`: matching across fields, filters, sort order, limits, special characters, missing image files, and read-only search behavior.
- `tests/test_ask.py`: evidence retrieval and limits, no-evidence behavior, prompt-injection text, citations, ungrounded/malformed answers and Ollama errors.

The Streamlit UI and real OCR/model accuracy are not covered by automated tests.

## Optional manual checks

Use only a few non-sensitive or synthetic screenshots. These checks use your configured local Tesseract and/or local Ollama.

1. Start the app with `python -m streamlit run app/main.py`.
2. Upload a screenshot, inspect the preview, process it, and confirm that OCR text and metadata appear in **All Screenshots**.
3. Upload identical bytes with a different filename. The app should report a duplicate; a visually similar image with different bytes is not guaranteed to match.
4. Search for a word visible in the screenshot and confirm the result and highlighted snippet. Try a missing word and a category filter.
5. Ask a question whose answer is visible in the source text. Compare the answer and citation with the screenshot and extracted text. Ask about a detail absent from the library and confirm that the app reports no matching evidence.
6. To check local error handling, stop Ollama and try Ask or import a separate synthetic screenshot. The app should show a helpful message and preserve the saved image and any OCR text it already extracted.

## Safe manual deletion check

Use a disposable screenshot you are comfortable deleting. Open it in **All Screenshots**, select **Delete screenshot**, review the confirmation, and confirm. Verify only that record and its managed image were removed. Do not test deletion by editing the database or inserting crafted file paths by hand.

## Optional live setup checks

- OCR availability: run `tesseract --version` in PowerShell. The app also offers **Check OCR and AI setup**. If Tesseract is installed outside PATH, set `TESSERACT_CMD` in your ignored `.env` file.
- Ollama availability: run `ollama list` and confirm `gemma3:4b` is installed, then use the app's setup check. This is optional; automated tests mock Ollama.
- Keep `OLLAMA_HOST` on `http://localhost:11434` for the default same-computer setup. Configuring another host sends OCR text and Ask evidence to that host.
