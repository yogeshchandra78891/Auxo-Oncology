"""Persistent Chroma storage for PubMed and ClinicalTrials reference records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, Sequence


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class ChromaVectorStore:
    """Own a versioned Chroma collection with caller-supplied Azure embeddings."""

    COLLECTION_NAME = "clinical_reference"

    def __init__(self, persist_directory: Path) -> None:
        try:
            import chromadb
        except ImportError as error:
            raise SystemExit("Chroma is required. Install dependencies with: pip install -r requirement/requirements.txt") from error
        persist_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_directory))

    def rebuild_if_changed(
        self, records: list[dict[str, Any]], source_version: str, embedder: Embedder
    ) -> None:
        try:
            collection = self.client.get_collection(self.COLLECTION_NAME)
            if collection.metadata and collection.metadata.get("source_version") == source_version:
                return
            self.client.delete_collection(self.COLLECTION_NAME)
        except Exception as error:
            # Chroma raises its own NotFoundError; do not require it as a public dependency here.
            if "does not exist" not in str(error).casefold() and "not found" not in str(error).casefold():
                raise

        collection = self.client.create_collection(
            self.COLLECTION_NAME, metadata={"source_version": source_version}
        )
        if not records:
            return

        documents = [record["document"] for record in records]
        collection.upsert(
            ids=[record["id"] for record in records],
            documents=documents,
            embeddings=embedder.embed(documents),
            metadatas=[
                {
                    "source": record["source"],
                    "record_json": json.dumps(record["record"], ensure_ascii=False),
                }
                for record in records
            ],
        )

    def query(self, query_embedding: list[float], limit: int) -> list[dict[str, Any]]:
        try:
            collection = self.client.get_collection(self.COLLECTION_NAME)
        except Exception:
            return []
        if collection.count() == 0:
            return []
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, collection.count()),
            include=["metadatas"],
        )
        metadatas = result.get("metadatas", [[]])[0]
        records = []
        for metadata in metadatas:
            if not metadata or "record_json" not in metadata:
                continue
            record = json.loads(metadata["record_json"])
            record["_source"] = metadata.get("source", "")
            records.append(record)
        return records
