import pytest

from mcp import Client
from reccobeats_mcp import client, server


@pytest.fixture
async def live_client(monkeypatch):
    """An MCP client wired to the real ReccoBeats API, with a fresh HTTP client per test."""
    monkeypatch.setattr(client, "_client", None)
    async with Client(server.mcp) as c:
        yield c
    if client._client is not None:
        await client._client.aclose()
