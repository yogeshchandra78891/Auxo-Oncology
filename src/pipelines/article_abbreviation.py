import argparse
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CACHE, CANONICAL_INPUT, CATEGORY_OUTPUT, CLINICAL_TRIALS, DESCRIPTION_OUTPUT, PUBMED
from utils.azure_client import create_client
from utils.cache import load, save
from utils.json_utils import fingerprint, read_json, write_json


PROMPT_VERSION = "knowledge-base-grounded-v1"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
TEXT_FIELDS = ("title", "summary", "condition", "interventions", "abstract")


def tokens(value: str) -> set[str]:
    return {token for token in TOKEN_PATTERN.findall(value.casefold()) if len(token) > 2}


def load_knowledge_base() -> list[dict[str, str]]:
    """Load the two approved evidence sources from the data directory."""
    records: list[dict[str, str]] = []
    if PUBMED.exists():
        pubmed_articles = re.split(r"(?m)(?=^\d+\.\s)", PUBMED.read_text(encoding="utf-8-sig"))
        records.extend(
            {"source": "PubMed", "text": article.strip()}
            for article in pubmed_articles
            if article.strip()
        )
    for trial in read_json(CLINICAL_TRIALS):
        if not isinstance(trial, dict):
            continue
        text = "\n".join(
            f"{field}: {trial[field]}" for field in TEXT_FIELDS if trial.get(field)
        )
        if text:
            records.append({"source": "ClinicalTrials.gov", "text": text})
    return records


def relevant_context(query: str, knowledge_base: list[dict[str, str]], limit: int) -> str:
    """Return only locally matching evidence; an empty result means 404."""
    query_tokens = tokens(query)
    matches = []
    for record in knowledge_base:
        score = len(query_tokens & tokens(record["text"]))
        if score:
            matches.append((score, record))
    matches.sort(key=lambda item: -item[0])
    return "\n\n".join(
        f"Source: {record['source']}\n{record['text'][:6000]}"
        for _, record in matches[:limit]
    )


def abbreviations_from_entity(client, deployment: str, field: str, value: str, context: str) -> list[str]:
    instructions = """You extract clinically valid abbreviations and aliases for one canonical ICD entity field using an approved knowledge base.

Use the supplied evidence as the only knowledge source. Return only abbreviations, acronyms, or alternate clinical names explicitly supported by that evidence and directly relevant to the supplied canonical field. Do not use ICD codes, code_3, description_3, other canonical entities, or outside knowledge. Do not infer or invent names.

Style example only: for a canonical value "Tongue Cancer", evidence may support aliases such as "Tongue Carcinoma", "Tongue Malignancy", and "Glossal Cancer". Do not output codes such as "C02" or "C02.0".

If the evidence does not mention the supplied category/description, or does not support any abbreviation or alternate name, return exactly [\"404\"]. Never combine "404" with other values.
Return JSON only in this exact form: {\"abbreviations\": [\"...\"]}. The array must contain unique strings."""
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate knowledge-base-grounded abbreviations for canonical category or description fields.")
    parser.add_argument("--mode", choices=("category", "description"), required=True)
    parser.add_argument("--input", default=str(CANONICAL_INPUT))
    parser.add_argument("--output")
    parser.add_argument("--top-k", type=int, default=5, help="Maximum relevant PubMed/trial records supplied as evidence.")
    parser.add_argument("--refresh-cache", action="store_true")
    args = parser.parse_args()
    entities = read_json(Path(args.input))
    field = "category" if args.mode == "category" else "description_2"
    payload_field = "payload_category" if args.mode == "category" else "payload_description"
    output_path = Path(args.output or (CATEGORY_OUTPUT if args.mode == "category" else DESCRIPTION_OUTPUT))
    cache_path = CACHE / f"{args.mode}_abbreviations_cache.json"
    cache = {} if args.refresh_cache else load(cache_path)
    knowledge_base = load_knowledge_base()
    knowledge_base_version = fingerprint(knowledge_base)

    def cache_key(query: str) -> str:
        return fingerprint({"mode": args.mode, "query": query, "top_k": args.top_k,
                            "knowledge_base_version": knowledge_base_version, "prompt_version": PROMPT_VERSION})

    unique_queries = list(dict.fromkeys(str(entity.get(field, "")).strip() for entity in entities if entity.get(field)))
    missing = [query for query in unique_queries if cache_key(query) not in cache]
    print(f"{len(entities):,} entities; {len(unique_queries):,} unique {args.mode} payloads; {len(missing):,} to process.")
    client = deployment = None
    try:
        for query in missing:
            key = cache_key(query)
            context = relevant_context(query, knowledge_base, args.top_k)
            if not context:
                cache[key] = {"abbreviations": ["404"]}
                save(cache, cache_path)
                continue
            if client is None:
                client, deployment = create_client()
            for attempt in range(3):
                try:
                    cache[key] = {"abbreviations": abbreviations_from_entity(client, deployment, field, query, context)}
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
        query = str(entity[field]).strip()
        key = cache_key(query)
        output.append({
            "category_description2": entity["category_description2"],
            "category": entity["category"],
            "description_2": entity["description_2"],
            payload_field: {field: query},
            "abbreviations": cache.get(key, {}).get("abbreviations", []),
        })
    write_json(output, output_path)
    print(f"Wrote {len(output):,} records to {output_path.resolve()}")


if __name__ == "__main__":
    main()
