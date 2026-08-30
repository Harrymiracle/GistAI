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

from app.ai.client import OpenAICompatibleClient
from app.ai.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
)
from app.ai.service import AIService


VALID_JSON = """{
  "one_sentence_summary": "文章说明了结构化 AI 输出的重要性。",
  "key_points": ["只依据正文", "输出必须校验"],
  "detailed_summary": "文章讨论了如何安全地生成和验证结构化摘要。",
  "tags": ["AI", "结构化输出", "AI"]
}"""


class RawLLMStub:
    def __init__(self, response: str) -> None:
        self.response = response
        self.system_prompt = ""
        self.user_prompt = ""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.response


def configured_client(**overrides) -> OpenAICompatibleClient:
    values = {
        "base_url": "https://llm.example/v1",
        "api_key": SecretStr("unit-test-placeholder"),
        "model": "unit-test-model",
        "timeout_seconds": 1,
    }
    values.update(overrides)
    return OpenAICompatibleClient(**values)


def test_ai_service_builds_guarded_prompt_and_validates_result() -> None:
    llm = RawLLMStub(VALID_JSON)
    service = AIService(llm)

    result = service.generate_article_result("这是待分析的文章正文。")

    assert result.one_sentence_summary == "文章说明了结构化 AI 输出的重要性。"
    assert result.key_points == ["只依据正文", "输出必须校验"]
    assert result.tags == ["AI", "结构化输出"]
    assert "只能依据" in llm.system_prompt
    assert "不得联网" in llm.system_prompt
    assert "默认使用简体中文" in llm.system_prompt
    assert "这是待分析的文章正文。" in llm.user_prompt


@pytest.mark.parametrize(
    "raw_response",
    [
        "",
        "not-json",
        "{}",
        '{"one_sentence_summary":"","key_points":[],"detailed_summary":"","tags":[]}',
        '{"one_sentence_summary":"摘要","key_points":"错误类型","detailed_summary":"详情","tags":["AI"]}',
        '{"one_sentence_summary":"摘要","key_points":["观点"],"detailed_summary":"详情","tags":["AI"],"extra":true}',
    ],
)
def test_ai_service_rejects_invalid_structured_output(raw_response: str) -> None:
    with pytest.raises(LLMResponseError, match="结构化结果无效"):
        AIService(RawLLMStub(raw_response)).generate_article_result("有效正文")


@pytest.mark.parametrize(
    ("base_url", "api_key", "model", "missing_name"),
    [
        ("", SecretStr("unit-test-placeholder"), "model", "LLM_BASE_URL"),
        ("https://llm.example/v1", SecretStr(""), "model", "LLM_API_KEY"),
        ("https://llm.example/v1", SecretStr("unit-test-placeholder"), "", "LLM_MODEL"),
    ],
)
def test_llm_client_reports_missing_configuration(
    base_url: str,
    api_key: SecretStr,
    model: str,
    missing_name: str,
) -> None:
    client = configured_client(base_url=base_url, api_key=api_key, model=model)

    with pytest.raises(LLMConfigurationError, match=missing_name):
        client.complete("system", "user")


def openai_http_error(error_type, status_code: int):
    request = httpx.Request("POST", "https://llm.example/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type("safe test error", response=response, body=None)


@pytest.mark.parametrize(
    ("raised_error", "expected_error"),
    [
        (APITimeoutError(httpx.Request("POST", "https://llm.example/v1")), LLMTimeoutError),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://llm.example/v1")
            ),
            LLMConnectionError,
        ),
        (openai_http_error(AuthenticationError, 401), LLMAuthenticationError),
        (openai_http_error(RateLimitError, 429), LLMRateLimitError),
        (openai_http_error(InternalServerError, 500), LLMServiceError),
    ],
)
def test_llm_client_maps_provider_errors_to_safe_errors(
    raised_error: Exception,
    expected_error: type[Exception],
) -> None:
    def failing_factory(**_kwargs):
        raise raised_error

    client = configured_client(client_factory=failing_factory)

    with pytest.raises(expected_error) as exc_info:
        client.complete("system", "user")
    assert "unit-test-placeholder" not in str(exc_info.value)
    assert "Traceback" not in str(exc_info.value)


class FakeCompletions:
    def __init__(self, response) -> None:
        self.response = response

    def create(self, **_kwargs):
        return self.response


class FakeOpenAIClient:
    def __init__(self, response) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(response))
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" "))]),
    ],
)
def test_llm_client_rejects_empty_response_and_closes_client(response) -> None:
    fake_client = FakeOpenAIClient(response)
    client = configured_client(client_factory=lambda **_kwargs: fake_client)

    with pytest.raises(LLMResponseError, match="空结果"):
        client.complete("system", "user")
    assert fake_client.closed is True
