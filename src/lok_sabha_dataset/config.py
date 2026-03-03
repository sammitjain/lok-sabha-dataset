"""Centralized configuration for dataset builds."""

from __future__ import annotations

import os
from pathlib import Path

# Path to the lok-sabha-rag data directory (contains 17/, 18/, metadata.db, etc.)
SOURCE_DATA_DIR: Path = Path(
    os.getenv("LOKSABHA_RAG_DATA_DIR", str(Path.home() / "Downloads" / "lok-sabha-rag" / "data"))
)

# Where built datasets are written
OUTPUT_DIR: Path = Path(os.getenv("LOKSABHA_DATASET_OUTPUT_DIR", "output"))

# Sessions available per Lok Sabha number
SESSIONS: dict[int, list[int]] = {
    18: [2, 3, 4, 5, 6, 7],
    # 17: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15],  # add when data is ready
}
