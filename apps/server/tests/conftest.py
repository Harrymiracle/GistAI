from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_crawler_service, get_db
from app.crawler.extractor import ExtractedArticle
from app.db.session import engine
from app.main import app


class SuccessfulCrawlerStub:
    """为 CRUD 回归测试提供稳定且不访问公网的抓取结果。"""

    def fetch_article(self, _url: str) -> ExtractedArticle:
        return ExtractedArticle(
            clean_content="用于 CRUD 回归测试的正文。" * 30,
            title="抓取标题",
            source_name="测试站点",
        )


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """在外层事务中提供真实 PostgreSQL 会话，测试结束后整体回滚。"""

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """让 API 测试复用受事务保护的数据库会话。"""

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_crawler_service] = SuccessfulCrawlerStub
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
