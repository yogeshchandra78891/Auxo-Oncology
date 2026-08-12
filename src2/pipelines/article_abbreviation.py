import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import CACHE, CANONICAL_INPUT, CATEGORY_OUTPUT, CLINICAL_TRIALS, DESCRIPTION_OUTPUT, PUBMED
from src2.rag.context_builder import build_context
from src2.rag.retriever import retrieve
from utils.azure_client import create_client
from utils.cache import load, save
from utils.json_utils import fingerprint, read_json, write_json


def abbreviations_from_context(client, deployment: str, query: str, context: str) -> list[str]:
    instructions = """Extract concise, clinically valid abbreviations, synonyms, and common alternate names for the supplied payload.
Use only the payload and retrieved context. Do not invent abbreviations. Return JSON only: {\"abbreviations\": [\"...\"]}.
Return a unique array of strings; return [] if none are supported."""
    response = client.chat.completions.create(
        model=deployment,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": f"Payload: {query}\n\nRetrieved context:\n{context}"},
        ],
    )
    content = response.choices[0].message.content
    values = json.loads(content or "{}").get("abbreviations", [])
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("Azure OpenAI returned invalid abbreviations JSON")
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RAG-grounded abbreviations from category or description payloads.")
    parser.add_argument("--mode", choices=("category", "description"), required=True)
    parser.add_argument("--input", default=str(CANONICAL_INPUT))
    parser.add_argument("--output")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--refresh-cache", action="store_true")
    args = parser.parse_args()
    entities = read_json(Path(args.input))
    field = "category" if args.mode == "category" else "description_2"
    payload_field = "payload_category" if args.mode == "category" else "payload_description"
    output_path = Path(args.output or (CATEGORY_OUTPUT if args.mode == "category" else DESCRIPTION_OUTPUT))
    cache_path = CACHE / f"{args.mode}_abbreviations_cache.json"
    cache = {} if args.refresh_cache else load(cache_path)

    # Retrieval + model work is deduplicated by the exact source payload.
    # Changing either local source invalidates only article-based cache entries.
    source_version = fingerprint({"pubmed": read_json(PUBMED), "clinical_trials": read_json(CLINICAL_TRIALS)})
    def cache_key(query: str) -> str:
        return fingerprint({"mode": args.mode, "query": query, "top_k": args.top_k, "source_version": source_version})

    unique_queries = list(dict.fromkeys(str(entity.get(field, "")).strip() for entity in entities if entity.get(field)))
    missing = [query for query in unique_queries if cache_key(query) not in cache]
    print(f"{len(entities):,} entities; {len(unique_queries):,} unique {args.mode} payloads; {len(missing):,} to process.")
    client = deployment = None
    try:
        for query in missing:
            key = cache_key(query)
            retrieved = retrieve(PUBMED, CLINICAL_TRIALS, query, args.top_k)
            context = build_context(retrieved)
            if not retrieved["pubmed"] and not retrieved["clinical_trials"]:
                cache[key] = {"abbreviations": []}
                save(cache, cache_path)
                continue
            if client is None:
                client, deployment = create_client()
            for attempt in range(3):
                try:
                    cache[key] = {"abbreviations": abbreviations_from_context(client, deployment, query, context)}
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
