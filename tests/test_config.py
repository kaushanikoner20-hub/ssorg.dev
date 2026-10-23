"""Configuration checks run in a fresh process so environment parsing is realistic."""

import json
import os
import subprocess
import sys

from app import config


def test_model_is_fixed_and_local_url_timeout_and_paths_are_configurable():
    env = os.environ.copy()
    env.update(
        {
            "OLLAMA_HOST": "127.0.0.1:11434/",
            "OLLAMA_TIMEOUT": "45",
            "OLLAMA_MODEL": "some-other-model:latest",
            "TESSERACT_CMD": "",
            "SSORG_DATA_DIR": "test-data",
        }
    )
    script = (
        "import json; from app import config; "
        "print(json.dumps({'model': config.OLLAMA_MODEL, 'default_model': config.DEFAULT_OLLAMA_MODEL, "
        "'url': config.OLLAMA_BASE_URL, 'timeout': config.OLLAMA_TIMEOUT_SECONDS, "
        "'tesseract': config.TESSERACT_CMD, 'data_dir': str(config.DATA_DIR)}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=config.PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["model"] == result["default_model"] == "gemma3:4b"
    assert result["url"] == "http://127.0.0.1:11434"
    assert result["timeout"] == 45
    assert result["tesseract"] == ""
    assert result["data_dir"] == str(config.PROJECT_ROOT / "test-data")


def test_invalid_timeout_uses_safe_default_instead_of_crashing():
    env = os.environ.copy()
    env["OLLAMA_TIMEOUT"] = "not-a-number"
    completed = subprocess.run(
        [sys.executable, "-c", "from app import config; print(config.OLLAMA_TIMEOUT_SECONDS)"],
        cwd=config.PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == "120"


def test_repository_ignores_private_runtime_and_sqlite_files():
    gitignore = (config.PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".venv/", "__pycache__/", ".env", "data/screenshots/*", "*.db", "*.db-wal", "*.db-shm"):
        assert pattern in gitignore
