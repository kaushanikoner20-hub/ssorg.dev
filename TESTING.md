# Testing

## Run the automated tests

From the project root, with the virtual environment active:

```powershell
python -m pytest
```

## What the tests cover

- `tests/test_database.py`: creating the database, adding and reading records, updating results, deleting, JSON list fields (including damaged JSON), the unique hash rule, SQL text stored literally, rollback, counts and ordering.
- `tests/test_storage.py`: SHA-256 hashing, validating images by content, generated filenames, path-traversal protection (including symlinks where the computer allows them), no-overwrite saving, deleting only managed files.
- `tests/test_import_workflow.py`: importing a new screenshot, exact duplicates, different images, cleanup when the database insert or the file save fails, keeping the screenshot when OCR or Gemma fails, batches where one file fails, re-running analysis, and deleting (including a missing image file and a tampered filename that points outside the folder).
- `tests/test_search.py`: searching each field, case-insensitivity, several words and phrases, empty and no-match queries, special characters (`%`, `_`, quotes, backslashes and SQL-looking text), category and date filters, sorting and ranking, pagination and limits, no duplicate results, missing image files, snippets and highlighting, and that searching never calls OCR, the AI or the network.
- `tests/test_ask.py`: keyword extraction, retrieving and ranking evidence, limits on the number and size of evidence, the answer checks (valid answer, malformed answer, missing fields, citing screenshots that were not retrieved, answers without citations, unverified numbers), Ollama unavailable or timing out, prompt-injection text inside a screenshot, and that no AI call is made when there is no evidence.
- `tests/test_ocr.py`, `tests/test_gemma.py`, `tests/test_workflow.py`: the Stage 2 tests for OCR, Gemma and the analysis step.

## Safety for your real data

`tests/conftest.py` redirects the data folder, screenshot folder and database to a temporary folder for **every** test. Tests never read or write your real `data/ssorg.db` or `data/screenshots/`. OCR and Ollama are mocked, so no Tesseract, Ollama or model is needed.

## What the automated tests do not cover

- Real Tesseract accuracy and real Gemma answers.
- The Streamlit interface itself.

## Manual test: Search and Ask ssorg

You need a few imported screenshots that contain text (a receipt, a notice, a chat).

1. **Search:** open **Search**, type a word you can see in one screenshot, and check that it appears with the word highlighted. Try a word that is in none of them (you should see "No screenshots match"), then use the category filter, the sort menu and **Clear**.
2. **Search needs no AI:** quit Ollama from the system tray and search again. Search still works.
3. **Ask:** start Ollama, open **Ask ssorg**, and ask about something in one screenshot, for example "Which screenshot mentions the deadline?" using a word from the text. Check that the answer matches the **Sources** text shown below it, then click **View details** and compare with the original image.
4. **No evidence:** ask about something that is in none of your screenshots. You should see "No matching evidence was found" and no answer.
5. **Ollama down:** quit Ollama and ask again. You should see a message that the local AI could not answer, plus the matching screenshots.

## Manual test: import, restart, duplicate, delete

1. Start Ollama and the app: `python -m streamlit run app/main.py`.
2. **Import:** upload one screenshot that contains text and click **Process screenshots**. Open its result under "Import results".
3. **Restart:** stop the app with `Ctrl+C`, start it again, and open **All Screenshots**. The screenshot should still be there with its text and analysis.
4. **Duplicate:** upload the same file again, or a copy renamed in File Explorer, and click Process. You should see "This screenshot is already in your library." and the total should not change.
5. **Failure handling:** stop Ollama (quit it from the system tray), import a different screenshot, and check that it is saved with "AI analysis failed" and its OCR text. Start Ollama again and click **Re-run analysis** in its detail view.
6. **Delete:** open a screenshot, click **Delete screenshot**, then confirm. It should disappear from the library and its file should disappear from `data/screenshots/`.