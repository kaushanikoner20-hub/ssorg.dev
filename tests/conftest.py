"""Shared test setup.

The autouse fixture below runs for EVERY test. It points the app's data
folder, screenshot folder and database at a temporary folder, so a test can
never touch your real library (data/ssorg.db and data/screenshots/).
"""

from unittest.mock import patch

import pytest

from app import config


@pytest.fixture(autouse=True)
def isolated_library(tmp_path):
    data_dir = tmp_path / "isolated_data"
    with patch.object(config, "DATA_DIR", data_dir), patch.object(
        config, "SCREENSHOT_DIR", data_dir / "screenshots"
    ), patch.object(config, "DATABASE_PATH", data_dir / "ssorg.db"):
        yield data_dir