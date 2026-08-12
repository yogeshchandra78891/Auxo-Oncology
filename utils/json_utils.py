import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any


def read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as file:
        value = json.load(file)
    if not isinstance(value, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return value


def write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
    for attempt in range(3):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 2:
                # Some Windows sync/virus scanners briefly lock a recently written file.
                # The direct write keeps the pipeline recoverable when atomic replace is unavailable.
                with path.open("w", encoding="utf-8") as file:
                    json.dump(value, file, ensure_ascii=False, indent=2)
                temp.unlink(missing_ok=True)
                return
            time.sleep(0.25 * (attempt + 1))


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def entity_id(category: object, description_2: object) -> str:
    return f"{normalize(category)}|{normalize(description_2)}"


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
