"""Centralized configuration for the lok-sabha-dataset pipeline."""

from __future__ import annotations

import os
from pathlib import Path

# Root data directory for the pipeline (contains <lok_no>/ subdirectories).
# Override via env var or --data-dir CLI options on individual commands.
DATA_DIR: Path = Path(os.getenv("LOKSABHA_DATA_DIR", "data"))

# Where built datasets are written
OUTPUT_DIR: Path = Path(os.getenv("LOKSABHA_DATASET_OUTPUT_DIR", "output"))

# Sessions available per Lok Sabha number
SESSIONS: dict[int, list[int]] = {
    18: [2, 3, 4, 5, 6, 7],
    # 17: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15],  # add when data is ready
}
