"""OpenAI-compatible chat completion client."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_PROVIDER = "siliconflow"
DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.2


class LLMError(RuntimeError):
    """Raised when an LLM request fails."""


class LLMConfigError(ValueError):
    """Raised when LLM configuration is incomplete or invalid."""


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    extra_body: Dict[str, Any] = field(default_factory=dict)

    @property
    def endpoint_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    response_id: Optional[str] = None


class OpenAICompatibleClient:
    """Minimal OpenAI-compatible chat completions client.

    The project intentionally avoids a hard dependency on the OpenAI SDK for now.
    SiliconFlow exposes an OpenAI-compatible HTTP interface, so the standard
    library is enough for this small CLI path.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def create_chat_completion(
        self, messages: Sequence[Mapping[str, str]]
    ) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [dict(message) for message in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }
        payload.update(self.config.extra_body)
        request = Request(
            self.config.endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise LLMError(_http_error_message(exc)) from exc
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            choice = response_data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM response did not contain message content.") from exc
        if not str(content).strip():
            raise LLMError("LLM response content was empty.")

        return LLMResponse(
            content=str(content).strip(),
            model=str(response_data.get("model") or self.config.model),
            usage=dict(response_data.get("usage") or {}),
            response_id=response_data.get("id"),
        )


def load_llm_config(
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    env_file_paths: Optional[Sequence[Path]] = None,
) -> LLMConfig:
    env_values = _load_env_files(env_file_paths or [Path(".env.local"), Path(".env")])
    merged = {**env_values, **os.environ}
    resolved_provider = _clean(provider) or _clean(
        merged.get("PAPERSCOUT_LLM_PROVIDER")
    ) or DEFAULT_PROVIDER
    resolved_provider = resolved_provider.lower()
    resolved_api_key = _clean(api_key) or _first_value(
        merged,
        _provider_env_names(resolved_provider, "API_KEY")
        + ["PAPERSCOUT_LLM_API_KEY", "OPENAI_API_KEY"],
    )
    resolved_base_url = _clean(base_url) or _first_value(
        merged,
        _provider_env_names(resolved_provider, "BASE_URL")
        + ["PAPERSCOUT_LLM_BASE_URL", "OPENAI_BASE_URL"],
    )
    resolved_model = _clean(model) or _first_value(
        merged,
        _provider_env_names(resolved_provider, "MODEL")
        + ["PAPERSCOUT_LLM_MODEL", "OPENAI_MODEL"],
    )

    if not resolved_base_url and resolved_provider == "siliconflow":
        resolved_base_url = DEFAULT_SILICONFLOW_BASE_URL

    missing = []
    if not resolved_api_key:
        missing.append("API key")
    if not resolved_base_url:
        missing.append("base URL")
    if not resolved_model:
        missing.append("model")
    if missing:
        raise LLMConfigError(
            "LLM configuration is incomplete: "
            + ", ".join(missing)
            + ". "
            + _configuration_hint(missing, resolved_provider)
        )
    if max_tokens <= 0:
        raise LLMConfigError("max_tokens must be positive.")
    if timeout_seconds <= 0:
        raise LLMConfigError("timeout_seconds must be positive.")

    return LLMConfig(
        provider=resolved_provider,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    )


def _http_error_message(exc: HTTPError) -> str:
    detail = ""
    try:
        detail = exc.read().decode("utf-8", errors="replace")
    except OSError:
        detail = ""
    if len(detail) > 500:
        detail = detail[:497].rstrip() + "..."
    return f"LLM request failed with HTTP {exc.code}: {detail or exc.reason}"


def _configuration_hint(missing: Sequence[str], provider: str) -> str:
    prefix = provider.upper().replace("-", "_")
    hints = []
    if "API key" in missing:
        hints.append(f"set {prefix}_API_KEY in .env.local or the environment")
    if "model" in missing:
        hints.append(f"set {prefix}_MODEL or pass --llm-model")
    if "base URL" in missing:
        hints.append(f"set {prefix}_BASE_URL or PAPERSCOUT_LLM_BASE_URL")
    return "; ".join(hints) + "."


def _load_env_files(paths: Sequence[Path]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for path in paths:
        path = Path(path)
        if not path.exists() or not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            key, value = _parse_env_line(line)
            if key:
                values[key] = value
    return values


def _parse_env_line(line: str) -> tuple[Optional[str], str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None, ""
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    key, value = stripped.split("=", maxsplit=1)
    key = key.strip()
    if not key:
        return None, ""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _provider_env_names(provider: str, suffix: str) -> List[str]:
    normalized = provider.upper().replace("-", "_")
    return [f"{normalized}_{suffix}"]


def _first_value(values: Mapping[str, str], names: Sequence[str]) -> Optional[str]:
    for name in names:
        value = _clean(values.get(name))
        if value:
            return value
    return None


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
