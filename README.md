# ssorg.dev

**Your screenshots, finally searchable.**

ssorg.dev is a local-first AI screenshot organizer. It reads the text in your screenshots with Tesseract OCR and categorizes and summarizes them with a Gemma model running on your own computer through Ollama.

## The problem

Screenshots pile up: receipts, error messages, chats, tickets, recipes. They all have filenames like `Screenshot 2026-10-20 143012.png`, so finding one later means scrolling through hundreds of thumbnails.

## Current status: Stage 2 (OCR and local Gemma analysis)

**Works now:**
- Upload multiple PNG, JPG, JPEG and WEBP screenshots, with previews, validation and removal from the selection.
- **Process screenshots**: Tesseract extracts the text of each image, then Gemma 3 4B (`gemma3:4b`) running in your local Ollama returns a category, a short summary, important dates, named entities, search terms and a confidence label.
- Each screenshot gets its own expandable result. If one image fails, the others still run. If Ollama is unavailable, the OCR text is still shown.
- A "Check OCR and AI setup" button that tests Tesseract and Ollama.

**Not implemented yet:** saving screenshots or results (no database, everything is lost when you close the page), duplicate detection, keyword search and Ask ssorg. These are planned for later stages.

## Privacy in short

Images are processed in memory and are not saved to disk. OCR runs on your computer. The extracted **text** (not the image) is sent to the Ollama service at the address in your settings, which is your own computer by default. No cloud AI service is used. See [PRIVACY.md](PRIVACY.md).

## Tech stack

Python 3.10+, Streamlit, Pillow, pytesseract (Tesseract OCR), requests, Ollama with `gemma3:4b`, pytest.

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

Everything has a default and no `.env` file is required. See [.env.example](.env.example) for the supported variables: `TESSERACT_CMD`, `TESSERACT_LANG`, `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`, `OCR_TIMEOUT_SECONDS`.

## Current limitations

- Nothing is saved. Results disappear when the page is closed or refreshed.
- OCR quality depends on the image. Small, blurry or handwritten text may not be read.
- The AI can be wrong. Dates and names are only kept if they appear in the OCR text, but categories and summaries are the model's best guess. Accuracy has not been formally measured yet (see [EVALUATION.md](EVALUATION.md)).
- Analysis uses at most the first 6000 characters of a screenshot's text.
- The first analysis after starting Ollama can take a while because the model has to load.
- Whether the whole app works fully offline has not been verified yet.

## Project documents

[ARCHITECTURE](ARCHITECTURE.md) | [AI_DESIGN](AI_DESIGN.md) | [PRIVACY](PRIVACY.md) | [TESTING](TESTING.md) | [EVALUATION](EVALUATION.md) | [DEVELOPMENT](DEVELOPMENT.md) | [CONTRIBUTING](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).