"""LangGraph checkpointer factory.

Returns a PostgresSaver backed by the Neon database so that in-flight HITL
review states survive Streamlit server restarts. Falls back to an in-memory
checkpointer only in local/dev-style environments where that is explicitly
allowed.
"""

import atexit

from settings import MEMORY_DATABASE_URL, REQUIRE_PERSISTENT_CHECKPOINTER
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

# PostgresSaver requires autocommit connections with prepared statements disabled.
_CONNECTION_KWARGS = {"autocommit": True, "prepare_threshold": 0}

_pool = None
_checkpointer = None


def get_checkpointer():
    """Return a process-wide LangGraph checkpointer (lazy singleton)."""
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    if not MEMORY_DATABASE_URL:
        if REQUIRE_PERSISTENT_CHECKPOINTER:
            raise RuntimeError(
                "Persistent LangGraph checkpointing is required, but DATABASE_URL/NEON_DATABASE_URL "
                "is not configured. Set a Postgres connection string before starting the app."
            )
        from langgraph.checkpoint.memory import MemorySaver

        logger.warning(
            "No DATABASE_URL configured; using in-memory checkpointer. "
            "HITL review state will NOT survive server restarts."
        )
        _checkpointer = MemorySaver()
        return _checkpointer

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    _pool = ConnectionPool(
        conninfo=MEMORY_DATABASE_URL,
        min_size=1,
        max_size=5,
        kwargs=_CONNECTION_KWARGS,
        open=True,
    )
    atexit.register(_close_pool)

    saver = PostgresSaver(_pool)
    saver.setup()  # idempotent — creates checkpoint tables if missing
    _checkpointer = saver
    logger.info("PostgresSaver checkpointer initialised against Neon Postgres")
    return _checkpointer


def _close_pool() -> None:
    global _pool, _checkpointer
    if _pool is not None:
        _pool.close()
        _pool = None
        _checkpointer = None
        logger.info("Checkpointer connection pool closed")
