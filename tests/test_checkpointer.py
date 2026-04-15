"""Tests for infrastructure/persistence/checkpointer.py."""

import sys
from types import SimpleNamespace

from infrastructure.persistence import checkpointer


class DummyMemorySaver:
    pass


class DummyPool:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    def close(self):
        self.closed = True


class DummyPostgresSaver:
    def __init__(self, pool):
        self.pool = pool
        self.setup_called = False

    def setup(self):
        self.setup_called = True


class TestGetCheckpointer:
    def setup_method(self):
        checkpointer._pool = None
        checkpointer._checkpointer = None

    def test_returns_memory_saver_when_database_not_configured(self, monkeypatch):
        monkeypatch.setattr(checkpointer, "MEMORY_DATABASE_URL", "")
        monkeypatch.setitem(
            sys.modules,
            "langgraph.checkpoint.memory",
            SimpleNamespace(MemorySaver=DummyMemorySaver),
        )

        saver = checkpointer.get_checkpointer()

        assert isinstance(saver, DummyMemorySaver)
        assert checkpointer.get_checkpointer() is saver

    def test_returns_postgres_saver_when_database_configured(self, monkeypatch):
        monkeypatch.setattr(checkpointer, "MEMORY_DATABASE_URL", "postgres://example")
        monkeypatch.setitem(
            sys.modules,
            "langgraph.checkpoint.postgres",
            SimpleNamespace(PostgresSaver=DummyPostgresSaver),
        )
        monkeypatch.setitem(
            sys.modules,
            "psycopg_pool",
            SimpleNamespace(ConnectionPool=DummyPool),
        )

        saver = checkpointer.get_checkpointer()

        assert isinstance(saver, DummyPostgresSaver)
        assert saver.setup_called is True
        assert checkpointer._pool.kwargs["conninfo"] == "postgres://example"

    def test_close_pool_resets_singletons(self):
        pool = DummyPool(conninfo="postgres://example")
        checkpointer._pool = pool
        checkpointer._checkpointer = object()

        checkpointer._close_pool()

        assert pool.closed is True
        assert checkpointer._pool is None
        assert checkpointer._checkpointer is None
