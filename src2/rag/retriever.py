"""Azure OpenAI + Chroma retriever for PubMed and ClinicalTrials records."""

from __future__ import annotations

import atexit
from pathlib import Path
from typing import Any

from config.config import VECTOR_DB
from src2.rag.embedder import AzureOpenAIEmbedder
from src2.rag.vector_store import ChromaVectorStore
from utils.json_utils import fingerprint, read_json


TEXT_FIELDS = ("title", "abstract", "summary", "brief_summary", "description", "condition", "interventions")
_embedder: AzureOpenAIEmbedder | None = None


def _get_embedder() -> AzureOpenAIEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = AzureOpenAIEmbedder()
    return _embedder


def _close_embedder() -> None:
    if _embedder is not None:
        _embedder.close()


atexit.register(_close_embedder)


def _document(record: dict[str, Any]) -> str:
    return "\n".join(f"{field}: {record[field]}" for field in TEXT_FIELDS if record.get(field))


def _index_records(source: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = []
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        document = _document(record)
        if document:
            indexed.append({
                "id": fingerprint({"source": source, "position": position, "record": record}),
                "source": source,
                "record": record,
                "document": document,
            })
    return indexed


def retrieve(pubmed_path: Path, trials_path: Path, query: str, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    """Retrieve semantic matches, rebuilding Chroma only when source data changes."""
    pubmed = read_json(pubmed_path)
    trials = read_json(trials_path)
    if not pubmed and not trials:
        return {"pubmed": [], "clinical_trials": []}

    records = _index_records("pubmed", pubmed) + _index_records("clinical_trials", trials)
    version = fingerprint({"pubmed": pubmed, "clinical_trials": trials})
    embedder = _get_embedder()
    store = ChromaVectorStore(VECTOR_DB)
    store.rebuild_if_changed(records, version, embedder)
    # Ask for twice K so each source can contribute up to K semantic matches.
    matches = store.query(embedder.embed([query])[0], limit * 2)
    return {
        "pubmed": [record for record in matches if record.get("_source") == "pubmed"][:limit],
        "clinical_trials": [record for record in matches if record.get("_source") == "clinical_trials"][:limit],
    }
