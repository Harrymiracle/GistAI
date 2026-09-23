import logging
import time
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
from pydantic import BaseModel, SecretStr

from app.ai.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
)


OpenAIClientFactory = Callable[..., Any]
logger = logging.getLogger("uvicorn.error")


class OpenAICompatibleClient:
    """只负责调用配置化 OpenAI-compatible Chat Completions API。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        json_schema_enabled: bool = False,
        enable_thinking: bool = True,
        client_factory: OpenAIClientFactory = OpenAI,
    ) -> None:
        self._base_url = base_url.strip()
        self._api_key = api_key.get_secret_value().strip()
        self._model = model.strip()
        self._timeout_seconds = timeout_seconds
        self._json_schema_enabled = json_schema_enabled
        self._enable_thinking = enable_thinking
        self._client_factory = client_factory

    @property
    def model(self) -> str:
        """返回当前配置的模型名，不包含任何凭据。"""

        return self._model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_schema: type[BaseModel] | None = None,
        purpose: str = "unspecified",
        enable_thinking: bool | None = None,
    ) -> str:
        self._ensure_configured()
        effective_thinking = (
            self._enable_thinking
            if enable_thinking is None
            else enable_thinking
        )
        started_at = time.perf_counter()
        outcome = "error"
        client = None
        try:
            try:
                client = self._client_factory(
                    api_key=self._api_key,
                    base_url=self._base_url,
                    timeout=self._timeout_seconds,
                    max_retries=0,
                )
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format=self._response_format(response_schema),
                    extra_body={"enable_thinking": effective_thinking},
                    temperature=0.2,
                )
            except APITimeoutError as exc:
                raise LLMTimeoutError("LLM 请求超时") from exc
            except AuthenticationError as exc:
                raise LLMAuthenticationError("LLM 鉴权失败，请检查本机配置") from exc
            except RateLimitError as exc:
                raise LLMRateLimitError("LLM 服务请求过于频繁，请稍后重试") from exc
            except APIConnectionError as exc:
                raise LLMConnectionError("无法连接 LLM 服务") from exc
            except APIStatusError as exc:
                if exc.status_code >= 500:
                    raise LLMServiceError("LLM 服务暂时不可用") from exc
                raise LLMServiceError(
                    f"LLM 服务返回 HTTP {exc.status_code}"
                ) from exc
            except OpenAIError as exc:
                raise LLMServiceError("LLM 调用失败") from exc
            finally:
                if client is not None:
                    client.close()

            if not response.choices:
                raise LLMResponseError("LLM 返回空结果")
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise LLMResponseError("LLM 返回空结果")
            outcome = "success"
            return content.strip()
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            uses_json_schema = (
                self._json_schema_enabled and response_schema is not None
            )
            logger.info(
                "llm_call purpose=%s model=%s json_schema=%s "
                "thinking=%s duration_ms=%.2f outcome=%s",
                purpose,
                self._model,
                str(uses_json_schema).lower(),
                str(effective_thinking).lower(),
                duration_ms,
                outcome,
            )

    def _response_format(
        self,
        response_schema: type[BaseModel] | None,
    ) -> dict[str, Any]:
        if not self._json_schema_enabled or response_schema is None:
            return {"type": "json_object"}

        schema = response_schema.model_json_schema()
        _normalize_strict_object_schemas(schema)
        return {
            "type": "json_schema",
            "json_schema": {
                "name": response_schema.__name__,
                "strict": True,
                "schema": schema,
            },
        }

    def _ensure_configured(self) -> None:
        missing = []
        if not self._base_url:
            missing.append("LLM_BASE_URL")
        if not self._api_key:
            missing.append("LLM_API_KEY")
        if not self._model:
            missing.append("LLM_MODEL")
        if missing:
            raise LLMConfigurationError(f"LLM 配置缺失：{', '.join(missing)}")


def _normalize_strict_object_schemas(node: Any) -> None:
    """递归规范化 Provider 严格模式所需的对象约束。"""

    if isinstance(node, dict):
        node.pop("default", None)
        properties = node.get("properties")
        if node.get("type") == "object" and isinstance(properties, dict):
            node["required"] = list(properties)
            node["additionalProperties"] = False
        for value in node.values():
            _normalize_strict_object_schemas(value)
    elif isinstance(node, list):
        for value in node:
            _normalize_strict_object_schemas(value)
