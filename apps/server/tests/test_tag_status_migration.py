from uuid import uuid4

import pytest
from sqlalchemy import String, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def test_tag_status_column_default_and_check(db_session: Session) -> None:
    inspector = inspect(db_session.connection())
    columns = {column["name"]: column for column in inspector.get_columns("tags")}

    assert "status" in columns
    assert isinstance(columns["status"]["type"], String)
    assert columns["status"]["type"].length == 16
    assert columns["status"]["nullable"] is False
    assert "active" in str(columns["status"]["default"])
    assert "ck_tags_status" in {
        constraint["name"] for constraint in inspector.get_check_constraints("tags")
    }


def test_tag_status_default_and_allowed_values(db_session: Session) -> None:
    name_prefix = f"status-contract-{uuid4().hex}"
    default_status = db_session.execute(
        text("INSERT INTO tags (name) VALUES (:name) RETURNING status"),
        {"name": f"{name_prefix}-default"},
    ).scalar_one()
    active_status = db_session.execute(
        text("INSERT INTO tags (name, status) VALUES (:name, :status) RETURNING status"),
        {"name": f"{name_prefix}-active", "status": "active"},
    ).scalar_one()
    pending_status = db_session.execute(
        text("INSERT INTO tags (name, status) VALUES (:name, :status) RETURNING status"),
        {"name": f"{name_prefix}-pending", "status": "pending"},
    ).scalar_one()

    assert (default_status, active_status, pending_status) == (
        "active",
        "active",
        "pending",
    )


@pytest.mark.parametrize("invalid_status", ["unknown", "", "ACTIVE"])
def test_tag_status_rejects_invalid_values(
    db_session: Session,
    invalid_status: str,
) -> None:
    name = f"status-invalid-{uuid4().hex}"
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(
            text("INSERT INTO tags (name, status) VALUES (:name, :status)"),
            {"name": name, "status": invalid_status},
        )

    assert db_session.scalar(
        text("SELECT count(*) FROM tags WHERE name = :name"), {"name": name}
    ) == 0


def test_tag_status_test_write_can_roll_back(db_session: Session) -> None:
    name = f"status-rollback-{uuid4().hex}"
    savepoint = db_session.begin_nested()
    db_session.execute(
        text("INSERT INTO tags (name, status) VALUES (:name, 'active')"),
        {"name": name},
    )
    savepoint.rollback()

    assert db_session.scalar(
        text("SELECT count(*) FROM tags WHERE name = :name"), {"name": name}
    ) == 0
