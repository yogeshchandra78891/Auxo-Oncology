from Bio import Entrez
from pathlib import Path
# Entrez.email = "your_email@example.com"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "top10_pubmed_abstracts.txt"

def fetch_top_pubmed_abstracts(topic, max_results=10, output=DEFAULT_OUTPUT):
    search_handle = Entrez.esearch(
        db="pubmed",
        term=f"{topic} AND free full text[Filter]",
        retmax=max_results,
        sort="relevance",
    )
    search_results = Entrez.read(search_handle)
    search_handle.close()

    article_ids = search_results["IdList"]

    if not article_ids:
        print("No articles found.")
        return

    # Fetch only abstracts
    fetch_handle = Entrez.efetch(
        db="pubmed",
        id=article_ids,
        rettype="abstract",
        retmode="text",
    )
    abstract_data = fetch_handle.read()
    fetch_handle.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as file:
        file.write(abstract_data)

    print(
        f"Fetched {len(article_ids)} abstracts "
        f"and saved to {output}"
    )

fetch_top_pubmed_abstracts("lung cancer", max_results=10)