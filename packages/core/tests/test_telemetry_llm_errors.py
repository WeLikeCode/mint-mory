"""Reading a malformed port for telemetry must not change what an LLM call raises.

Spec: observability › Telemetry must not change what an LLM call raises: reading — feedback FB-002.

``post_chat_completion`` reads ``urlsplit(base_url).port`` for the ``gen_ai.chat`` span
attributes. ``urlsplit`` raises ``ValueError`` for a non-numeric or out-of-range port
before the request is made, which replaces the ``http.client.InvalidURL`` /
``urllib.error.URLError`` the caller saw before telemetry was added. These tests fail by
assertion against the current code, which lets that ``ValueError`` escape.
"""

from __future__ import annotations

import http.client
import urllib.error

import pytest
from mintmory.core.llm import post_chat_completion


@pytest.mark.l4("C-8c8c8cf4")
@pytest.mark.parametrize("port", ["abc", "99999"])
def test_malformed_port_raises_the_pre_telemetry_exception(port: str) -> None:
    """A malformed port still surfaces as InvalidURL/URLError, never as ValueError."""
    try:
        post_chat_completion(
            base_url=f"http://127.0.0.1:{port}",
            api_key=None,
            payload={"model": "test-model", "messages": []},
            timeout_s=0.5,
            system="test",
            model="test-model",
        )
    except (http.client.InvalidURL, urllib.error.URLError):
        pass
    except ValueError as exc:
        pytest.fail(f"telemetry changed the raised exception to ValueError: {exc}")
    else:
        pytest.fail("expected the request to fail for the malformed port")
