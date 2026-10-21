# Architecture

How ssorg.dev is put together today (Stage 2).

## Modules

- `app/main.py`: all Streamlit UI (dashboard, upload, results display).
- `app/config.py`: settings, with environment variables and an optional `.env` file.
- `app/ocr.py`: Tesseract OCR, returns an `OcrResult`.
- `app/gemma.py`: local Ollama client and answer validation, returns a `GemmaResult`.
- `app/processor.py`: runs OCR then AI analysis for each screenshot. No Streamlit code, so it is easy to test.
- `app/database.py`, `app/search.py`: placeholders for later stages.

## Flow

Upload -> OCR (`ocr.py`) -> if text was found, analysis (`gemma.py`) -> results kept in Streamlit session state -> shown in the UI.

Imports go one way: `main` -> `processor` -> `ocr` / `gemma` -> `config`. Nothing imports `main`.

## Planned

Stage 3 adds SQLite storage (`ssorg.db`) and saved screenshots. Search and Ask ssorg come after that. This document will then gain a diagram and the database schema.