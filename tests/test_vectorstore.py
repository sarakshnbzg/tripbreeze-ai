"""Tests for infrastructure/rag/vectorstore.py."""

from infrastructure.rag.vectorstore import _chroma_dir_for_provider, _build_vectorstore, retrieve


class TestChromaDirForProvider:
    def test_provider_gets_own_directory(self):
        assert str(_chroma_dir_for_provider("openai")).endswith("chroma_db/openai")
        assert str(_chroma_dir_for_provider("google")).endswith("chroma_db/google")


class TestBuildVectorstore:
    def test_uses_provider_specific_embeddings_and_directory(self, monkeypatch):
        captured = {}

        monkeypatch.setattr(
            "infrastructure.rag.vectorstore.create_embeddings",
            lambda provider: f"embeddings:{provider}",
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore._load_and_split_docs",
            lambda: ["doc1"],
        )

        class FakeChroma:
            @staticmethod
            def from_documents(documents, embedding, persist_directory):
                captured["documents"] = documents
                captured["embedding"] = embedding
                captured["persist_directory"] = persist_directory
                return "vectorstore"

        monkeypatch.setattr("infrastructure.rag.vectorstore.Chroma", FakeChroma)

        result = _build_vectorstore(provider="google", force_rebuild=True)

        assert result == "vectorstore"
        assert captured["documents"] == ["doc1"]
        assert captured["embedding"] == "embeddings:google"
        assert captured["persist_directory"].endswith("chroma_db/google")


class TestRetrieve:
    def test_passes_provider_through_to_vectorstore(self, monkeypatch):
        calls = {}

        class FakeVectorStore:
            def as_retriever(self, search_kwargs):
                calls["search_kwargs"] = search_kwargs
                return "vector_retriever"

        class FakeDoc:
            def __init__(self, page_content):
                self.page_content = page_content

        class FakeEnsembleRetriever:
            def __init__(self, retrievers, weights):
                calls["retrievers"] = retrievers
                calls["weights"] = weights

            def invoke(self, query):
                calls["query"] = query
                return [FakeDoc("chunk 1"), FakeDoc("chunk 2")]

        monkeypatch.setattr(
            "infrastructure.rag.vectorstore._build_vectorstore",
            lambda provider=None, force_rebuild=False: (
                calls.__setitem__("provider", provider) or FakeVectorStore()
            ),
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore._load_and_split_docs",
            lambda: ["doc1", "doc2"],
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore.BM25Retriever.from_documents",
            lambda chunks, k: ("bm25", chunks, k),
        )
        monkeypatch.setattr(
            "infrastructure.rag.vectorstore.EnsembleRetriever",
            FakeEnsembleRetriever,
        )

        result = retrieve("visa query", provider="google", k=2)

        assert calls["provider"] == "google"
        assert calls["search_kwargs"] == {"k": 2}
        assert calls["query"] == "visa query"
        assert result == ["chunk 1", "chunk 2"]
