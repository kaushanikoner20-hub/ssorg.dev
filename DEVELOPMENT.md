# Development

## Stages

1. **Stage 1 (done):** project foundation, UI, upload preview.
2. **Stage 2 (done):** Tesseract OCR and local Gemma 3 4B analysis through Ollama.
3. **Stage 3 (done):** local image storage, SQLite library, exact duplicate detection, library page, delete.
4. **Stage 4 (done):** keyword search with filters and sorting, and Ask ssorg (retrieval first, then a grounded answer).
5. Later: ideas such as semantic search or exporting the library.

## Local workflow

Follow the Windows setup in [README.md](README.md). Run `python -m pytest` before committing. Keep code simple and beginner-friendly, and keep settings in `app/config.py`.