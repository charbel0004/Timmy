import asyncio

import httpx
import pytest

from timmy import ai_status
from timmy.config import Settings


@pytest.mark.parametrize(("tags", "expected"), [
    ({"models": [{"name": "qwen-test:latest"}]}, "ready"),
    ({"models": [{"name": "another-model:latest"}]}, "model_missing"),
    ({"models": None}, "unreachable"),
    (None, "unreachable"),
])
def test_ollama_status(monkeypatch, tags, expected):
    def handle(request):
        assert str(request.url) == "http://127.0.0.1:11434/api/tags"
        if tags is None:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, json=tags)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(ai_status.httpx, "AsyncClient", lambda **kwargs: client)
    result = asyncio.run(ai_status.probe_ollama(Settings(
        ollama_url="http://127.0.0.1:11434", ollama_model="qwen-test",
    )))
    assert result.status == expected
    assert result.model == "qwen-test"
