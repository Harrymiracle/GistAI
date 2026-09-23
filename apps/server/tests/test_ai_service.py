import json
import logging
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
from pydantic import BaseModel, SecretStr

from app.agent.schemas import AgentDecision
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
from app.core.config import Settings


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
        self.response_schemas: list[type[BaseModel] | None] = []
        self.purposes: list[str] = []
        self.thinking_overrides: list[bool | None] = []

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_schema: type[BaseModel] | None = None,
        purpose: str = "unspecified",
        enable_thinking: bool | None = None,
    ) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.response_schemas.append(response_schema)
        self.purposes.append(purpose)
        self.thinking_overrides.append(enable_thinking)
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


@pytest.mark.parametrize("configured_value", [True, False])
def test_settings_exposes_agent_decision_thinking_mode(
    configured_value: bool,
) -> None:
    configured = Settings(
        _env_file=None,
        agent_decision_enable_thinking=configured_value,
    )

    assert (
        getattr(configured, "agent_decision_enable_thinking", None)
        is configured_value
    )


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
    assert llm.response_schemas == [None]
    assert llm.purposes == ["article_analysis"]
    assert llm.thinking_overrides == [None]


def test_ai_service_keeps_grounded_answer_on_json_object_path() -> None:
    llm = RawLLMStub('{"answer":"知识库证据支持的回答。"}')

    answer = AIService(llm).generate_grounded_answer("问题", "知识库证据")

    assert answer == "知识库证据支持的回答。"
    assert llm.response_schemas == [None]
    assert llm.purposes == ["rag_answer"]
    assert llm.thinking_overrides == [None]


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
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeOpenAIClient:
    def __init__(self, response) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(response))
        self.closed = False

    def close(self) -> None:
        self.closed = True


def successful_response():
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))]
    )


def test_llm_client_uses_json_object_without_response_schema() -> None:
    fake_client = FakeOpenAIClient(successful_response())
    client = configured_client(
        json_schema_enabled=True,
        client_factory=lambda **_kwargs: fake_client,
    )

    client.complete("system", "user")

    assert fake_client.chat.completions.calls[0]["response_format"] == {
        "type": "json_object"
    }


@pytest.mark.parametrize(
    ("global_thinking", "call_override", "expected_thinking"),
    [
        (True, None, True),
        (True, False, False),
        (False, True, True),
    ],
)
def test_llm_client_resolves_effective_thinking_mode(
    global_thinking: bool,
    call_override: bool | None,
    expected_thinking: bool,
) -> None:
    fake_client = FakeOpenAIClient(successful_response())
    client = configured_client(
        enable_thinking=global_thinking,
        client_factory=lambda **_kwargs: fake_client,
    )

    client.complete("system", "user", enable_thinking=call_override)

    assert fake_client.chat.completions.calls[0]["extra_body"] == {
        "enable_thinking": expected_thinking
    }


def test_llm_client_uses_strict_normalized_agent_decision_schema() -> None:
    fake_client = FakeOpenAIClient(successful_response())
    client = configured_client(
        json_schema_enabled=True,
        enable_thinking=False,
        client_factory=lambda **_kwargs: fake_client,
    )

    client.complete(
        "system",
        "user",
        response_schema=AgentDecision,
        enable_thinking=True,
    )

    response_format = fake_client.chat.completions.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "AgentDecision"
    assert response_format["json_schema"]["strict"] is True
    assert fake_client.chat.completions.calls[0]["extra_body"] == {
        "enable_thinking": True
    }
    provider_schema = response_format["json_schema"]["schema"]
    expected_fields = {
        "evidence_status",
        "reason",
        "next_action",
        "selected_result_indexes",
        "selected_web_result_indexes",
        "selected_article_result_index",
        "selected_web_page_result_index",
        "selected_article_content_indexes",
        "selected_web_page_content_indexes",
    }
    assert provider_schema["additionalProperties"] is False
    assert set(provider_schema["properties"]) == expected_fields
    assert set(provider_schema["required"]) == expected_fields
    assert '"default"' not in json.dumps(provider_schema)


def test_llm_client_uses_json_object_when_json_schema_is_disabled() -> None:
    fake_client = FakeOpenAIClient(successful_response())
    client = configured_client(
        json_schema_enabled=False,
        enable_thinking=False,
        client_factory=lambda **_kwargs: fake_client,
    )

    client.complete("system", "user", response_schema=AgentDecision)

    assert fake_client.chat.completions.calls[0]["response_format"] == {
        "type": "json_object"
    }
    assert fake_client.chat.completions.calls[0]["extra_body"] == {
        "enable_thinking": False
    }


def test_llm_client_logs_duration_and_safe_metadata(
    monkeypatch,
    caplog,
) -> None:
    fake_client = FakeOpenAIClient(successful_response())
    client = configured_client(
        json_schema_enabled=True,
        client_factory=lambda **_kwargs: fake_client,
    )
    times = iter([20.0, 20.125])
    monkeypatch.setattr(
        "app.ai.client.time",
        SimpleNamespace(perf_counter=lambda: next(times)),
        raising=False,
    )
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    client.complete(
        "完整系统 Prompt 不得记录",
        "完整用户消息不得记录",
        response_schema=AgentDecision,
        purpose="agent_decision",
    )

    assert "llm_call purpose=agent_decision" in caplog.text
    assert "model=unit-test-model" in caplog.text
    assert "json_schema=true" in caplog.text
    assert "thinking=true" in caplog.text
    assert "duration_ms=125.00" in caplog.text
    assert "outcome=success" in caplog.text
    assert "unit-test-placeholder" not in caplog.text
    assert "完整系统 Prompt 不得记录" not in caplog.text
    assert "完整用户消息不得记录" not in caplog.text


def test_llm_client_logs_duration_without_swallowing_error(
    monkeypatch,
    caplog,
) -> None:
    def failing_factory(**_kwargs):
        raise APITimeoutError(httpx.Request("POST", "https://llm.example/v1"))

    client = configured_client(
        enable_thinking=False,
        client_factory=failing_factory,
    )
    times = iter([30.0, 30.25])
    monkeypatch.setattr(
        "app.ai.client.time",
        SimpleNamespace(perf_counter=lambda: next(times)),
        raising=False,
    )
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    with pytest.raises(LLMTimeoutError):
        client.complete(
            "敏感系统 Prompt",
            "敏感用户消息",
            purpose="contextualize",
        )

    assert "llm_call purpose=contextualize" in caplog.text
    assert "duration_ms=250.00" in caplog.text
    assert "thinking=false" in caplog.text
    assert "outcome=error" in caplog.text
    assert "敏感系统 Prompt" not in caplog.text
    assert "敏感用户消息" not in caplog.text


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
