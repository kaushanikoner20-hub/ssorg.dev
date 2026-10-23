# Evaluation

This document defines a small, repeatable manual evaluation. The examples below are fictional. Do not add receipts, invoices, screenshots, or identifying details from your own library.

## Synthetic examples

| ID | Fictional screenshot text | Expected category | Details to check |
| --- | --- | --- | --- |
| R1 | `Pine & Pebble Cafe` / `Date: 14 May 2026` / `Total: $18.40` | Receipt | Merchant, date, and total stay faithful to the text. |
| I1 | `Invoice: INV-2048` / `From: Northwind Garden Supply` / `Amount due: $312.00` / `Due: 30 May 2026` | Invoice | Invoice number, amount, and due date are copied correctly. |
| T1 | `Lakeview Rail` / `Trip: 08 June 2026` / `Departure: 09:15` / `Booking: LV-731` | Travel | Carrier, date, time, and booking reference are not invented. |
| E1 | `Biology - Cell division` / `Mitosis produces two daughter cells.` | Education | The summary retains the key fact without adding claims. |
| N1 | A blank image or one containing only unreadable marks | No readable text | The screenshot is retained and marked as having no readable text; Gemma is not called. |

For an optional real OCR/model check, create these as synthetic image files yourself, then import them through the app. This optional step uses local Tesseract and local Ollama; it is not part of automated tests. Do not save the generated images in a public repository unless you intend them to be public.

## Manual scoring checklist

Score each applicable item as **Pass**, **Needs review**, or **Not checked**. Write notes about the exact observed error; do not turn this small set into an accuracy percentage.

| Check | Pass means | Result | Notes |
| --- | --- | --- | --- |
| OCR extraction | Visible text is transcribed without meaningful omissions or substitutions. | Not checked | |
| Category | Category matches the intended document type. | Not checked | |
| Summary | Summary states only facts present in the screenshot text. | Not checked | |
| Dates and entities | Dates and names match the source; unsupported values are absent. | Not checked | |
| Exact duplicate detection | Reimporting identical bytes under another filename reports a duplicate; changed bytes are not called an exact duplicate. | Not checked | |
| Search relevance | Queries return the intended record, filters and ordering are sensible, and unrelated records do not dominate. | Not checked | |
| Ask answer accuracy | Answer matches the retrieved OCR evidence and is appropriately cautious about uncertainty. | Not checked | |
| Citation correctness | Every displayed citation points to a retrieved screenshot that supports the answer. | Not checked | |
| Missing evidence | An unmatched question gets no model-generated factual answer. | Not checked | |
| Tesseract unavailable | Import remains usable and reports an OCR failure in the record. | Not checked | |
| Ollama unavailable | Import keeps the screenshot and OCR text, or Ask shows a helpful error with sources. | Not checked | |

## Automated tests versus observations

- **Automated test results:** on 23 October 2026, `python -m pytest` completed with **186 passed** and `python -m compileall app tests` completed successfully on Windows with Python 3.12.14. Unit tests mock Tesseract and Ollama and use temporary storage; they do not measure OCR or model accuracy.
- **Manual observations:** fill the result and notes columns above only after importing the synthetic examples and comparing outputs with their source text.
- **Not measured:** no OCR accuracy, category accuracy, summary quality, search relevance, or Ask answer accuracy has been benchmarked. This document makes no performance or accuracy claim.

## Optional local-model evaluation

If you choose to use the locally installed `gemma3:4b` model, record the app version/commit, Ollama version, date, synthetic input, and observed outputs. Repeat each example if you want to understand variability. Keep this separate from the automated suite: automated tests must not require an Ollama server, download a model, or use real screenshots.
