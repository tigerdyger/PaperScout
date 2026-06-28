"""Small cached HTTP client for metadata collectors."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class HttpResponse:
    """Minimal HTTP response object used by the cached client."""

    status: int
    body: str
    headers: Dict[str, str] = field(default_factory=dict)


Transport = Callable[[str, Mapping[str, str], float], HttpResponse]


class HttpRequestError(RuntimeError):
    """Raised when an HTTP request fails before a usable response is cached."""


@dataclass
class CachedHttpClient:
    """Fetch text/JSON through a filesystem cache.

    The cache stores raw response bodies plus lightweight metadata. Tests can
    inject a fake transport so collector logic stays deterministic and offline.
    """

    cache_dir: Path = Path("data/cache/http")
    timeout_seconds: float = 30.0
    min_interval_seconds: float = 0.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    transport: Optional[Transport] = None
    _last_request_at: Optional[float] = field(default=None, init=False, repr=False)

    def get_text(
        self,
        url: str,
        *,
        params: Optional[Mapping[str, object]] = None,
        headers: Optional[Mapping[str, str]] = None,
        cache_key_prefix: str = "http",
        refresh: bool = False,
    ) -> str:
        request_url = build_url(url, params=params)
        cache_path = self._cache_path(cache_key_prefix, request_url)
        if cache_path.exists() and not refresh:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return str(cached["body"])

        transport = self.transport or default_transport
        response = self._fetch_with_retries(
            transport=transport,
            request_url=request_url,
            headers=dict(headers or {}),
        )

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "url": request_url,
                    "status": response.status,
                    "headers": response.headers,
                    "body": response.body,
                    "fetched_at": int(time.time()),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return response.body

    def _fetch_with_retries(
        self,
        *,
        transport: Transport,
        request_url: str,
        headers: Mapping[str, str],
    ) -> HttpResponse:
        last_error: Optional[HttpRequestError] = None
        max_attempts = max(0, int(self.max_retries)) + 1
        for attempt in range(max_attempts):
            self._respect_min_interval()
            try:
                response = transport(
                    request_url,
                    dict(headers),
                    self.timeout_seconds,
                )
            except HttpRequestError as exc:
                last_error = exc
                if attempt + 1 >= max_attempts:
                    raise
                self._sleep_before_retry(attempt)
                continue

            if 200 <= response.status < 300:
                return response

            last_error = HttpRequestError(
                f"GET {request_url} failed with status {response.status}"
            )
            if (
                not _is_retryable_status(response.status)
                or attempt + 1 >= max_attempts
            ):
                raise last_error
            self._sleep_before_retry(attempt)

        if last_error is not None:
            raise last_error
        raise HttpRequestError(f"GET {request_url} failed before receiving a response")

    def get_json(
        self,
        url: str,
        *,
        params: Optional[Mapping[str, object]] = None,
        headers: Optional[Mapping[str, str]] = None,
        cache_key_prefix: str = "http",
        refresh: bool = False,
    ) -> Mapping[str, object]:
        text = self.get_text(
            url,
            params=params,
            headers=headers,
            cache_key_prefix=cache_key_prefix,
            refresh=refresh,
        )
        value = json.loads(text)
        if not isinstance(value, Mapping):
            raise ValueError(f"GET {url} did not return a JSON object")
        return value

    def _cache_path(self, prefix: str, request_url: str) -> Path:
        digest = hashlib.sha256(request_url.encode("utf-8")).hexdigest()
        safe_prefix = "".join(
            character if character.isalnum() or character in {"-", "_"} else "_"
            for character in prefix
        )
        return self.cache_dir / f"{safe_prefix}-{digest}.json"

    def _respect_min_interval(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        now = time.monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
        self._last_request_at = time.monotonic()

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        time.sleep(self.retry_backoff_seconds * (2**attempt))


def build_url(url: str, *, params: Optional[Mapping[str, object]] = None) -> str:
    if not params:
        return url
    query = urlencode(
        {
            key: value
            for key, value in params.items()
            if value is not None
        }
    )
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def default_transport(url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return HttpResponse(
                status=response.status,
                body=body,
                headers=dict(response.headers.items()),
            )
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResponse(
            status=exc.code,
            body=body,
            headers=dict(exc.headers.items()),
        )
    except (OSError, URLError) as exc:
        raise HttpRequestError(f"GET {url} failed: {exc}") from exc


def _is_retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status < 600
