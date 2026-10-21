# Privacy

> Starter document.

ssorg.dev is designed to be local-first: no paid services, no cloud AI APIs, no external databases.

## Stage 1 today

- Uploaded images are held in memory for the current session only.
- Nothing is written to disk and no database exists.
- Streamlit usage statistics are turned off in `.streamlit/config.toml`.

This document will later cover what is stored, where, how to delete it, and what leaves your machine (the goal: nothing).