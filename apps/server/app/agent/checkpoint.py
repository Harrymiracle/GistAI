from collections.abc import Generator
from contextlib import contextmanager
import logging

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


CHECKPOINT_POOL_MIN_SIZE = 1
CHECKPOINT_POOL_MAX_SIZE = 5
CHECKPOINT_POOL_OPEN_TIMEOUT_SECONDS = 10.0
CHECKPOINT_SETUP_ADVISORY_LOCK_ID = 7_184_901_335_201


class _SafePoolLogFilter(logging.Filter):
    """移除 psycopg pool 日志中可能包含的连接信息。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = "Agent checkpoint connection pool event"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


class AgentCheckpointStartupError(RuntimeError):
    """PostgreSQL Checkpointer 无法安全启动。"""


def to_psycopg_connection_string(database_url: str) -> str:
    """将项目 SQLAlchemy URL 转换为 psycopg 可识别的连接字符串。"""

    sqlalchemy_prefix = "postgresql+psycopg://"
    if database_url.startswith(sqlalchemy_prefix):
        return f"postgresql://{database_url[len(sqlalchemy_prefix):]}"
    if database_url.startswith(("postgresql://", "postgres://")):
        return database_url
    raise ValueError("Agent checkpoint 仅支持 PostgreSQL DATABASE_URL")


@contextmanager
def postgres_checkpointer(
    database_url: str,
) -> Generator[PostgresSaver, None, None]:
    """建立应用级连接池，并交由官方 Checkpointer 管理持久化表。"""

    pool_logger = logging.getLogger("psycopg.pool")
    safe_log_filter = _SafePoolLogFilter()
    pool_logger.addFilter(safe_log_filter)
    pool: ConnectionPool | None = None
    try:
        connection_string = to_psycopg_connection_string(database_url)
        pool = ConnectionPool(
            conninfo=connection_string,
            min_size=CHECKPOINT_POOL_MIN_SIZE,
            max_size=CHECKPOINT_POOL_MAX_SIZE,
            open=False,
            timeout=CHECKPOINT_POOL_OPEN_TIMEOUT_SECONDS,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        pool.open(wait=True, timeout=CHECKPOINT_POOL_OPEN_TIMEOUT_SECONDS)
        saver = PostgresSaver(
            pool,
            serde=JsonPlusSerializer(allowed_msgpack_modules=None),
        )
        with pool.connection() as connection:
            connection.execute(
                "SELECT pg_advisory_lock(%s)",
                (CHECKPOINT_SETUP_ADVISORY_LOCK_ID,),
            )
            try:
                saver.setup()
            finally:
                connection.execute(
                    "SELECT pg_advisory_unlock(%s)",
                    (CHECKPOINT_SETUP_ADVISORY_LOCK_ID,),
                )
    except Exception:
        if pool is not None:
            pool.close()
        pool_logger.removeFilter(safe_log_filter)
        raise AgentCheckpointStartupError(
            "Agent checkpoint 初始化失败"
        ) from None

    try:
        yield saver
    finally:
        pool.close()
        pool_logger.removeFilter(safe_log_filter)
