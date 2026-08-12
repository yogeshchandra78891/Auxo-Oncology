import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CACHE, CANONICAL_INPUT, LLM_OUTPUT
from utils.azure_client import create_client
from utils.cache import load, save
from utils.json_utils import fingerprint, read_json, write_json


def generate(client, deployment: str, payload: dict[str, str]) -> list[str]:
    instructions = """Generate concise, clinically valid abbreviations, synonyms, and common alternate names.
Use only category and description_2 from the input payload. Do not use external context or invent terms.
Return JSON only: {\"abbreviations\": [\"...\"]}. Return a unique array of strings, or [] if none apply."""
    response = client.chat.completions.create(
        model=deployment, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps(payload)}],
    )
    values = json.loads(response.choices[0].message.content or "{}").get("abbreviations", [])
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("Azure OpenAI returned invalid abbreviations JSON")
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LLM-only abbreviations from canonical entities.")
    parser.add_argument("--input", default=str(CANONICAL_INPUT))
    parser.add_argument("--output", default=str(LLM_OUTPUT))
    parser.add_argument("--refresh-cache", action="store_true")
    args = parser.parse_args()
    entities = read_json(Path(args.input))
    cache_path = CACHE / "llm_abbreviations_cache.json"
    cache = {} if args.refresh_cache else load(cache_path)
    missing = [entity for entity in entities if fingerprint({"category": entity["category"], "description_2": entity["description_2"]}) not in cache]
    print(f"{len(entities):,} entities; {len(missing):,} LLM payloads to process.")
    client = deployment = None
    try:
        for entity in missing:
            payload = {"category": entity["category"], "description_2": entity["description_2"]}
            key = fingerprint(payload)
            if client is None:
                client, deployment = create_client()
            for attempt in range(3):
                try:
                    cache[key] = {"abbreviations": generate(client, deployment, payload)}
                    save(cache, cache_path)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)
    finally:
        if client is not None:
            client.close()
    output = []
    for entity in entities:
        payload = {"category": entity["category"], "description_2": entity["description_2"]}
        output.append({**entity, "payload_llm": payload, "abbreviations": cache[fingerprint(payload)]["abbreviations"]})
    write_json(output, Path(args.output))
    print(f"Wrote {len(output):,} records to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
