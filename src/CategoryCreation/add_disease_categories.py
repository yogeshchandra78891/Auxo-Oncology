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


DEFAULT_INPUT = "data/ICD_raw_2025(in)-new.csv"
DEFAULT_OUTPUT = "data/ICD_with_categories.csv"
DEFAULT_API_VERSION = "2025-01-01-preview"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    parser.add_argument("--batch-size", type=int, default=70, help="Descriptions per API call.")
    parser.add_argument("--limit", type=int, help="Only process this many distinct descriptions.")
    return parser.parse_args()

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

    # 5. Use the canonical disease name rather than simply repeating the wording from description_2.
    instructions = """ 
You are an ICD-10-CM diagnosis normalization engine.
Convert each description_2 into ONE canonical Main Category using ONLY the information explicitly stated in description_2.

CORE OBJECTIVE:
Generate the most appropriate standardized category while preserving the clinically meaningful disease and anatomical site.
The goal is CONSISTENT CATEGORY NORMALIZATION, not free-form medical summarization.

RULES:

1. Do not generalize a specific anatomical site to an unrelated broader site,like Oropharynx → Oropharyngeal Cancer, NOT Throat Cancer
2. For malignant neoplasms, use the canonical cancer category for the stated site, like Malignant neoplasm of ureter → Ureteral Cancer.
3. Remove administrative qualifiers such as: unspecified, other, laterality, stage, sequela, and similar qualifiers.
4. Do not invent anatomy, disease, histology, or clinical information.
5. Do not add qualifiers such as "Chronic", "Acute", "Gland", "Cerebral", etc.
6. Use 1–4 words in Title Case whenever possible.
7. Lymphoma variants → Lymphoma.
8. Return exactly one category per supplied index.

Some examples of Canonical Category conversions(for illustration only):

Malignant melanoma of skin → Skin Cancer
Other and unspecified malignant neoplasm of skin → Non-Melanoma Skin Cancer
Malignant neoplasm of accessory sinuses → Sinus Cancer
Malignant neoplasm of other and unspecified parts of biliary tract → Bile Duct Cancer
Malignant neoplasm of meninges → Meningioma
Cerebral infarction → Ischemic Stroke
Acute myocardial infarction → Heart Attack
Angina pectoris → Angina
Disorders of lipoprotein metabolism and other lipidemias → Lipidemia

Occlusion and stenosis of cerebral arteries, not resulting in cerebral infarction
→ Occlusion And Stenosis Of Precerebral Arteries

Malignant neoplasm of other and unspecified female genital organs
→ Fallopian Tube Cancer

Malignant neoplasm of peripheral nerves and autonomic nervous system
→ Peripheral Nerve Sheath Tumor

Other and unspecified malignant neoplasms of lymphoid, hematopoietic and related tissue
→ Blood Cancer

Return JSON only:
{"categories":[{"index":0,"category":"..."}]}
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
        print("AZURE_OPENAI_CA_BUNDLE not set; using system trust store for TLS validation.")
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

    input_path, output_path = Path(args.input), Path(args.output)
    source = pd.read_csv(input_path, dtype=str, low_memory=False)
    if args.description_column not in source.columns:
        available = ", ".join(source.columns)
        raise SystemExit(f"Column '{args.description_column}' was not found. Available columns: {available}")

    descriptions = source[args.description_column].fillna("").str.strip()
    distinct = list(dict.fromkeys(value for value in descriptions if value))
    if args.limit is not None:
        distinct = distinct[: args.limit]

    print(f"{len(descriptions):,} rows; {len(distinct):,} distinct descriptions; {len(distinct):,} to classify with Azure OpenAI.")

    results: dict[str, str] = {}

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
        for batch_number, batch in enumerate(chunks(distinct, args.batch_size), start=1):
            for attempt in range(3):
                try:
                    results.update(categories_for_batch(client, deployment, batch))
                    completed = min(batch_number * args.batch_size, len(distinct))
                    print(f"Completed batch {batch_number} ({completed:,}/{len(distinct):,}).")
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
    output["Category"] = descriptions.map(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(output):,} rows to {output_path.resolve()}")
    print(output.head(10).to_string(index=False))


if __name__ == "__main__":
    main()