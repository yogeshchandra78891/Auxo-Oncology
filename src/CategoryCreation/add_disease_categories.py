"""Generate LLM-only ICD main categories with an Azure OpenAI GPT-4o mini deployment."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import time
from pathlib import Path
from typing import Iterable

import httpx
import pandas as pd
import truststore
from dotenv import load_dotenv
from openai import AzureOpenAI


DEFAULT_INPUT = "data/ICD_raw_2025(in).csv"
DEFAULT_OUTPUT = "data/ICD_with_categories.csv"
DEFAULT_CACHE = "data/icd_category_cache.json"
DEFAULT_API_VERSION = "2025-01-01-preview"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = PROJECT_ROOT / DEFAULT_CACHE
LEGACY_CACHE_PATH = PROJECT_ROOT / "icd_category_cache_v2.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate concise ICD main categories using an Azure OpenAI deployment."
    )
    parser.add_argument("--input", default=str(PROJECT_ROOT / DEFAULT_INPUT), help="Input ICD CSV path.")
    parser.add_argument("--output", default=str(PROJECT_ROOT / DEFAULT_OUTPUT), help="Output CSV path.")
    parser.add_argument(
        "--description-column",
        default="description_2",
        help="CSV column to categorize (D is description_2 in the supplied file).",
    )
    parser.add_argument(
        "--deployment",
        help="Azure GPT-4o mini deployment name. Overrides AZURE_OPENAI_DEPLOYMENT.",
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Descriptions per API call.")
    # Reuse the cache created before the data-directory restructuring when present.
    default_cache = LEGACY_CACHE_PATH if not DEFAULT_CACHE_PATH.exists() and LEGACY_CACHE_PATH.exists() else DEFAULT_CACHE_PATH
    parser.add_argument("--cache", default=str(default_cache), help="JSON cache path for resumable runs.")
    parser.add_argument("--limit", type=int, help="Only process this many distinct descriptions.")
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore prior cached labels and regenerate all categories with the LLM.",
    )
    return parser.parse_args()

def load_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        raw_cache = json.load(file)
    return {str(description): str(category) for description, category in raw_cache.items()}


def save_cache(cache: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(cache, file, ensure_ascii=False, indent=2)
    temporary_path.replace(path)

def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def categories_for_batch(
    client: AzureOpenAI, deployment: str, descriptions: list[str]
) -> dict[str, str]:
    """Request one JSON category per description, using no local override rules."""
    numbered_descriptions = "\n".join(
        f"{index}. {description}" for index, description in enumerate(descriptions)
    )
    instructions = """You normalize ICD diagnosis descriptions into a short, reusable Main Category.
Return JSON only in exactly this shape: {"categories": [{"index": 0, "category": "..."}]}.
Return exactly one item for every supplied index.

Rules:
- The category is a stable disease FAMILY, not a restatement of the diagnosis.
- Use a clinically meaningful broad label of 1-4 words in Title Case.
- For malignant neoplasms, use the anatomical cancer category when clear: for example,
  'Malignant neoplasm of lip' -> 'Lip Cancer'.
- Prefer a well-known disease-family label when it is more useful: for example,
  'Follicular lymphoma' -> 'Lymphoma'.
- Group every form, complication, site, sequela, and qualifier of tuberculosis under
  'Tuberculosis': 'Respiratory tuberculosis' -> 'Tuberculosis';
  'Sequelae of tuberculosis' -> 'Tuberculosis'.
- Group lymphoma, B-cell lymphoma, Hodgkin lymphoma, non-Hodgkin lymphoma, and malignant
  immunoproliferative diseases under 'Lymphoma'.
- Remove qualifiers such as unspecified, acute/chronic, laterality, stage, recurrence,
  sequela, manifestation, organism, site, and subtype unless they fundamentally change
  the disease family.
- Do not invent anatomy or a diagnosis absent from the description. Do not use ICD codes.
"""
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": f"Descriptions to categorize:\n{numbered_descriptions}"},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Azure OpenAI returned no text response for this batch.")

    items = json.loads(content)["categories"]
    by_index = {item["index"]: str(item["category"]).strip() for item in items}
    expected_indexes = set(range(len(descriptions)))
    if set(by_index) != expected_indexes or any(not value for value in by_index.values()):
        raise ValueError("The model returned an incomplete category batch; no results were saved.")
    return {descriptions[index]: by_index[index] for index in range(len(descriptions))}


def create_azure_client(endpoint: str, api_key: str, api_version: str) -> AzureOpenAI:
    """Keep TLS validation enabled while supporting corporate Windows certificates."""
    ca_bundle = os.getenv("AZURE_OPENAI_CA_BUNDLE")
    if ca_bundle:
        certificate_path = Path(ca_bundle).expanduser()
        if not certificate_path.is_file():
            raise SystemExit(f"AZURE_OPENAI_CA_BUNDLE does not exist: {certificate_path}")
        verify: ssl.SSLContext | str = str(certificate_path)
    else:
        verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        http_client=httpx.Client(verify=verify, trust_env=True, timeout=90.0),
    )


def main() -> None:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1.")

    input_path, output_path, cache_path = map(Path, (args.input, args.output, args.cache))
    source = pd.read_csv(input_path, dtype=str, low_memory=False)
    if args.description_column not in source.columns:
        available = ", ".join(source.columns)
        raise SystemExit(f"Column '{args.description_column}' was not found. Available columns: {available}")

    descriptions = source[args.description_column].fillna("").str.strip()
    distinct = list(dict.fromkeys(value for value in descriptions if value))
    if args.limit is not None:
        distinct = distinct[: args.limit]

    cache = {} if args.refresh_cache else load_cache(cache_path)
    pending = [description for description in distinct if description not in cache]
    print(f"{len(descriptions):,} rows; {len(distinct):,} distinct descriptions; {len(pending):,} to classify with Azure OpenAI.")

    if pending:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = args.deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)
        missing = [
            name
            for name, value in {
                "AZURE_OPENAI_ENDPOINT": endpoint,
                "AZURE_OPENAI_API_KEY": api_key,
                "AZURE_OPENAI_DEPLOYMENT": deployment,
            }.items()
            if not value
        ]
        if missing:
            raise SystemExit(f"Missing .env values: {', '.join(missing)}")

        client = create_azure_client(endpoint, api_key, api_version)
        try:
            for batch_number, batch in enumerate(chunks(pending, args.batch_size), start=1):
                for attempt in range(3):
                    try:
                        cache.update(categories_for_batch(client, deployment, batch))
                        save_cache(cache, cache_path)
                        completed = min(batch_number * args.batch_size, len(pending))
                        print(f"Completed batch {batch_number} ({completed:,}/{len(pending):,}).")
                        break
                    except Exception as error:
                        if attempt == 2:
                            raise RuntimeError(f"Batch {batch_number} failed after 3 attempts.") from error
                        wait_seconds = 2**attempt
                        print(f"Batch {batch_number} failed ({error}); retrying in {wait_seconds}s.")
                        time.sleep(wait_seconds)
        finally:
            client.close()

    output = source.copy()
    output["Category"] = descriptions.map(cache)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(output):,} rows to {output_path.resolve()}")
    print(output.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
