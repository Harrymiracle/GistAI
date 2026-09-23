from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    RateLimitError,
)
from pydantic import SecretStr

from app.embedding.client import OpenAICompatibleEmbeddingClient
from app.embedding.errors import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingConnectionError,
    EmbeddingRateLimitError,
    EmbeddingResponseError,
    EmbeddingServiceError,
    EmbeddingTimeoutError,
)


def configured_client(**overrides) -> OpenAICompatibleEmbeddingClient:
    values = {
        "base_url": "https://embedding.example/v1",
        "api_key": SecretStr("unit-test-placeholder"),
        "model": "unit-test-embedding-model",
        "dimension": 1024,
        "timeout_seconds": 1,
    }
    values.update(overrides)
    return OpenAICompatibleEmbeddingClient(**values)


class FakeEmbeddings:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class FakeOpenAIClient:
    def __init__(self, response) -> None:
        self.embeddings = FakeEmbeddings(response)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_embedding_client_validates_1024_dimensions_and_restores_index_order() -> None:
    response = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[0.2] * 1024),
            SimpleNamespace(index=0, embedding=[0.1] * 1024),
        ]
    )
    fake_client = FakeOpenAIClient(response)
    client = configured_client(client_factory=lambda **_kwargs: fake_client)

    vectors = client.embed(["第一块", "第二块"])

    assert len(vectors) == 2
    assert all(len(vector) == 1024 for vector in vectors)
    assert vectors[0][0] == 0.1
    assert vectors[1][0] == 0.2
    assert fake_client.embeddings.kwargs["dimensions"] == 1024
    assert fake_client.closed is True


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1] * 1023)]),
        SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[float("nan")] * 1024)]),
        SimpleNamespace(data=[SimpleNamespace(index=2, embedding=[0.1] * 1024)]),
    ],
)
def test_embedding_client_rejects_invalid_provider_results(response) -> None:
    fake_client = FakeOpenAIClient(response)
    client = configured_client(client_factory=lambda **_kwargs: fake_client)

    with pytest.raises(EmbeddingResponseError):
        client.embed(["正文"])
    assert fake_client.closed is True


@pytest.mark.parametrize(
    ("base_url", "api_key", "model", "missing_name"),
    [
        ("", SecretStr("unit-test-placeholder"), "model", "EMBEDDING_BASE_URL"),
        ("https://embedding.example/v1", SecretStr(""), "model", "EMBEDDING_API_KEY"),
        (
            "https://embedding.example/v1",
            SecretStr("unit-test-placeholder"),
            "",
            "EMBEDDING_MODEL",
        ),
    ],
)
def test_embedding_client_reports_missing_configuration(
    base_url: str,
    api_key: SecretStr,
    model: str,
    missing_name: str,
) -> None:
    client = configured_client(base_url=base_url, api_key=api_key, model=model)

    with pytest.raises(EmbeddingConfigurationError, match=missing_name):
        client.embed(["正文"])


def test_embedding_client_rejects_dimension_incompatible_with_database() -> None:
    client = configured_client(dimension=768)

    with pytest.raises(EmbeddingConfigurationError, match="必须为 1024"):
        client.embed(["正文"])


def test_embedding_client_rejects_non_ascii_api_key_safely() -> None:
    client = configured_client(api_key=SecretStr("无效占位值"))

    with pytest.raises(EmbeddingConfigurationError, match="API_KEY 格式无效") as exc_info:
        client.embed(["正文"])
    assert "无效占位值" not in str(exc_info.value)


def openai_http_error(error_type, status_code: int):
    request = httpx.Request("POST", "https://embedding.example/v1/embeddings")
    response = httpx.Response(status_code, request=request)
    return error_type("safe test error", response=response, body=None)


@pytest.mark.parametrize(
    ("raised_error", "expected_error"),
    [
        (
            APITimeoutError(
                httpx.Request("POST", "https://embedding.example/v1/embeddings")
            ),
            EmbeddingTimeoutError,
        ),
        (
            APIConnectionError(
                request=httpx.Request(
                    "POST", "https://embedding.example/v1/embeddings"
                )
            ),
            EmbeddingConnectionError,
        ),
        (
            openai_http_error(AuthenticationError, 401),
            EmbeddingAuthenticationError,
        ),
        (openai_http_error(RateLimitError, 429), EmbeddingRateLimitError),
        (openai_http_error(InternalServerError, 500), EmbeddingServiceError),
    ],
)
def test_embedding_client_maps_provider_errors_to_safe_errors(
    raised_error: Exception,
    expected_error: type[Exception],
) -> None:
    def failing_factory(**_kwargs):
        raise raised_error

    client = configured_client(client_factory=failing_factory)

    with pytest.raises(expected_error) as exc_info:
        client.embed(["正文"])
    assert "unit-test-placeholder" not in str(exc_info.value)
    assert "Traceback" not in str(exc_info.value)
