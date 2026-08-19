from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
import time
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CANONICAL_INPUT, CATEGORY_OUTPUT, CLINICAL_TRIALS, DESCRIPTION_OUTPUT, PUBMED
from utils.azure_client import create_client
from utils.json_utils import read_json, write_json

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
TEXT_FIELDS = ("title", "summary", "condition", "interventions", "abstract")

GENERIC_ENTITY_TOKENS = frozenset({
    "and", "are", "cancer", "disease", "disorder", "ill", "malignant",
    "neoplasm", "of", "organ", "organs", "other", "specified", "system",
    "the", "undefined", "unspecified",
})


def tokens(value: str) -> set[str]:
    return {token for token in TOKEN_PATTERN.findall(value.casefold()) if len(token) > 2}


def entity_tokens(value: str) -> set[str]:
    return tokens(value) - GENERIC_ENTITY_TOKENS


def load_knowledge_base() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    if PUBMED.exists():
        for entry in read_json(PUBMED):
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", "").strip()
            abstract = entry.get("text", "").strip()
            combined = f"{title} {abstract}".strip()
            if combined:
                records.append({"source": "PubMed", "text": combined})
    if CLINICAL_TRIALS.exists():
        for trial in read_json(CLINICAL_TRIALS):
            if not isinstance(trial, dict):
                continue
            text = "\n".join(
                f"{field}: {trial[field]}" for field in TEXT_FIELDS if trial.get(field)
            )
            if text:
                records.append({"source": "ClinicalTrials.gov", "text": text})
    return records


def relevant_context(
    query: str, 
    knowledge_base: list[dict[str, str]], 
    limit: int, 
    source: Optional[str] = None
) -> str:
    specific_tokens = entity_tokens(query)
    if not specific_tokens:
        return ""
    matches = []
    for record in knowledge_base:
        if source and record.get("source") != source:
            continue
        score = len(specific_tokens & tokens(record["text"]))
        if score:
            matches.append((score, record))
    matches.sort(key=lambda item: -item[0])
    return "\n\n".join(
        f"Source: {record['source']}\n{record['text'][:6000]}"
        for _, record in matches[:limit]
    )


def abbreviations_from_entity(client, deployment: str, field: str, value: str, context: str) -> list[str]:
    instructions = """You extract a complete, clinically valid alias family for one canonical ICD entity field using an approved knowledge base.

Use the supplied Context as the only knowledge source. The submitted category or description must be specifically mentioned or clearly implied by the evidence. If it is not, return exactly ["404"]. Do not use ICD codes, code_3, description_3, other canonical entities, or outside knowledge.

━━━ WHAT TO INCLUDE ━━━
Return every unique, directly relevant variant supported by the evidence:
- The canonical common disease name (e.g., "Liver Cancer", "Lung Cancer")
- <site> Cancer, <site> Carcinoma, <site> Malignancy, Malignancy of <site>
- Established histological subtypes mentioned in the evidence (e.g., "Hepatocellular Carcinoma", "Adenocarcinoma of Lung")
- Widely used acronyms that unambiguously refer to this entity (e.g., "HCC", "NSCLC", "TNBC")
- Established anatomical synonyms (e.g., "Glossal Cancer" for tongue, "Hepatoma" for liver cell carcinoma)
- Lay terms in clinical use (e.g., "Voice Box Cancer" for laryngeal cancer)
- Directional/laterality qualifiers when the description specifies a site (e.g., "Right Ovarian Cancer")
- Combination/overlapping terms when the description covers multiple named sites

━━━ WHAT TO EXCLUDE ━━━
- Standalone modifiers without a complete entity phrase (never "malignant", "pulmonary", "hepatic" alone)
- ICD codes or numeric codes of any kind
- Aliases for a DIFFERENT cancer, organ, or body system
- Duplicate values (case-insensitive)   
- The sentinel "404" combined with real values

━━━ REQUIRED OUTPUT STYLE — STUDY THESE EXAMPLES (for illustration purposes) ━━━

Input: category="Tongue Cancer", description="Malignant neoplasm of tongue"
Output: ["Tongue Cancer", "Tongue Carcinoma", "Tongue Malignancy", "Glossal Cancer", "Lingual Cancer"]

Input: category="Liver Cancer", description="Malignant neoplasm of liver and intrahepatic bile ducts"
Output: ["Liver Cancer", "Liver Carcinoma", "Hepatocellular Carcinoma", "HCC", "Hepatoma", "Liver Cell Carcinoma", "Intrahepatic Cholangiocarcinoma", "ICC", "Malignant Neoplasm of Liver", "Primary Liver Cancer"]

Input: category="Lymphoma", description="Nodular sclerosis classical Hodgkin lymphoma"
Output: ["Nodular Sclerosis Hodgkin Lymphoma", "NSHL", "Nodular Sclerosis HL", "NS Hodgkin Lymphoma", "Classical HL - Nodular Sclerosis", "Hodgkin Lymphoma", "HL", "Hodgkin's Lymphoma"]

Input: category="Breast Cancer", description="Malignant neoplasm of central portion of female breast"
Output: ["Breast Cancer", "Mammary Carcinoma", "Breast Carcinoma", "Ductal Carcinoma", "Lobular Carcinoma", "Triple-Negative Breast Cancer", "TNBC", "HER2-Positive Breast Cancer", "Metastatic Breast Cancer", "mBC"]

Input: category="Atherosclerosis", description="Atherosclerosis of native arteries of extremities with intermittent claudication"
Output: ["Atherosclerosis", "Peripheral Artery Disease", "PAD", "Peripheral Vascular Disease", "PVD", "ASCVD", "Atherosclerotic Cardiovascular Disease", "claudication"]

Input: category="Lipidemias", description="Pure hypercholesterolemia, unspecified"
Output: ["Hypercholesterolemia", "Lipidemias", "High Cholesterol", "Dyslipidemia", "Familial Hypercholesterolemia", "FH"]

━━━ SENTINEL RULE ━━━
If the evidence does not support ANY entity-specific alias, return exactly ["404"]. Never combine "404" with other values.

Return JSON only in this exact form: {"abbreviations": ["..."]}. The array must contain unique strings."""
    response = client.chat.completions.create(
        model=deployment,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps({"field": field, "value": value, "knowledge_base_evidence": context})},
        ],
    )
    content = response.choices[0].message.content
    values = json.loads(content or "{}").get("abbreviations", [])
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("Azure OpenAI returned invalid abbreviations JSON")
    cleaned = list(dict.fromkeys(item.strip() for item in values if item.strip()))
    return ["404"] if not cleaned or "404" in cleaned else cleaned


def run_abbreviations(
    entities: list[dict],
    mode: str,
    output_path: Path,
    top_k: int = 5,
    knowledge_base: Optional[list] = None,
) -> list[dict]:
    if mode not in ("category", "description"):
        raise ValueError(f"mode must be 'category' or 'description', got {mode!r}")

    field = "category" if mode == "category" else "description_2"
    payload_field = "payload_category" if mode == "category" else "payload_description"

    kb = knowledge_base if knowledge_base is not None else load_knowledge_base()

    unique_queries = list(dict.fromkeys(
        str(entity.get(field, "")).strip() for entity in entities if entity.get(field)
    ))
    print(f"  [{mode}] {len(entities):,} entities | {len(unique_queries):,} unique queries")

    sources = [("pubmed", "PubMed"), ("clinical_trials", "ClinicalTrials.gov")]
    results: dict[str, dict[str, list[str]]] = {}
    client = deployment = None

    try:
        for query in unique_queries:
            results[query] = {}
            for source_key, source_name in sources:
                context = relevant_context(query, kb, top_k, source=source_name)
                if not context:
                    results[query][source_key] = ["404"]
                    continue
                if client is None:
                    client, deployment = create_client()
                for attempt in range(3):
                    try:
                        results[query][source_key] = abbreviations_from_entity(client, deployment, field, query, context)
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
        query = str(entity[field]).strip()
        output.append({
            "category_description2": entity["category_description2"],
            "category": entity["category"],
            "description_2": entity["description_2"],
            payload_field: {field: query},
            "abbreviations": results.get(query, {"pubmed": ["404"], "clinical_trials": ["404"]}),
        })
    write_json(output, output_path)
    print(f"  [{mode}] Wrote {len(output):,} records → {output_path.resolve()}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate knowledge-base-grounded abbreviations for canonical category or description fields.")
    parser.add_argument("--mode", choices=("category", "description"), required=True)
    parser.add_argument("--input", default=str(CANONICAL_INPUT))
    parser.add_argument("--output")
    parser.add_argument("--top-k", type=int, default=5, help="Maximum relevant PubMed/trial records supplied as evidence.")
    args = parser.parse_args()

    entities = read_json(Path(args.input))
    output_path = Path(args.output or (CATEGORY_OUTPUT if args.mode == "category" else DESCRIPTION_OUTPUT))

    run_abbreviations(
        entities=entities,
        mode=args.mode,
        output_path=output_path,
        top_k=args.top_k,
        knowledge_base=None,
    )


if __name__ == "__main__":
    main()