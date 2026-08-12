from pathlib import Path
from typing import Any
from utils.json_utils import read_json, write_json


def load(path: Path) -> dict[str, Any]:
    records = read_json(path)
    if not records:
        return {}
    if len(records) != 1 or not isinstance(records[0], dict):
        raise ValueError(f"Invalid cache format in {path}")
    return records[0]


def save(cache: dict[str, Any], path: Path) -> None:
    write_json([cache], path)
