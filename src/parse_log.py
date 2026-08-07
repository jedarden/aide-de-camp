"""
JSONL file loading utilities.

Provides basic file loading functionality for JSONL (JSON Lines) files,
where each line is a valid JSON object. This module handles file I/O and
basic JSON parsing, with no field extraction logic.
"""

import json
from pathlib import Path
from typing import Iterator, Dict

from logging import getLogger

logger = getLogger(__name__)


def load_jsonl(file_path: str) -> Iterator[Dict]:
    """
    Load a JSONL file and parse each line as a JSON object.

    Reads the file line by line, parsing each line as a separate JSON object.
    Empty lines are skipped. Yields individual parsed dict objects.

    Args:
        file_path: Path to the JSONL file (str).

    Yields:
        Dict objects parsed from each line in the file.

    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    with path.open('r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            try:
                obj = json.loads(line)
                yield obj
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse line {line_num} in {path}: {e}")
                continue
