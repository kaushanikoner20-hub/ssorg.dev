# AI Design

How ssorg.dev analyzes screenshots in Stage 2. Everything here describes what the code in `app/ocr.py`, `app/gemma.py` and `app/processor.py` actually does.

## Pipeline

1. **OCR** (`app/ocr.py`): Pillow loads the image and makes a copy in RGB (transparent images get a white background). Tesseract, through `pytesseract`, extracts the text. Fewer than 3 letters or digits counts as "no readable text".
2. **AI analysis** (`app/gemma.py`): if meaningful text was found, the text is sent to Ollama's local chat API (`/api/chat`, default `http://localhost:11434`) using the model `gemma3:4b`.
3. **Validation**: the answer is parsed as JSON (never with `eval`) and checked before it is shown.

Each screenshot goes through these steps on its own. A failure in one does not stop the others.

## What the model is asked for

A JSON object with: `category` (Receipt, Invoice, Shopping, Food, Travel, Education, Work, Social Media, Notes, Other), `short_summary`, `important_dates`, `named_entities`, `useful_search_terms` and `confidence` (low, medium, high).

The request asks Ollama for structured JSON output with this shape, uses temperature 0, and a context window of 4096 tokens.

## Safety measures

- **Untrusted text**: the OCR text is placed between `<ocr_text>` tags and the system prompt says it is data, to be analyzed and never obeyed. Our own tags are removed from the text so it cannot close the block early. This lowers prompt-injection risk but cannot guarantee that a model never follows hidden instructions.
- **No invention**: the prompt forbids guessing. In addition, dates and named entities that do not appear in the OCR text are dropped after the answer comes back.
- **Strict validation**: required fields, data types, allowed categories and confidence values are checked. An invalid answer is reported as an error and is never shown as if it were valid. Capitalization of the category is forgiven.
- **Safe display**: OCR text and model output are shown as plain text in the interface, so links or images inside them are not rendered or loaded.
- **Long text**: only the first 6000 characters are analyzed, and the user is told when that happens.
- **No fallback model**: if Ollama or the model is unavailable, the app shows a message. It never switches to another model or a cloud service.

## Errors handled

Ollama not running, connection or read timeout, model not found (HTTP 404), other HTTP errors, replies that are not JSON, JSON in the wrong shape, missing fields, wrong types, and invalid categories. Users see short messages, never stack traces.

## Not done yet

No accuracy measurements exist. Later stages will add storage of results, search and Ask ssorg.