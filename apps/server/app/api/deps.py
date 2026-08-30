from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


DEFAULT_USER_ID = 1


def get_db() -> Generator[Session, None, None]:
    """为单次请求提供数据库会话。"""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user_id() -> int:
    """返回 V1 默认用户，后续可替换为认证结果。"""

    return DEFAULT_USER_ID
