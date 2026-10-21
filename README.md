# ssorg.dev

**Your screenshots, finally searchable.**

ssorg.dev is a local-first AI screenshot organizer. It reads the text in your screenshots with Tesseract OCR and categorizes and summarizes them with a Gemma model running on your own computer through Ollama.

## The problem

Screenshots pile up: receipts, error messages, chats, tickets, recipes. They all have filenames like `Screenshot 2026-10-20 143012.png`, so finding one later means scrolling through hundreds of thumbnails.

## Current status: Stage 3 (local library and duplicate detection)

**Works now:**
- Upload multiple PNG, JPG, JPEG and WEBP screenshots, with previews, validation and removal from the selection.
- **Process screenshots** saves each new screenshot on your computer, reads its text with Tesseract OCR, and analyzes the text with Gemma 3 4B (`gemma3:4b`) running in your local Ollama. You get a category, a short summary, important dates, named entities, search terms and a confidence label.
- **Persistent library:** screenshots and their results are stored locally (files in `data/screenshots/`, details in the SQLite database `data/ssorg.db`) and are still there after you restart the app.
- **All Screenshots** page: a gallery with previews, category, summary, import date and status, plus a detail view with the full OCR text and metadata.
- **Exact duplicate detection:** a SHA-256 hash of the file contents is compared with the library. Uploading the same file again, even under another name, says "This screenshot is already in your library." and creates nothing new.
- **Safe failures:** if OCR finds no text, OCR fails, or Ollama is unavailable, the screenshot is still kept with its status (and its OCR text, if it was read). Use **Re-run analysis** in the detail view to try again.
- **Delete** a screenshot, with a confirmation step. This removes its database record and its image file.
- A "Check OCR and AI setup" button that tests Tesseract and Ollama.

**Not implemented yet:** keyword search, Ask ssorg, and similarity-based duplicate detection (for example the same picture saved in a different format).

## Where your data is stored

```
ssorg/data/ssorg.db            <- the SQLite database (text, categories, summaries)
ssorg/data/screenshots/        <- your screenshot files, under random names
```

These are ignored by Git, so they are never committed. You can move them with `SSORG_DATA_DIR` (see `.env.example`).

**Backups:** close the app (press `Ctrl+C` in the terminal), then copy the whole `data` folder. The database and the images belong together, so back up both:

```powershell
Copy-Item data -Destination "$HOME\Documents\ssorg-backup" -Recurse
```

To restore, close the app and copy the folder back. Your backup contains your private screenshots: keep it somewhere safe and never put it in Git.

**Cloud-synced folders:** if this project folder is inside OneDrive, Dropbox or similar, your screenshots and database are synced to that service too. To keep the library on your computer only, set `SSORG_DATA_DIR` to a folder outside any synced folder, for example `C:\ssorg-data`.

## Privacy in short

Screenshots and the database stay on your computer. OCR runs locally. The extracted **text** (not the image) is sent to the Ollama service at the address in your settings, your own computer by default. No cloud AI service is used. See [PRIVACY.md](PRIVACY.md).

## Tech stack

Python 3.10+, Streamlit, Pillow, pytesseract (Tesseract OCR), requests, SQLite (built into Python), Ollama with `gemma3:4b`, pytest.

## Setup on Windows 11 (VS Code terminal, PowerShell)

### 1. Install Tesseract OCR (separate program)

Install Tesseract for Windows (the installer from the [UB Mannheim builds](https://github.com/UB-Mannheim/tesseract/wiki) is widely used) and keep the English language data selected. Then check it:

```powershell
tesseract --version
```

If Windows says the command is not found, either add the install folder to your PATH or point the app at it. The app also checks the usual install folders by itself. To set the path manually, copy `.env.example` to `.env` and set:

```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

### 2. Install Ollama and check the model (separate program)

Install [Ollama](https://ollama.com/download). The model must be exactly `gemma3:4b`:

```powershell
ollama list
```

You should see `gemma3:4b` in the list. To test the model in the terminal (type `/bye` to leave):

```powershell
ollama run gemma3:4b
```

ssorg.dev does not download any model for you. If `gemma3:4b` is not listed, install it yourself with `ollama pull gemma3:4b`.

### 3. Python environment and dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again.

### 4. Run the app

```powershell
python -m streamlit run app/main.py
```

Your browser opens at http://localhost:8501. Make sure Ollama is running (its icon is in the system tray).

### 5. Run the tests

```powershell
python -m pytest
```

The tests use fake OCR and fake Ollama responses. They do not need Tesseract or Ollama.

## Settings

Everything has a default and no `.env` file is required. See [.env.example](.env.example) for the supported variables: `TESSERACT_CMD`, `TESSERACT_LANG`, `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`, `OCR_TIMEOUT_SECONDS`, `SSORG_DATA_DIR`, `SSORG_SCREENSHOT_DIR`, `SSORG_DATABASE_PATH`.

## Current limitations

- Duplicate detection is exact: it compares file contents. Images that look the same but were saved with a different encoding or metadata (for example a PNG and a JPG of the same screen) are not detected as duplicates.
- OCR quality depends on the image. Small, blurry or handwritten text may not be read.
- The AI can be wrong. Dates and names are only kept if they appear in the OCR text, but categories and summaries are the model's best guess. Accuracy has not been formally measured yet (see [EVALUATION.md](EVALUATION.md)).
- Analysis uses at most the first 6000 characters of a screenshot's text.
- The first analysis after starting Ollama can take a while because the model has to load.
- No keyword search or Ask ssorg yet, and no bulk delete or database reset buttons.
- Use one running copy of the app at a time. Whether the whole app works fully offline has not been verified.

## Project documents

[ARCHITECTURE](ARCHITECTURE.md) | [AI_DESIGN](AI_DESIGN.md) | [PRIVACY](PRIVACY.md) | [TESTING](TESTING.md) | [EVALUATION](EVALUATION.md) | [DEVELOPMENT](DEVELOPMENT.md) | [CONTRIBUTING](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).