"""Azure OpenAI embedding adapter used by the local Chroma vector store."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from utils.azure_client import create_embedding_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AzureOpenAIEmbedder:
    """Create embeddings through an Azure OpenAI embedding deployment."""

    def __init__(self, batch_size: int = 64) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        self.deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        if not self.deployment:
            raise SystemExit("Set AZURE_OPENAI_EMBEDDING_DEPLOYMENT in .env")
        self.client = create_embedding_client()
        self.batch_size = batch_size

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return embeddings in the same order as *texts*."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            response = self.client.embeddings.create(
                model=self.deployment,
                input=list(texts[start : start + self.batch_size]),
            )
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        return vectors

    def close(self) -> None:
        self.client.close()
