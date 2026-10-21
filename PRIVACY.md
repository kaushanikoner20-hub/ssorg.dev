# Privacy

ssorg.dev is designed to be local-first. This document describes what Stage 2 actually does.

## What happens to your screenshots

- Uploaded images are held in memory by the running app. **They are not written to disk by ssorg.dev.** There is no database yet.
- OCR runs on your computer with Tesseract. The image is not sent anywhere.
- The **text extracted from the image** (not the image) is sent to the Ollama service at `OLLAMA_HOST`, which defaults to `http://localhost:11434`, your own computer, for categorization and summarization with `gemma3:4b`.
- No cloud AI service (OpenAI, Gemini, Claude or any other) is used, and there is no fallback to one.
- Screenshot text and AI output are not logged by ssorg.dev.
- Streamlit usage statistics are turned off in `.streamlit/config.toml`.

## What to keep in mind

- If you change `OLLAMA_HOST` to another machine, your OCR text is sent to that machine.
- The Streamlit server runs on your computer. Streamlit and your browser keep uploaded files in memory until the session ends or you clear the selection.
- Prompt-injection risk: screenshot text could contain instructions meant to trick the AI. The app treats the text as data and validates the output, but no method is perfect.
- Whether the whole application works fully offline has **not** been verified, and ssorg.dev does not claim it. Installing Python packages, Tesseract, Ollama and the model needs internet access.

## Later stages

Stage 3 will add saving. This document will then explain what is stored, where, and how to delete it.