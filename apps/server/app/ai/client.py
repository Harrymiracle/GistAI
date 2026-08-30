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


class OpenAICompatibleClient:
    """只负责调用配置化 OpenAI-compatible Chat Completions API。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        client_factory: OpenAIClientFactory = OpenAI,
    ) -> None:
        self._base_url = base_url.strip()
        self._api_key = api_key.get_secret_value().strip()
        self._model = model.strip()
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory

    @property
    def model(self) -> str:
        """返回当前配置的模型名，不包含任何凭据。"""

        return self._model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self._ensure_configured()
        client = None
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
                response_format={"type": "json_object"},
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
            raise LLMServiceError(f"LLM 服务返回 HTTP {exc.status_code}") from exc
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
        return content.strip()

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
