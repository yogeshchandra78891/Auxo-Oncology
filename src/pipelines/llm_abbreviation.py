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
    max_new: int,
) -> list[str]:

    existing_block = (
        "\n".join(f"  {i + 1}. {a}" for i, a in enumerate(existing))
        if existing
        else "  (none yet)"
    )

    instructions = """You are an expert medical terminology and abbreviation-generation system.

Your task is to generate NEW, entity-specific abbreviations, aliases, synonyms,
clinical terms, and disease-name variants for the given category and description_2.

IMPORTANT CONTEXT:
- Do NOT use PubMed.
- Do NOT use ClinicalTrials/CTE.
- Do NOT use any external knowledge base.
- Use ONLY:
  1. category
  2. description_2
  3. the supplied category-abbreviation evidence
  4. the supplied description-abbreviation evidence
  5. the supplied difference/evidence variants
  6. the rules and examples in this prompt.

The input comes from canonical_entities.json.

Each input record has this structure:

{
  "category_description2": "merkel cell carcinoma|merkel cell carcinoma",
  "category": "Merkel cell carcinoma",
  "description_2": "Merkel cell carcinoma"
}


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO GENERATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Generate UP TO 10 unique NEW variants.

Generate every unique, directly relevant variant supported by the supplied
evidence.

Prioritize:

1. Canonical common disease names.

2. Site-based variants:
   - <site> Cancer
   - <site> Carcinoma
   - <site> Malignancy
   - Malignancy of <site>
   - Cancer of <site>
   - Carcinoma of <site>

3. Established histological subtypes mentioned in the evidence.

4. Widely used acronyms that unambiguously refer to this entity.

5. Established anatomical synonyms.

6. Lay/clinical terms.

7. Anatomical subsite variants.

8. Directional/laterality-specific variants.

9. Combination/overlapping-site variants.

10. Histology + anatomical-site combinations.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL DUPLICATE RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The following values already exist and MUST NOT be returned:

{existing_block}

Compare case-insensitively.

If a candidate already exists in this list, exclude it.

Also remove duplicates within the LLM output itself.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPORTANT EVIDENCE RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Do NOT invent medical aliases merely to reach 10.

Prefer fewer high-quality, evidence-supported variants over fabricated variants.

If only 6 valid NEW variants exist, return 6.

Do NOT create artificial phrases such as:

"<site> Cancer Entity"
"<site> Carcinoma Entity"
"Neoplastic <site> Malignancy"

unless that terminology is actually supported by the supplied evidence.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO EXCLUDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEVER return:

- ICD codes
- Numeric codes
- code_3
- description_3
- Standalone modifiers
- "malignant" alone
- "pulmonary" alone
- "hepatic" alone
- "cancer" alone
- "carcinoma" alone
- "malignancy" alone
- Aliases for a different cancer
- Aliases for a different organ
- Unrelated diseases
- Duplicate values

The sentinel "404" must NEVER appear together with real values.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
404 RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If there are NO valid NEW entity-specific variants, return:

["404"]

If at least one valid variant exists, NEVER return "404".


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Input:
category="Tongue Cancer"
description_2="Malignant neoplasm of tongue"

Possible output:

[
  "Tongue Cancer",
  "Tongue Carcinoma",
  "Tongue Malignancy",
  "Glossal Cancer",
  "Lingual Cancer"
]


Input:
category="Liver Cancer"
description_2="Malignant neoplasm of liver and intrahepatic bile ducts"

Possible output:

[
  "Liver Cancer",
  "Liver Carcinoma",
  "Hepatocellular Carcinoma",
  "HCC",
  "Hepatoma",
  "Liver Cell Carcinoma",
  "Intrahepatic Cholangiocarcinoma",
  "ICC",
  "Malignant Neoplasm of Liver",
  "Primary Liver Cancer"
]


Input:
category="Lymphoma"
description_2="Nodular sclerosis classical Hodgkin lymphoma"

Possible output:

[
  "Nodular Sclerosis Hodgkin Lymphoma",
  "NSHL",
  "Nodular Sclerosis HL",
  "NS Hodgkin Lymphoma",
  "Classical HL - Nodular Sclerosis",
  "Hodgkin Lymphoma",
  "HL",
  "Hodgkin's Lymphoma"
]


Input:
category="Breast Cancer"
description_2="Malignant neoplasm of central portion of female breast"

Possible output:

[
  "Breast Cancer",
  "Mammary Carcinoma",
  "Breast Carcinoma",
  "Ductal Carcinoma",
  "Lobular Carcinoma",
  "Triple-Negative Breast Cancer",
  "TNBC",
  "HER2-Positive Breast Cancer",
  "Metastatic Breast Cancer",
  "mBC"
]


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return JSON ONLY.

Do not return markdown.
Do not return explanations.
Do not return comments.
Do not return ```json.

Use exactly:

{
  "category_description2": "",
  "category": "",
  "description_2": "",
  "payload_llm": {
    "category": "",
    "description_2": ""
  },
  "abbreviations": []
}

The category_description2, category, and description_2 values must be copied
from the input.

Only abbreviations are generated by the LLM.

The abbreviations array must contain ONLY unique NEW entity-specific variants.
"""

    response = client.chat.completions.create(
        model=deployment,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": instructions,
            },
            {
                "role": "user",
                "content": f"""
Generate UP TO {max_new} NEW variants for:

category_description2 = "{payload.get("category_description2", "")}"
category = "{payload.get("category", "")}"
description_2 = "{payload.get("description_2", "")}"

Existing category/description variants:

{existing_block}

Remember:
- Do not return anything already in the existing list.
- Do not fabricate variants.
- Return only valid NEW entity-specific variants.
""",
            },
        ],
    )

    values = json.loads(
        response.choices[0].message.content or "{}"
    ).get("abbreviations", [])

    if not isinstance(values, list) or not all(
        isinstance(item, str) for item in values
    ):
        raise ValueError("Azure OpenAI returned invalid abbreviations JSON")

    existing_lower = {a.casefold() for a in existing}

    deduped = []
    seen = set()

    for item in values:
        item = item.strip()

        if not item:
            continue

        key = item.casefold()

        if key == "404":
            continue

        if key in existing_lower:
            continue

        if key in seen:
            continue

        # Standalone modifiers / invalid generic values
        if key in {
            "malignant",
            "pulmonary",
            "hepatic",
            "cancer",
            "carcinoma",
            "malignancy",
        }:
            continue

        seen.add(key)
        deduped.append(item)

        if len(deduped) >= max_new:
            break

    # Only return 404 if there are genuinely no new variants.
    if not deduped:
        return ["404"]

    return deduped


def run_llm(
    entities: list,
    output_path: Optional[Path] = None,
    article_category_records: Optional[list] = None,
    article_description_records: Optional[list] = None,
    max_new: int = 10,
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

    print(
        f"  [llm] {len(entities):,} entities to process "
        f"(up to {max_new} new variants)"
    )

    results = {}

    client = deployment = None

    try:
        for entity in entities:

            eid = entity["category_description2"]

            category = str(
                entity.get("category", "")
            ).strip()

            description = str(
                entity.get("description_2", "")
            ).strip()

            existing = []
            seen_lower = set()

            # ---------------------------------------------
            # Existing CATEGORY abbreviations
            # ---------------------------------------------
            c_data = cat_by_id.get(eid, {})

            if isinstance(c_data, dict):
                c_list = (
                    c_data.get("pubmed", [])
                    + c_data.get("clinical_trials", [])
                )
            elif isinstance(c_data, list):
                c_list = c_data
            else:
                c_list = []

            # ---------------------------------------------
            # Existing DESCRIPTION abbreviations
            # ---------------------------------------------
            d_data = desc_by_id.get(eid, {})

            if isinstance(d_data, dict):
                d_list = (
                    d_data.get("pubmed", [])
                    + d_data.get("clinical_trials", [])
                )
            elif isinstance(d_data, list):
                d_list = d_data
            else:
                d_list = []

            # ---------------------------------------------
            # Combine existing values
            # ---------------------------------------------
            for abbrev in c_list + d_list:

                if not isinstance(abbrev, str):
                    continue

                a = abbrev.strip()

                if not a:
                    continue

                if a.casefold() == "404":
                    continue

                if a.casefold() not in seen_lower:
                    existing.append(a)
                    seen_lower.add(a.casefold())

            payload = {
                "category_description2": eid,
                "category": category,
                "description_2": description,
            }

            if client is None:
                client, deployment = create_client()

            # ---------------------------------------------
            # Generate NEW LLM abbreviations
            # ---------------------------------------------
            for attempt in range(3):

                try:

                    new_abbrevs = generate(
                        client=client,
                        deployment=deployment,
                        payload=payload,
                        existing=existing,
                        max_new=max_new,
                    )

                    results[eid] = new_abbrevs
                    break

                except Exception:

                    if attempt == 2:
                        raise

                    time.sleep(2 ** attempt)

    finally:

        if client is not None:
            client.close()

    # ---------------------------------------------
    # Build final output
    # ---------------------------------------------
    output = []

    for entity in entities:

        eid = entity["category_description2"]

        output.append(
            {
                **entity,
                "payload_llm": {
                    "category": str(
                        entity["category"]
                    ).strip(),
                    "description_2": str(
                        entity["description_2"]
                    ).strip(),
                },
                "abbreviations": results.get(
                    eid,
                    ["404"],
                ),
            }
        )

    write_json(output, output_path)

    print(
        f"  [llm] Wrote {len(output):,} records → "
        f"{output_path.resolve()}"
    )

    return output


def main() -> None:

    parser = argparse.ArgumentParser(
        description="Generate LLM-only abbreviations from canonical entities."
    )

    parser.add_argument(
        "--input",
        default=str(CANONICAL_INPUT),
    )

    parser.add_argument(
        "--output",
        default=str(LLM_OUTPUT),
    )

    args = parser.parse_args()

    entities = read_json(
        Path(args.input)
    )

    run_llm(
        entities=entities,
        output_path=Path(args.output),
        max_new=10,
    )


if __name__ == "__main__":
    main()