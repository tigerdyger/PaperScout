import json
from io import BytesIO

import pytest

from paperscout.llm import client
from paperscout.llm.client import (
    DEFAULT_SILICONFLOW_BASE_URL,
    LLMConfig,
    LLMConfigError,
    OpenAICompatibleClient,
    load_llm_config,
)


def test_load_llm_config_reads_siliconflow_env_file(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "SILICONFLOW_API_KEY=fake-key\n"
        "SILICONFLOW_MODEL=Qwen/test-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_MODEL", raising=False)
    monkeypatch.delenv("PAPERSCOUT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PAPERSCOUT_LLM_MODEL", raising=False)

    config = load_llm_config(env_file_paths=[env_path])

    assert config.provider == "siliconflow"
    assert config.api_key == "fake-key"
    assert config.model == "Qwen/test-model"
    assert config.base_url == DEFAULT_SILICONFLOW_BASE_URL


def test_load_llm_config_requires_key_and_model(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_MODEL", raising=False)
    monkeypatch.delenv("PAPERSCOUT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PAPERSCOUT_LLM_MODEL", raising=False)

    with pytest.raises(LLMConfigError, match="API key, model"):
        load_llm_config(env_file_paths=[tmp_path / ".env.local"])


def test_openai_compatible_client_posts_chat_completion(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "id": "resp-1",
                    "model": "Qwen/test-model",
                    "choices": [
                        {"message": {"content": "Generated report."}},
                    ],
                    "usage": {"total_tokens": 123},
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(client, "urlopen", fake_urlopen)
    config = LLMConfig(
        provider="siliconflow",
        api_key="fake-key",
        base_url="https://api.siliconflow.cn/v1",
        model="Qwen/test-model",
        temperature=0.1,
        max_tokens=500,
        timeout_seconds=33,
    )

    response = OpenAICompatibleClient(config).create_chat_completion(
        [{"role": "user", "content": "Explain."}]
    )

    assert captured["url"] == "https://api.siliconflow.cn/v1/chat/completions"
    assert captured["timeout"] == 33
    assert captured["authorization"] == "Bearer fake-key"
    assert captured["body"]["model"] == "Qwen/test-model"
    assert captured["body"]["messages"] == [{"role": "user", "content": "Explain."}]
    assert captured["body"]["stream"] is False
    assert response.content == "Generated report."
    assert response.usage == {"total_tokens": 123}


def test_openai_compatible_client_reports_bad_response(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return BytesIO(json.dumps({"choices": []}).encode("utf-8")).read()

    monkeypatch.setattr(client, "urlopen", lambda request, timeout: FakeResponse())
    config = LLMConfig(
        provider="siliconflow",
        api_key="fake-key",
        base_url="https://api.siliconflow.cn/v1",
        model="Qwen/test-model",
    )

    with pytest.raises(client.LLMError, match="did not contain message content"):
        OpenAICompatibleClient(config).create_chat_completion(
            [{"role": "user", "content": "Explain."}]
        )
