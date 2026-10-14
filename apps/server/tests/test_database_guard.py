import os
import subprocess
import sys
import unittest
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from database_guard import validate_test_database_url


BUSINESS_URL = "postgresql+psycopg://user:secret@localhost:5432/gistai"
TEST_URL = "postgresql+psycopg://user:secret@localhost:5432/gistai_test"


class TestDatabaseGuard(unittest.TestCase):
    def test_accepts_explicit_test_database(self) -> None:
        self.assertEqual(validate_test_database_url(TEST_URL, BUSINESS_URL), TEST_URL)

    def test_rejects_missing_test_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "TEST_DATABASE_URL"):
            validate_test_database_url(None, BUSINESS_URL)

    def test_rejects_malformed_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "无法解析"):
            validate_test_database_url("not-a-url", BUSINESS_URL)

    def test_rejects_business_database(self) -> None:
        with self.assertRaisesRegex(ValueError, "gistai_test"):
            validate_test_database_url(BUSINESS_URL, BUSINESS_URL)

    def test_rejects_same_business_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "业务 DATABASE_URL 相同"):
            validate_test_database_url(TEST_URL, TEST_URL)

    def test_rejects_other_database_with_test_name_fragment(self) -> None:
        with self.assertRaisesRegex(ValueError, "gistai_test"):
            validate_test_database_url(
                "postgresql+psycopg://user:secret@localhost:5432/gistai_test_copy",
                BUSINESS_URL,
            )

    def test_rejects_non_postgresql_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "PostgreSQL"):
            validate_test_database_url("sqlite:///gistai_test", BUSINESS_URL)


def test_pytest_session_connects_to_gistai_test(db_session: Session) -> None:
    assert db_session.execute(text("SELECT current_database()")).scalar_one() == "gistai_test"


@pytest.mark.parametrize(
    ("test_url", "expected_message"),
    [
        (None, "TEST_DATABASE_URL"),
        (BUSINESS_URL, "gistai_test"),
        (TEST_URL, "业务 DATABASE_URL 相同"),
    ],
)
def test_pytest_rejects_unsafe_url_before_collection(
    test_url: str | None,
    expected_message: str,
) -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["DATABASE_URL"] = TEST_URL if expected_message == "业务 DATABASE_URL 相同" else BUSINESS_URL
    if test_url is None:
        env.pop("TEST_DATABASE_URL", None)
    else:
        env["TEST_DATABASE_URL"] = test_url
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/test_tags.py"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode != 0
    assert expected_message in result.stdout + result.stderr


if __name__ == "__main__":
    unittest.main()
