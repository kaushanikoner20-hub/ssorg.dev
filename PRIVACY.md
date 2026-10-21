# Privacy

ssorg.dev is designed to be local-first. This document describes what Stage 3 actually does.

## What is stored, and where

- **Your screenshots:** saved as files in `data/screenshots/` (under random names such as `3f2a...e1.png`) inside the project folder, unless you change `SSORG_DATA_DIR` or `SSORG_SCREENSHOT_DIR`.
- **Your library database:** `data/ssorg.db` (SQLite). It contains the original filenames, the OCR text of your screenshots, categories, summaries, dates and names found in them, and import times.
- Both are stored in plain, unencrypted form on your computer. Anyone who can open your user account or your backups can read them.

## What leaves your computer

Nothing is sent to a cloud service by ssorg.dev.

- OCR runs locally with Tesseract. The image is not sent anywhere.
- The **text extracted from the image** (not the image) is sent to the Ollama service at `OLLAMA_HOST`, which defaults to `http://localhost:11434`, your own computer, for analysis with `gemma3:4b`. No cloud AI provider is used and there is no fallback to one.
- Screenshot text and AI output are not logged by ssorg.dev.
- Streamlit usage statistics are turned off in `.streamlit/config.toml`.

## Keep private data out of Git

`.gitignore` excludes `data/ssorg.db`, SQLite journal/WAL/SHM files, everything in `data/screenshots/` (except the empty `.gitkeep`), `.env` and `.venv/`. Still check `git status` before every commit, and never commit screenshots, receipts, invoices or a copy of the database. `docs/screenshots/` is tracked, so use only harmless sample images there.

## Things to keep in mind

- **Cloud-synced folders:** if the project folder is inside OneDrive, Dropbox, Google Drive or similar, your screenshots and database are uploaded by that service. Set `SSORG_DATA_DIR` to a folder outside synced folders to avoid it. Running SQLite inside a synced folder can also cause file-locking problems.
- **Backups:** a backup is a full copy of your private library. Store it safely and never put it in Git. To back up, close the app and copy the whole `data` folder.
- If you change `OLLAMA_HOST` to another machine, your OCR text is sent to that machine.
- **Deleting:** deleting a screenshot in the app removes its record and its image file from the managed folder. It does not securely erase the disk, and copies you made elsewhere (backups, synced copies) are not touched.
- **Prompt injection:** screenshot text could contain instructions meant to trick the AI. The app treats text as data and validates the output, but no method is perfect. Text and AI output are shown as plain text, so links or images inside them are not loaded.
- Whether the whole application works fully offline has **not** been verified, and ssorg.dev does not claim it. Installing Python packages, Tesseract, Ollama and the model needs internet access.