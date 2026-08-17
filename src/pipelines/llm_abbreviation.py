import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CACHE, CANONICAL_INPUT, LLM_OUTPUT
from utils.azure_client import create_client
from utils.cache import load, save
from utils.json_utils import fingerprint, read_json, write_json


PROMPT_VERSION = "canonical-only-alias-v3-multiclass"


def generate(client, deployment: str, payload: dict[str, str]) -> list[str]:
    instructions = """Generate a complete, clinically valid alias family for exactly one canonical ICD entity.

Use only the input `category` and `description_2`. This is a canonical-only task: do not rely on PubMed articles, ClinicalTrials records, any other knowledge base, ICD codes, code_3, description_3, or other entities. Do not return aliases for a related condition simply because it shares an organ system or disease family.

Every returned phrase must refer to the exact site, disease, and histology represented by the supplied input. Preserve the site: never substitute a different site, organ, histology, stage, or metastasis.

━━━ WHAT TO INCLUDE ━━━
- The canonical common disease name
- <site> Cancer, <site> Carcinoma, <site> Malignancy, Malignancy of <site>
- Established histological subtypes directly derivable from the input (e.g., "Hepatocellular Carcinoma", "Adenocarcinoma of Lung")
- Widely used acronyms that unambiguously refer to this entity (e.g., "HCC", "NSCLC", "TNBC", "CLL", "AML")
- Established anatomical synonyms for the same site (e.g., "Glossal Cancer" for tongue, "Hepatoma" for liver)
- Lay terms in clinical use (e.g., "Voice Box Cancer" for laryngeal, "Womb Cancer" for uterine)
- Directional or site-specific qualifiers when the description explicitly names a subsite (e.g., "Upper Lobe Lung Cancer")
- Combination terms when the description explicitly covers multiple named subsites

━━━ WHAT TO EXCLUDE ━━━
- Standalone modifiers without a complete entity phrase (never "malignant" alone, "pulmonary" alone)
- ICD or numeric codes of any kind
- Aliases for a DIFFERENT cancer, organ, body system, or disease family
- Duplicate values (case-insensitive)
- Overly broad terms that apply to many entities (e.g., never "Cancer" alone, never "Leukemia" alone as the only entry)

━━━ REQUIRED STYLE — STUDY THESE EXAMPLES ━━━

category="Lip Cancer", description="Malignant neoplasm of lip"
→ ["Lip Cancer", "Lip Malignancy", "Malignancy of Lip", "Lip's Cancer", "Vermilion Border Cancer", "Lip Carcinoma"]

category="Lung Cancer", description="Malignant neoplasm of upper lobe, bronchus or lung"
→ ["Lung Cancer", "Pulmonary Cancer", "Lung Carcinoma", "Non-Small Cell Lung Cancer", "NSCLC", "Small Cell Lung Cancer", "SCLC", "Adenocarcinoma of Lung", "Bronchogenic Carcinoma", "Malignant Neoplasm of Upper Lobe of Lung"]

category="Breast Cancer", description="Malignant neoplasm of central portion of female breast"
→ ["Breast Cancer", "Mammary Carcinoma", "Breast Carcinoma", "IBC", "Ductal Carcinoma", "Lobular Carcinoma", "Triple-Negative Breast Cancer", "TNBC", "HER2-Positive Breast Cancer", "HER2+ BC", "Metastatic Breast Cancer", "mBC", "ER+ BC"]

category="Lymphoma", description="Chronic lymphocytic leukemia/small lymphocytic lymphoma"
→ ["CLL", "Chronic Lymphocytic Leukemia", "B-CLL", "Small Lymphocytic Lymphoma", "SLL", "CLL/SLL", "B-Cell Chronic Lymphocytic Leukemia", "Lymphoma"]

category="Atherosclerosis", description="Atherosclerosis of native arteries of extremities with intermittent claudication"
→ ["Atherosclerosis", "Peripheral Artery Disease", "PAD", "Peripheral Vascular Disease", "PVD", "ASCVD", "Atherosclerotic Cardiovascular Disease", "claudication"]

category="Angina", description="Unstable angina"
→ ["Angina", "Unstable Angina", "Chest Pain", "Crescendo Angina", "Pre-infarction Angina", "Coronary Artery Disease", "CAD", "Angina Pectoris"]


━━━ SENTINEL RULE ━━━
Return an empty array [] only when absolutely no clinically valid alias can be derived from the input. Never return ICD codes.

Return JSON only in this exact form: {"abbreviations": ["..."]}."""
    response = client.chat.completions.create(
        model=deployment, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps(payload)}],
    )
    values = json.loads(response.choices[0].message.content or "{}").get("abbreviations", [])
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("Azure OpenAI returned invalid abbreviations JSON")
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def run_llm(
    entities: list,
    output_path: Optional[Path] = None,
    refresh_cache: bool = False,
) -> list:
    """Generate LLM-only abbreviations for *entities* and return the output list.

    Args:
        entities:       List of canonical entity dicts (must have 'category' and
                        'description_2' keys).
        output_path:    Where to write the output JSON. Defaults to LLM_OUTPUT.
        refresh_cache:  If True, ignore existing cache entries.

    Returns:
        List of output dicts written to output_path.
    """
    output_path = output_path or LLM_OUTPUT
    cache_path = CACHE / "llm_abbreviations_cache.json"
    cache = {} if refresh_cache else load(cache_path)

    def cache_key(payload: dict[str, str]) -> str:
        return fingerprint({"payload": payload, "prompt_version": PROMPT_VERSION})

    missing = [
        entity for entity in entities
        if cache_key({"category": entity["category"], "description_2": entity["description_2"]}) not in cache
    ]
    print(f"  [llm] {len(entities):,} entities | {len(missing):,} to process")

    client = deployment = None
    try:
        for entity in missing:
            payload = {"category": entity["category"], "description_2": entity["description_2"]}
            key = cache_key(payload)
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

    write_json(output, output_path)
    print(f"  [llm] Wrote {len(output):,} records → {output_path.resolve()}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LLM-only abbreviations from canonical entities.")
    parser.add_argument("--input", default=str(CANONICAL_INPUT))
    parser.add_argument("--output", default=str(LLM_OUTPUT))
    parser.add_argument("--refresh-cache", action="store_true")
    args = parser.parse_args()
    entities = read_json(Path(args.input))
    run_llm(entities=entities, output_path=Path(args.output), refresh_cache=args.refresh_cache)


if __name__ == "__main__":
    main()