import math
from collections.abc import Callable
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import SecretStr

from app.embedding.errors import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingConnectionError,
    EmbeddingRateLimitError,
    EmbeddingResponseError,
    EmbeddingServiceError,
    EmbeddingTimeoutError,
)


OpenAIClientFactory = Callable[..., Any]
VECTOR_DIMENSION = 1024


class OpenAICompatibleEmbeddingClient:
    """只负责调用配置化 OpenAI-compatible Embeddings API。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        dimension: int,
        timeout_seconds: float,
        client_factory: OpenAIClientFactory = OpenAI,
    ) -> None:
        self._base_url = base_url.strip()
        self._api_key = api_key.get_secret_value().strip()
        self._model = model.strip()
        self._dimension = dimension
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure_configured()
        if not texts:
            return []

        client = None
        try:
            client = self._client_factory(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
            response = client.embeddings.create(
                model=self._model,
                input=texts,
                dimensions=self._dimension,
                encoding_format="float",
            )
        except APITimeoutError as exc:
            raise EmbeddingTimeoutError("Embedding 请求超时") from exc
        except AuthenticationError as exc:
            raise EmbeddingAuthenticationError(
                "Embedding 鉴权失败，请检查本机配置"
            ) from exc
        except RateLimitError as exc:
            raise EmbeddingRateLimitError(
                "Embedding 服务请求过于频繁，请稍后重试"
            ) from exc
        except APIConnectionError as exc:
            raise EmbeddingConnectionError("无法连接 Embedding 服务") from exc
        except APIStatusError as exc:
            if exc.status_code >= 500:
                raise EmbeddingServiceError("Embedding 服务暂时不可用") from exc
            raise EmbeddingServiceError(
                f"Embedding 服务返回 HTTP {exc.status_code}"
            ) from exc
        except OpenAIError as exc:
            raise EmbeddingServiceError("Embedding 调用失败") from exc
        finally:
            if client is not None:
                client.close()

        if len(response.data) != len(texts):
            raise EmbeddingResponseError("Embedding 返回数量与输入不一致")

        ordered_data = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in ordered_data] != list(range(len(texts))):
            raise EmbeddingResponseError("Embedding 返回顺序索引无效")

        vectors: list[list[float]] = []
        for item in ordered_data:
            vector = item.embedding
            if not isinstance(vector, list) or len(vector) != self._dimension:
                raise EmbeddingResponseError(
                    f"Embedding 向量维度必须为 {self._dimension}"
                )
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in vector
            ):
                raise EmbeddingResponseError("Embedding 向量包含非法数值")
            vectors.append([float(value) for value in vector])
        return vectors

    def _ensure_configured(self) -> None:
        missing = []
        if not self._base_url:
            missing.append("EMBEDDING_BASE_URL")
        if not self._api_key:
            missing.append("EMBEDDING_API_KEY")
        if not self._model:
            missing.append("EMBEDDING_MODEL")
        if missing:
            raise EmbeddingConfigurationError(
                f"Embedding 配置缺失：{', '.join(missing)}"
            )
        if not self._api_key.isascii():
            raise EmbeddingConfigurationError("EMBEDDING_API_KEY 格式无效")
        if self._dimension != VECTOR_DIMENSION:
            raise EmbeddingConfigurationError(
                f"EMBEDDING_DIMENSION 必须为 {VECTOR_DIMENSION}"
            )
