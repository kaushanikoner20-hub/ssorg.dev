# ssorg.dev

**Your screenshots, finally searchable.**

ssorg.dev is a local-first AI screenshot organizer. The goal is to read the text in your screenshots, sort them into categories, and let you search or ask questions about them, all on your own computer.

## The problem

Screenshots pile up: receipts, error messages, chats, tickets, recipes. They all have filenames like `Screenshot 2026-10-20 143012.png`, so finding one later means scrolling through hundreds of thumbnails.

## Planned features

- Import multiple screenshots.
- Extract text with Tesseract OCR.
- Categorize and summarize with Gemma running locally through Ollama.
- Store screenshot information in SQLite (`ssorg.db`).
- Search by keyword.
- **Ask ssorg**: ask questions about your screenshot collection.

## Current status: Stage 1 (UI and upload preview only)

**Works now:**
- Dashboard UI with sidebar navigation.
- Uploading multiple PNG, JPG, JPEG and WEBP files, with previews, file validation and removal from the current selection.

**Not implemented yet:** OCR, Gemma/Ollama, database storage, search and Ask ssorg. The "Process screenshots" button is intentionally disabled. Uploaded images are held in memory for the current session only and are never saved to disk.

## Tech stack

- Python 3
- Streamlit
- Pillow

## Setup on Windows 11 (VS Code terminal, PowerShell)

1. Install [Python 3.10 or newer](https://www.python.org/downloads/) and tick "Add python.exe to PATH".
2. Open the project folder in VS Code, then open a terminal (``Ctrl+` ``).
3. Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again.

4. Install dependencies:

```powershell
pip install -r requirements.txt
```

5. Run the app from the project root:

```powershell
python -m streamlit run app/main.py
```

Your browser opens at http://localhost:8501.

## Project documents

[ARCHITECTURE](ARCHITECTURE.md) | [AI_DESIGN](AI_DESIGN.md) | [PRIVACY](PRIVACY.md) | [TESTING](TESTING.md) | [EVALUATION](EVALUATION.md) | [DEVELOPMENT](DEVELOPMENT.md) | [CONTRIBUTING](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).