"""
JSONL file loading utilities.

Provides basic file loading functionality for JSONL (JSON Lines) files,
where each line is a valid JSON object. This module handles file I/O and
basic JSON parsing, with no field extraction logic.
"""

import json
from pathlib import Path
from typing import List, Dict, Any

from logging import getLogger

logger = getLogger(__name__)


def load_jsonl(file_path: str | Path) -> List[Dict[str, Any]]:
    """
    Load a JSONL file and parse each line as a JSON object.

    Reads the file line by line, parsing each line as a separate JSON object.
    Empty lines are skipped. Returns an empty list if the file is empty.

    Args:
        file_path: Path to the JSONL file (str or Path object).

    Returns:
        List of dictionaries, one per line in the file. Empty list if file is empty.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        json.JSONDecodeError: If any line (excluding empty lines) contains invalid JSON.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    results: List[Dict[str, Any]] = []

    with path.open('r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            try:
                obj = json.loads(line)
                results.append(obj)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse line {line_num} in {path}: {e}")
                raise json.JSONDecodeError(
                    f"Invalid JSON on line {line_num} in {path}: {e.msg}",
                    e.doc,
                    e.pos
                )

    logger.info(f"Loaded {len(results)} JSON objects from {path}")
    return results
