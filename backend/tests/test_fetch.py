from __future__ import annotations

import httpx
import pytest

from sponsor_radar.ingest import RETRY_DELAYS, fetch_json


def _client(statuses: list[int]) -> httpx.Client:
    responses = iter(statuses)
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(next(responses), json={"offers": []})))


def test_rate_limited_fetch_backs_off_then_succeeds():
    slept: list[float] = []

    payload = fetch_json(_client([429, 429, 200]), "greenhouse", "https://example.test/", sleep=slept.append, clock=lambda: 0.0)

    assert payload == {"offers": []}
    assert RETRY_DELAYS[0] in slept and RETRY_DELAYS[1] in slept


def test_persistent_rate_limit_fails_after_bounded_retries():
    with pytest.raises(httpx.HTTPStatusError):
        fetch_json(_client([429] * (len(RETRY_DELAYS) + 1)), "ashby", "https://example.test/", sleep=lambda s: None)
