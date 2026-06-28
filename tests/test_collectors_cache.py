import json

import pytest

from paperscout.collectors.cache import (
    CachedHttpClient,
    HttpRequestError,
    HttpResponse,
    build_url,
)


def test_cached_http_client_caches_response(tmp_path) -> None:
    calls = []

    def fake_transport(url, headers, timeout):
        calls.append((url, headers, timeout))
        return HttpResponse(status=200, body='{"ok": true}', headers={"x-test": "1"})

    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        transport=fake_transport,
    )

    first = client.get_json(
        "https://example.org/api",
        params={"q": "chem ai", "limit": 2},
        headers={"Accept": "application/json"},
        cache_key_prefix="example",
    )
    second = client.get_json(
        "https://example.org/api",
        params={"q": "chem ai", "limit": 2},
        headers={"Accept": "application/json"},
        cache_key_prefix="example",
    )

    assert first == {"ok": True}
    assert second == {"ok": True}
    assert len(calls) == 1
    assert "q=chem+ai" in calls[0][0]
    assert calls[0][1] == {"Accept": "application/json"}


def test_cached_http_client_refresh_fetches_again(tmp_path) -> None:
    calls = []

    def fake_transport(url, headers, timeout):
        calls.append(url)
        return HttpResponse(status=200, body=json.dumps({"count": len(calls)}))

    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        transport=fake_transport,
    )

    assert client.get_json("https://example.org/api") == {"count": 1}
    assert client.get_json("https://example.org/api", refresh=True) == {"count": 2}
    assert len(calls) == 2


def test_cached_http_client_rejects_error_status(tmp_path) -> None:
    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        max_retries=0,
        transport=lambda url, headers, timeout: HttpResponse(status=429, body="rate"),
    )

    with pytest.raises(HttpRequestError, match="429"):
        client.get_text("https://example.org/rate-limited")


def test_cached_http_client_retries_retryable_status(tmp_path) -> None:
    responses = [
        HttpResponse(status=503, body="busy"),
        HttpResponse(status=200, body='{"ok": true}'),
    ]

    def fake_transport(url, headers, timeout):
        return responses.pop(0)

    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        retry_backoff_seconds=0,
        transport=fake_transport,
    )

    assert client.get_json("https://example.org/flaky") == {"ok": True}
    assert responses == []


def test_cached_http_client_does_not_retry_non_retryable_status(tmp_path) -> None:
    calls = []

    def fake_transport(url, headers, timeout):
        calls.append(url)
        return HttpResponse(status=404, body="missing")

    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        retry_backoff_seconds=0,
        transport=fake_transport,
    )

    with pytest.raises(HttpRequestError, match="404"):
        client.get_text("https://example.org/missing")

    assert len(calls) == 1


def test_build_url_keeps_existing_query() -> None:
    assert (
        build_url("https://example.org/api?existing=1", params={"q": "ai"})
        == "https://example.org/api?existing=1&q=ai"
    )
