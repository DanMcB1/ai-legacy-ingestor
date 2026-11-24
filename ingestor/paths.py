"""Project paths for sample files and the local index."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SAMPLES_DIR = DATA_DIR / "samples"
INDEX_DIR = DATA_DIR / "index"
INDEX_DB = INDEX_DIR / "ingestor.sqlite"
