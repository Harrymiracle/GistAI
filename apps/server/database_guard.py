import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = "postgresql+psycopg://gistai:gistai@localhost:5432/gistai"


def validate_test_database_url(test_database_url: str | None, business_database_url: str) -> str:
    """确认 pytest 目标是显式配置的独立 PostgreSQL 测试库。"""

    if not test_database_url or not test_database_url.strip():
        raise ValueError("缺少 TEST_DATABASE_URL，pytest 已停止")

    try:
        test_url = make_url(test_database_url)
        business_url = make_url(business_database_url)
    except (ArgumentError, TypeError, ValueError) as exc:
        raise ValueError("TEST_DATABASE_URL 或业务 DATABASE_URL 无法解析") from exc

    if test_url.get_backend_name() != "postgresql":
        raise ValueError("TEST_DATABASE_URL 必须使用 PostgreSQL")
    if test_url.database != "gistai_test":
        raise ValueError("TEST_DATABASE_URL 的数据库名必须精确为 gistai_test")
    if test_url == business_url:
        raise ValueError("TEST_DATABASE_URL 与业务 DATABASE_URL 相同，pytest 已停止")

    return test_database_url


def configure_pytest_database() -> None:
    """在导入应用配置和数据库引擎前切换 pytest 的数据库目标。"""

    env_values = dotenv_values(PROJECT_ROOT / ".env")
    business_database_url = (
        os.environ.get("DATABASE_URL")
        or env_values.get("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )
    test_database_url = validate_test_database_url(
        os.environ.get("TEST_DATABASE_URL"), business_database_url
    )
    os.environ["DATABASE_URL"] = test_database_url
