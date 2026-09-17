import json

import httpx
import pytest
from openai import OpenAI
from PIL import Image

from llm_change_tool.core.jobs import RunConfig
from llm_change_tool.core.labels import KEYS
from llm_change_tool.providers.base import ProviderFailure
from llm_change_tool.providers.openai import OpenAIProvider


def install_transport(monkeypatch, handler):
    def client(**kwargs):
        assert kwargs["max_retries"] == 0
        assert kwargs["timeout"] == 60
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    monkeypatch.setattr("llm_change_tool.providers.openai.OpenAI", client)


def config():
    return RunConfig(provider="openai", input_price=1, output_price=2)


def test_actual_sdk_payload_and_usage_without_network(monkeypatch):
    prediction = json.dumps(
        dict(labels=dict.fromkeys(KEYS, 0), confidence=0.8, reason="합성", review_required=False)
    )

    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == config().model
        assert body["max_completion_tokens"] == config().max_output_tokens
        schema = body["response_format"]["json_schema"]
        assert schema["strict"] and set(
            schema["schema"]["properties"]["labels"]["required"]
        ) == set(KEYS)
        content = body["messages"][1]["content"]
        assert len(content) == 3
        assert all(
            item["image_url"]["url"].startswith("data:image/jpeg;base64,") for item in content[1:]
        )
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 0,
                "model": config().model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": prediction},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 321, "completion_tokens": 42, "total_tokens": 363},
            },
        )

    install_transport(monkeypatch, handle)
    result = OpenAIProvider("synthetic-only").predict(
        [Image.new("RGB", (32, 32))] * 2, "guideline", config()
    )
    assert result.raw == prediction
    assert result.input_tokens == 321 and result.output_tokens == 42


@pytest.mark.parametrize("status,retry", [(400, False), (429, True), (503, True)])
def test_sdk_status_is_sanitized_and_retryable(monkeypatch, status, retry):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "private response text"}})

    install_transport(monkeypatch, handle)
    with pytest.raises(ProviderFailure) as error:
        OpenAIProvider("synthetic-only").predict(
            [Image.new("RGB", (32, 32))] * 2, "guide", config()
        )
    assert str(error.value) == f"http_{status}"
    assert error.value.retryable is retry
    assert len(calls) == 1
