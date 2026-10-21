# Architecture

> Starter document. It will describe how ssorg.dev is put together as features are added.

## Current (Stage 1)

- `app/main.py`: all Streamlit UI.
- `app/config.py`: settings and colors.
- Other files in `app/` are TODO placeholders with no code.

## Planned flow

Import -> Extract (`ocr.py`) -> Organize (`gemma.py`) -> Store (`database.py`) -> Search (`search.py`), connected by `processor.py`.

This document will later include a diagram, module responsibilities and the database schema.