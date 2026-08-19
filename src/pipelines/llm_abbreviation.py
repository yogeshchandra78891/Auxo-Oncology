import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CANONICAL_INPUT, LLM_OUTPUT
from utils.azure_client import create_client
from utils.json_utils import read_json, write_json


def generate(
    client,
    deployment: str,
    payload: dict,
    existing: list[str],
    target_extra: int,
) -> list[str]:
    existing_count = len(existing)
    existing_block = (
        "\n".join(f"  {i+1}. {a}" for i, a in enumerate(existing))
        if existing
        else "  (none yet)"
    )

    instructions = f"""You are a clinical terminology expert. Your task is to generate EXACTLY {target_extra} new, unique aliases for the ICD entity below.

━━━ ENTITY ━━━
category      : {{category}}
description_2 : {{description_2}}

━━━ ALREADY HAVE ({existing_count} aliases — DO NOT REPEAT ANY OF THESE) ━━━
{existing_block}

━━━ YOUR REQUIREMENT ━━━
• You MUST return EXACTLY {target_extra} new aliases.
• Every alias must be case-insensitively distinct from all entries in the ALREADY HAVE list above.
• Every alias must refer to the EXACT same disease, anatomical site, and histology — never a different organ, cancer family, or disease.
• The combined total (already have + your new ones) MUST reach at least 20.

━━━ WHAT TO GENERATE ━━━
Draw from ALL of the following categories until you have {target_extra} entries:
1. Common disease name variants  — "<site> Cancer", "<site> Carcinoma", "<site> Malignancy", "Malignancy of <site>"
2. Histological subtypes         — established subtypes directly derivable from the input (e.g. "Hepatocellular Carcinoma", "Adenocarcinoma of Lung", "Squamous Cell Carcinoma of Tongue")
3. Acronyms                      — widely used clinical acronyms for this exact entity (e.g. "HCC", "NSCLC", "TNBC", "CLL", "AML", "CTCL")
4. Anatomical synonyms           — established alternate site names (e.g. "Glossal Cancer" for tongue, "Hepatoma" for liver, "Renal Cell Carcinoma" for kidney)
5. Lay / patient-facing terms    — terms used in clinical practice (e.g. "Voice Box Cancer" for laryngeal, "Womb Cancer" for uterine, "Bowel Cancer" for colorectal)
6. Qualifier variants            — directional, laterality, or site-specific qualifiers when the description names a subsite (e.g. "Upper Lobe Lung Cancer", "Right Ovarian Cancer")
7. Rare but established variants — recognized histological or molecular subtypes (e.g. sarcoma subtypes, lymphoma subtypes, specific mutation-defined variants)
8. Combination terms             — when the description covers multiple named sites or overlapping conditions
9. ICD phrase variant            — a natural-language rephrasing of the description_2 text itself (e.g. "Malignant Neoplasm of Main Bronchus")

━━━ STRICT RULES ━━━
✗ Do NOT repeat anything from the ALREADY HAVE list (case-insensitive)
✗ Do NOT include ICD or numeric codes of any kind
✗ Do NOT include standalone modifiers ("malignant" alone, "pulmonary" alone)
✗ Do NOT generate aliases for a DIFFERENT disease, organ, or cancer family
✗ Do NOT include duplicates within your own output (case-insensitive)
✗ Do NOT return fewer than {target_extra} entries — this is a hard requirement

━━━ REFERENCE EXAMPLES (relevance and variety expected) ━━━

category="Liver Cancer", description="Malignant neoplasm of liver and intrahepatic bile ducts"

existing=[] → should generate around 8 highly relevant new aliases:

["Liver Cancer","Liver Carcinoma","Hepatocellular Carcinoma","HCC","Hepatoma","Liver Cell Carcinoma",
 "Intrahepatic Cholangiocarcinoma","ICC","Primary Liver Cancer","Malignant Neoplasm of Liver",
 "Hepatic Sarcoma","Liver Sarcoma","Hepatic Angiosarcoma","Angiosarcoma of Liver",
 "Hemangiosarcoma of Liver","Malignant Vascular Tumor of Liver","Endothelial Sarcoma of Liver",
 "Bile Duct Cancer","Biliary Tract Cancer","Hepatic Malignancy"]

category="Lung Cancer", description="Malignant neoplasm of main bronchus"

existing=["Lung Cancer","NSCLC"] → should generate around 8 highly relevant new aliases:

["Pulmonary Cancer","Lung Carcinoma","Non-Small Cell Lung Cancer","Small Cell Lung Cancer","SCLC",
 "Adenocarcinoma of Lung","Bronchogenic Carcinoma","Small-Cell Lung Cancer","Squamous Cell Lung Cancer",
 "Large Cell Lung Carcinoma","Malignant Neoplasm of Main Bronchus","Bronchial Carcinoma",
 "Pulmonary Carcinoma","Lung Malignancy","Malignant Neoplasm of Lung","Bronchoalveolar Carcinoma",
 "Mesothelioma","Pleural Mesothelioma"]

category="Lymphoma", description="Mycosis fungoides of lymph nodes of multiple sites"

existing=["Lymphoma","CTCL"] → should generate around 8 highly relevant new aliases:

["T-Cell Lymphoma","T cell lymphoma","Cutaneous T-Cell Lymphoma","Mycosis Fungoides",
 "C-TCL","NK Cell Lymphoma","T/NK-Cell Lymphoma","Mycosis Fungoides of Spleen",
 "Spleen Mycosis Fungoides","Peripheral T-Cell Lymphoma","PTCL","Anaplastic Large Cell Lymphoma",
 "ALCL","Cutaneous Lymphoma","Primary Cutaneous Lymphoma","Sezary Syndrome",
 "Folliculotropic Mycosis Fungoides","Pagetoid Reticulosis"]

The examples demonstrate that the model should prioritize RELEVANCY and CLINICAL ACCURACY over generating a large number of aliases.

The target is approximately 8 high-quality, distinct aliases, but the model should NOT generate irrelevant or weak aliases merely to reach the target.

━━━ OUTPUT FORMAT ━━━
Return JSON only — no explanation, no markdown:
{{"abbreviations": ["alias1","alias2",...]}}
The array must contain EXACTLY {target_extra} unique new aliases."""

    response = client.chat.completions.create(
        model=deployment,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": instructions.replace("{category}", payload.get("category","")).replace("{description_2}", payload.get("description_2",""))},
            {"role": "user", "content": f"Generate exactly {target_extra} new aliases for: category=\"{payload.get('category','')}\" | description_2=\"{payload.get('description_2','')}\""},
        ],
    )
    values = json.loads(response.choices[0].message.content or "{}").get("abbreviations", [])
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("Azure OpenAI returned invalid abbreviations JSON")

    existing_lower = {a.casefold() for a in existing}
    deduped = list(dict.fromkeys(
        item.strip() for item in values
        if item.strip() and item.strip().casefold() not in existing_lower
    ))
    return deduped


def run_llm(
    entities: list,
    output_path: Optional[Path] = None,
    article_category_records: Optional[list] = None,
    article_description_records: Optional[list] = None,
    min_total: int = 10,
) -> list:
    output_path = output_path or LLM_OUTPUT

    cat_by_id = {
        r["category_description2"]: r.get("abbreviations", {})
        for r in (article_category_records or [])
        if r.get("category_description2")
    }
    desc_by_id = {
        r["category_description2"]: r.get("abbreviations", {})
        for r in (article_description_records or [])
        if r.get("category_description2")
    }

    print(f"  [llm] {len(entities):,} entities to process (always generating {min_total})")

    results = {}
    client = deployment = None
    try:
        for entity in entities:
            eid        = entity["category_description2"]
            category   = str(entity.get("category", "")).strip()
            description = str(entity.get("description_2", "")).strip()

            existing: list[str] = []
            seen_lower: set[str] = set()

            c_data = cat_by_id.get(eid, {})
            d_data = desc_by_id.get(eid, {})
            
            c_list = c_data.get("pubmed", []) + c_data.get("clinical_trials", []) if isinstance(c_data, dict) else (c_data if isinstance(c_data, list) else [])
            d_list = d_data.get("pubmed", []) + d_data.get("clinical_trials", []) if isinstance(d_data, dict) else (d_data if isinstance(d_data, list) else [])

            for abbrev in c_list + d_list:
                a = abbrev.strip()
                if a and a.casefold() != "404" and a.casefold() not in seen_lower:
                    existing.append(a)
                    seen_lower.add(a.casefold())

            # Always generate min_total regardless of existing articles
            target_extra = min_total

            payload = {"category": category, "description_2": description}

            if client is None:
                client, deployment = create_client()

            for attempt in range(3):
                try:
                    new_abbrevs = generate(client, deployment, payload, existing, target_extra)
                    results[eid] = new_abbrevs
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2 ** attempt)

            combined_lower = set()
            combined_list = []
            for a in existing + results.get(eid, []):
                key = a.casefold()
                if key not in combined_lower:
                    combined_lower.add(key)
                    combined_list.append(a)

            still_needed = min_total - len(results.get(eid, []))
            if still_needed > 0:
                print(f"  [llm] {eid!r}: {len(results.get(eid, []))} / {min_total} — top-up {still_needed} more")
                for attempt in range(3):
                    try:
                        topup = generate(client, deployment, payload, combined_list, still_needed)
                        results[eid] = results.get(eid, []) + topup
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
        eid = entity["category_description2"]
        output.append({
            **entity,
            "payload_llm": {
                "category": str(entity["category"]).strip(),
                "description_2": str(entity["description_2"]).strip(),
            },
            "abbreviations": results.get(eid, []),
        })

    write_json(output, output_path)
    print(f"  [llm] Wrote {len(output):,} records → {output_path.resolve()}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LLM-only abbreviations from canonical entities.")
    parser.add_argument("--input", default=str(CANONICAL_INPUT))
    parser.add_argument("--output", default=str(LLM_OUTPUT))
    args = parser.parse_args()
    entities = read_json(Path(args.input))
    run_llm(entities=entities, output_path=Path(args.output))


if __name__ == "__main__":
    main()