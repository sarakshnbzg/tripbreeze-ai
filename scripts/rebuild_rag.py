"""Rebuild the local ChromaDB knowledge base from markdown sources."""

import sys
from pathlib import Path

# Ensure project root is on the Python path when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.rag.vectorstore import _build_vectorstore


def main() -> None:
    """Force a rebuild of the persisted RAG vector store."""
    provider = sys.argv[1] if len(sys.argv) > 1 else None
    _build_vectorstore(provider=provider, force_rebuild=True)
    suffix = f" for provider `{provider}`" if provider else ""
    print(f"RAG knowledge base rebuilt in chroma_db/{suffix}")


if __name__ == "__main__":
    main()
