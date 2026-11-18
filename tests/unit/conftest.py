import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from mcp import Client
from reccobeats_mcp import client, server

FAKE_BASE_URL = "https://api.reccobeats.test/v1"
BASE_PATH = httpx.URL(FAKE_BASE_URL).path

Route = httpx.Response | dict | list | Exception | Callable[[httpx.Request], httpx.Response]


class FakeAPI:
    """Stand-in for the ReccoBeats API: records requests and serves canned responses by path."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[str, Route] = {}

    def route(self, path: str, response: Route) -> None:
        """Register a response for an API path such as "/track" (relative to the base URL)."""
        self.routes[path] = response

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix(BASE_PATH)
        response = self.routes.get(path, {"content": []})
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(request)
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200, json=response)

    @property
    def paths(self) -> list[str]:
        return [r.url.path.removeprefix(BASE_PATH) for r in self.requests]

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    @staticmethod
    def params(request: httpx.Request) -> dict[str, Any]:
        """Query params of a request; repeated keys become lists."""
        out: dict[str, Any] = {}
        for key in request.url.params.keys():
            values = request.url.params.get_list(key)
            out[key] = values if len(values) > 1 else values[0]
        return out


@pytest.fixture
def fake_api(monkeypatch) -> FakeAPI:
    api = FakeAPI()
    fake_client = httpx.AsyncClient(base_url=FAKE_BASE_URL, transport=httpx.MockTransport(api.handler))
    monkeypatch.setattr(client, "_client", fake_client)
    return api


@pytest.fixture
async def mcp_client(fake_api):
    async with Client(server.mcp) as c:
        yield c


@pytest.fixture
def wav_file(tmp_path) -> Path:
    """A real, valid WAV file: 0.1 s of mono 8 kHz silence."""
    path = tmp_path / "clip.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * 800)
    return path
