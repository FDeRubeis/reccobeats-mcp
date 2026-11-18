"""Smoke tests against the real ReccoBeats API, to catch changes in its contract.

They only run when selected explicitly: `pytest -m e2e`.
"""

import re

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.anyio]

# "Bohemian Rhapsody" by Pentatonix.
TRACK_ID = "387bbec0-a716-4457-ba12-3a260fe3c032"
TRACK_SPOTIFY_URL = "https://open.spotify.com/track/0lrkMvRttmoXjMNS8YONvj"
TRACK_ISRC = "USRC11700356"
ARTIST_ID = "fecab72e-c0be-44e3-81c5-cb72f07131a9"
ARTIST_SPOTIFY_URL = "https://open.spotify.com/artist/26AHtbjWKiwYzsoGoUZq53"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PAGE_KEYS = {"content", "page", "size", "totalElements", "totalPages"}


async def call(live_client, name, arguments):
    result = await live_client.call_tool(name, arguments)
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def test_search_tracks_shape(live_client):
    result = await call(live_client, "search_tracks", {"query": "Bohemian Rhapsody", "size": 3})
    assert PAGE_KEYS <= result.keys()
    assert result["page"] == 0
    assert 0 < len(result["content"]) <= 3
    for item in result["content"]:
        assert UUID_RE.match(item["id"])
        assert item["href"].startswith("https://open.spotify.com/track/")
        assert "availableCountries" not in item


async def test_available_countries_opt_in(live_client):
    result = await call(live_client, "get_tracks", {"ids": [TRACK_ID], "include_available_countries": True})
    assert "availableCountries" in result["content"][0]


async def test_get_tracks_by_spotify_url(live_client):
    result = await call(live_client, "get_tracks", {"ids": [TRACK_SPOTIFY_URL]})
    track = result["content"][0]
    assert (track["id"], track["isrc"], track["href"]) == (TRACK_ID, TRACK_ISRC, TRACK_SPOTIFY_URL)


async def test_get_tracks_by_isrc(live_client):
    result = await call(live_client, "get_tracks", {"ids": [TRACK_ISRC]})
    assert TRACK_ID in [t["id"] for t in result["content"]]


async def test_spotify_id_resolution_for_path_endpoint(live_client):
    # get_track_albums calls an endpoint that only takes ReccoBeats IDs, so this
    # exercises resolve_id's Spotify -> ReccoBeats lookup.
    result = await call(live_client, "get_track_albums", {"track_id": TRACK_SPOTIFY_URL, "size": 5})
    assert PAGE_KEYS <= result.keys()
    assert result["content"]


async def test_artist_relationships(live_client):
    tracks = await call(live_client, "get_artist_tracks", {"artist_id": ARTIST_SPOTIFY_URL, "size": 5})
    albums = await call(live_client, "get_artist_albums", {"artist_id": ARTIST_ID, "size": 5})
    assert tracks["content"]
    assert albums["content"]


async def test_audio_features(live_client):
    result = await call(live_client, "get_audio_features", {"ids": [TRACK_ID]})
    features = result["content"][0]
    for key in ("energy", "valence", "danceability", "tempo", "key", "mode", "loudness"):
        assert key in features


async def test_recommendations(live_client):
    result = await call(
        live_client, "get_recommendations", {"seeds": [TRACK_SPOTIFY_URL], "size": 5, "energy": 0.8}
    )
    assert 0 < len(result["content"]) <= 5
    assert all(UUID_RE.match(t["id"]) for t in result["content"])


async def test_unknown_spotify_id_is_reported(live_client):
    result = await live_client.call_tool("get_artist_tracks", {"artist_id": "0000000000000000000000"})
    assert result.is_error
    assert "No artist found" in result.content[0].text
