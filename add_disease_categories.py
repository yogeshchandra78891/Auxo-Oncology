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
from dotenv import load_dotenv
from google import genai
from google.genai import types
import truststore

DEFAULT_INPUT = "ICD_raw_2025(in).csv"
DEFAULT_OUTPUT = "ICD_raw_2025_with_category11.csv"
DEFAULT_CACHE = "icd_category_cache_v2.json"
DEFAULT_MODEL = "gemini-3.5-flash-lite"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate concise main categories for ICD descriptions using Gemini."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input ICD CSV path.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output CSV path.")
    parser.add_argument(
        "--description-column",
        default="description_2",
        help="CSV column to categorize (D is description_2 in the supplied file).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model to use.")
    parser.add_argument("--batch-size", type=int, default=75, help="Descriptions per API call.")
    parser.add_argument(
        "--cache", default=DEFAULT_CACHE, help="JSON cache path; makes interrupted runs resumable."
    )
    parser.add_argument(
        "--limit", type=int, help="Only process this many distinct descriptions (useful for a trial run)."
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore prior cached model labels and regenerate all non-rule categories.",
    )
    return parser.parse_args()


def load_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        raw_cache = json.load(file)
    return {str(description): str(category) for description, category in raw_cache.items()}


def save_cache(cache: dict[str, str], path: Path) -> None:
    """Write atomically so a stopped run does not corrupt the cache."""
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(cache, file, ensure_ascii=False, indent=2)
    temporary_path.replace(path)

def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def rule_category(description: str) -> str | None:
    """Return guaranteed disease-family labels for high-value ICD patterns."""
    text = description.casefold()
    if "tuberculosis" in text:
        return "Tuberculosis"
    if (
        "lymphoma" in text
        or "malignant immunoproliferative disease" in text
        or "b-cell lymphoproliferative" in text
        or "lymphoid leukemia" in text
    ):
        return "Lymphoma"
    if "leukemia" in text or "leukaemia" in text:
        return "Leukemia"
    return None


def normalize_category(description: str, category: str) -> str:
    """Apply deterministic taxonomy rules after model output as a safety net."""
    return rule_category(description) or category.strip()

def categories_for_batch(
    client: genai.Client, model: str, descriptions: list[str]
) -> dict[str, str]:
    """Ask Gemini for one concise category per description as structured JSON."""
    numbered_descriptions = "\n".join(
        f"{index}. {description}" for index, description in enumerate(descriptions)
    )
    response_schema = {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "category": {"type": "string"},
                    },
                    "required": ["index", "category"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["categories"],
        "additionalProperties": False,
    }
    instructions = """You normalize ICD diagnosis descriptions into a short, reusable Main Category.
Return exactly one category for each numbered description.

Rules:
- The category is a stable disease FAMILY, not a restatement of the diagnosis.
- Use a clinically meaningful broad label of 1-4 words in Title Case.
- For malignant neoplasms, use the anatomical cancer category when clear: for example,
  'Malignant neoplasm of lip' -> 'Lip Cancer'.
- Prefer a well-known disease-family label when it is more useful: for example,
  'Follicular lymphoma' -> 'Lymphoma'.
- Always group every form, complication, site, sequela, and qualifier of tuberculosis
  under 'Tuberculosis': 'Respiratory tuberculosis' -> 'Tuberculosis';
  'Sequelae of tuberculosis' -> 'Tuberculosis'.
- Always group lymphoma, B-cell lymphoma, Hodgkin lymphoma, non-Hodgkin lymphoma,
  and malignant immunoproliferative diseases under 'Lymphoma':
  'Malignant immunoproliferative diseases and certain other B-cell lymphomas' -> 'Lymphoma'.
- Remove qualifiers such as unspecified, acute/chronic, laterality, stage, recurrence,
  sequela, manifestation, organism, site, and subtype unless they fundamentally
  change the disease family.
- Do not invent anatomy or a diagnosis that is absent from the description.
- Do not use ICD codes in the category.
"""
    response = client.models.generate_content(
        model=model,
        contents=f"Descriptions to categorize:\n{numbered_descriptions}",
        config=types.GenerateContentConfig(
            system_instruction=instructions,
            response_mime_type="application/json",
            response_json_schema=response_schema,
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned no text response for this batch.")

    items = json.loads(response.text)["categories"]
    by_index = {item["index"]: item["category"].strip() for item in items}
    expected_indexes = set(range(len(descriptions)))
    if set(by_index) != expected_indexes or any(not value for value in by_index.values()):
        raise ValueError("Gemini returned an incomplete category batch; no results were saved.")
    return {
        descriptions[index]: normalize_category(descriptions[index], by_index[index])
        for index in range(len(descriptions))
    }


def create_gemini_client(api_key: str) -> genai.Client:
    """Use Windows trusted root certificates for corporate HTTPS proxies.

    Set GEMINI_CA_BUNDLE in .env only when IT provides a PEM certificate bundle
    that is not already installed in the Windows Trusted Root store.
    """
    ca_bundle = os.getenv("GEMINI_CA_BUNDLE")
    if ca_bundle:
        certificate_path = Path(ca_bundle).expanduser()
        if not certificate_path.is_file():
            raise SystemExit(f"GEMINI_CA_BUNDLE does not exist: {certificate_path}")
        verify: ssl.SSLContext | str = str(certificate_path)
    else:
        verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    http_client = httpx.Client(verify=verify, trust_env=True, timeout=60.0)
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(httpx_client=http_client),
    )


def main() -> None:
    args = parse_args()
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path)
    api_key = os.getenv("GEMINI_API_KEY")
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
    rule_based = {description: rule_category(description) for description in distinct}
    for description, category in rule_based.items():
        if category:
            cache[description] = category
    pending = [description for description in distinct if not rule_based[description] and description not in cache]
    print(
        f"{len(descriptions):,} rows; {len(distinct):,} distinct descriptions; "
        f"{sum(category is not None for category in rule_based.values()):,} rule-based; "
        f"{len(pending):,} to classify with Gemini."
    )
    save_cache(cache, cache_path)

    if pending:
        if not api_key or api_key == "paste_your_gemini_api_key_here":
            raise SystemExit(f"GEMINI_API_KEY is not set. Add it to {env_path} before running this script.")
        client = create_gemini_client(api_key)
        for batch_number, batch in enumerate(chunks(pending, args.batch_size), start=1):
            for attempt in range(3):
                try:
                    cache.update(categories_for_batch(client, args.model, batch))
                    save_cache(cache, cache_path)
                    completed = min(batch_number * args.batch_size, len(pending))
                    print(f"Completed batch {batch_number} ({completed:,}/{len(pending):,}).")
                    break
                except Exception as error:  # Network/rate-limit errors are safe to retry.
                    if attempt == 2:
                        raise RuntimeError(f"Batch {batch_number} failed after 3 attempts.") from error
                    wait_seconds = 2**attempt
                    print(f"Batch {batch_number} failed ({error}); retrying in {wait_seconds}s.")
                    time.sleep(wait_seconds)

    output = source.copy()
    output["Category"] = descriptions.map(cache)
    output.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(output):,} rows to {output_path.resolve()}")
    print(output.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
