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


PROMPT_VERSION = "canonical-only-oncology-alias-v2"


def generate(client, deployment: str, payload: dict[str, str]) -> list[str]:
    instructions = """Generate a complete, clinically valid alias family for exactly one canonical ICD entity.

Use only the input `category` and `description_2`. This is a canonical-only task: do not read, rely on, or refer to PubMed articles, ClinicalTrials records, any other knowledge base, ICD codes, code_3, description_3, or other entities. Do not return a related cancer simply because it is in the same organ system.

Every returned phrase must refer to the exact site and disease represented by the supplied category and description. Preserve the site: never substitute a different site, organ, histology, stage, or metastasis. For example, a digestive-system entity must never produce "Colorectal Cancer" or "Metastatic Cancer" unless those exact concepts are present in the input. A tracheal entity must never produce an alias for lung, laryngeal, thyroid, or another respiratory cancer.

The `abbreviations` array intentionally contains practical aliases, not only acronyms. Generate unique, concise variants derived from the input, where applicable:
- canonical common name;
- `<site> Cancer`;
- `<site> Carcinoma`;
- `<site> Malignancy` and `Malignancy of <site>`;
- established anatomical synonym that preserves the same site; and
- a standard acronym only when it unambiguously refers to the same input entity.

Examples of the required style:
- Input category "Lip Cancer" and description "Malignant neoplasm of lip" can yield "Lip Cancer", "Lip Malignancy", "Malignancy of Lip", "Lip's Cancer", "Vermilion Border Cancer", and "Lip Carcinoma".
- Input category "Tongue Cancer" and description "Malignant neoplasm of other and unspecified parts of tongue" can yield "Tongue Cancer", "Tongue Carcinoma", "Tongue Malignancy", and "Glossal Cancer".
- Input category "Tracheal Cancer" and description "Malignant neoplasm of trachea" can yield "Tracheal Cancer", "Tracheal Carcinoma", "Tracheal Malignancy", and "Malignancy of Trachea". It must not yield "Lung Cancer" or "NSCLC".

Do not output standalone modifiers such as "malignant" or "pulmonary", duplicate values, or ICD codes. Return an empty array when no valid entity-specific alias can be derived.
Return JSON only in this exact form: {\"abbreviations\": [\"...\"]}."""
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
    def cache_key(payload: dict[str, str]) -> str:
        return fingerprint({"payload": payload, "prompt_version": PROMPT_VERSION})

    missing = [entity for entity in entities if cache_key({"category": entity["category"], "description_2": entity["description_2"]}) not in cache]
    print(f"{len(entities):,} entities; {len(missing):,} LLM payloads to process.")
    client = deployment = None
    try:
        for entity in missing:
            payload = {"category": entity["category"], "description_2": entity["description_2"]}
            key = cache_key(payload)
            
            # --- NEW LUNG CANCER FILTER ---
            combined_text = f"{payload['category']} {payload['description_2']}".casefold()
            if "lung" not in combined_text:
                cache[key] = {"abbreviations": ["404"]}
                save(cache, cache_path)
                continue
            # ------------------------------

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
        output.append({**entity, "payload_llm": payload, "abbreviations": cache[cache_key(payload)]["abbreviations"]})
    write_json(output, Path(args.output))
    print(f"Wrote {len(output):,} records to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()