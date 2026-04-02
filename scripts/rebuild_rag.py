"""Rebuild the local ChromaDB knowledge base from markdown sources."""

import sys
from pathlib import Path

# Ensure project root is on the Python path when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.rag.vectorstore import _build_vectorstore


def main() -> None:
    """Force a rebuild of the persisted RAG vector store."""
    _build_vectorstore(force_rebuild=True)
    print("RAG knowledge base rebuilt in chroma_db/")


if __name__ == "__main__":
    main()
