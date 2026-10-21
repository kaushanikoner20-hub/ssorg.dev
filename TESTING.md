# Testing

## Run the automated tests

From the project root, with the virtual environment active:

```powershell
python -m pytest
```

## What the tests cover

- `tests/test_ocr.py`: successful extraction, empty or symbol-only text, invalid images, unsupported formats, missing Tesseract, Tesseract errors and timeouts, image mode conversion (the original image is not modified), and Tesseract path detection.
- `tests/test_gemma.py`: valid JSON, JSON in code fences, malformed JSON, missing fields, wrong types, invalid categories, invented dates and names being dropped, empty text (Ollama is not called), Ollama not running, timeouts, a missing model, server errors, unexpected replies, long text, and the prompt-injection safeguards in the request.
- `tests/test_workflow.py`: OCR then AI for each screenshot, skipping the AI when there is no text, keeping OCR text when the AI fails, and one failing image not stopping the rest.

All OCR and Ollama calls are mocked, so the tests need neither Tesseract nor Ollama.

## What the automated tests do not cover

- Real Tesseract accuracy and real Gemma answers. Try these by hand with a screenshot of your own (see the README).
- The Streamlit interface itself.

## Manual test with one screenshot

1. Start Ollama and the app.
2. Click "Run check" under "Check OCR and AI setup". Both lines should be green.
3. Upload one screenshot that contains text, click "Process screenshots", and open its result.