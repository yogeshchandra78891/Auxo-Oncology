import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import httpx
import truststore
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
from openai import AzureOpenAI


def normalize_endpoint(endpoint: str) -> str:
    """Return the Azure resource root, not a deployment-specific API URL.

    AzureOpenAI selects the deployment from the ``model`` argument. Supplying an
    endpoint containing ``/openai/deployments/<name>`` pins every request to that
    deployment, causing embeddings requests to be handled as chat completions.
    """
    parsed = urlsplit(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit("AZURE_OPENAI_ENDPOINT must be a full Azure resource URL.")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def create_client() -> tuple[AzureOpenAI, str]:
    load_dotenv(PROJECT_ROOT / ".env")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
    if not all((endpoint, api_key, deployment)):
        raise SystemExit("Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT in .env")
    ca_bundle = os.getenv("AZURE_OPENAI_CA_BUNDLE")
    if ca_bundle and not Path(ca_bundle).expanduser().is_file():
        raise SystemExit(f"AZURE_OPENAI_CA_BUNDLE does not exist: {ca_bundle}")
    verify: ssl.SSLContext | str = str(Path(ca_bundle).expanduser()) if ca_bundle else truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return AzureOpenAI(azure_endpoint=normalize_endpoint(endpoint), api_key=api_key, api_version=api_version,
                       http_client=httpx.Client(verify=verify, trust_env=True, timeout=90.0)), deployment

