import pytest

from reccobeats_mcp import server

pytestmark = pytest.mark.anyio

TRACK = "0lrkMvRttmoXjMNS8YONvj"
ARTIST = "1dfeR4HaWDbWqFHLkxsg1d"
ALBUM = "7HVoV2lgVsmuiHsjbbUJB4"
UUID = "387bbec0-a716-4457-ba12-3a260fe3c032"
UUID2 = "03184b85-67ac-4c6d-a6b2-ae2f441a8905"
ISRC = "USRC11700356"

async def call(mcp_client, name, arguments):
    """Call a tool and return its structured result, failing the test if the tool errored."""
    result = await mcp_client.call_tool(name, arguments)
    assert not result.is_error, result.content[0].text
    return result.structured_content


# --- Docstring helper -----------------------------------------------------------


def test_with_audio_features_doc():
    @server.with_audio_features_doc
    def tool():
        """Intro.

        {audio_features}
        """

    assert server.AUDIO_FEATURES_DOC in tool.__doc__
    assert "{audio_features}" not in tool.__doc__

# --- Search -----------------------------------------------------------------------


class TestSearch:
    async def test_search_tracks_defaults(self, mcp_client, fake_api):
        await call(mcp_client, "search_tracks", {"query": "Bohemian"})
        assert fake_api.paths == ["/track/search"]
        assert fake_api.params(fake_api.last) == {
            "searchText": "Bohemian",
            "sort": "desc",
            "page": "0",
            "size": "10",
        }

    async def test_search_tracks_with_artist_name(self, mcp_client, fake_api):
        await call(
            mcp_client,
            "search_tracks",
            {"query": "Bohemian", "artist": "Queen", "sort": "asc", "page": 2, "size": 5},
        )
        assert fake_api.params(fake_api.last) == {
            "searchText": "Bohemian",
            "artist": "Queen",
            "sort": "asc",
            "page": "2",
            "size": "5",
        }

    async def test_search_tracks_resolves_artist_id(self, mcp_client, fake_api):
        fake_api.route("/artist", {"content": [{"id": UUID}]})
        await call(
            mcp_client,
            "search_tracks",
            {"query": "Bohemian", "artist_id": f"https://open.spotify.com/artist/{ARTIST}"},
        )
        assert fake_api.paths == ["/artist", "/track/search"]
        assert fake_api.params(fake_api.requests[0]) == {"ids": ARTIST}
        assert fake_api.params(fake_api.last)["artistId"] == UUID

    async def test_search_tracks_with_uuid_artist_id_skips_lookup(self, mcp_client, fake_api):
        await call(mcp_client, "search_tracks", {"query": "Bohemian", "artist_id": UUID})
        assert fake_api.paths == ["/track/search"]
        assert fake_api.params(fake_api.last)["artistId"] == UUID

    @pytest.mark.parametrize(("tool", "path"), [("search_artists", "/artist/search"), ("search_albums", "/album/search")])
    async def test_search_artists_and_albums(self, mcp_client, fake_api, tool, path):
        await call(mcp_client, tool, {"query": "Queen", "page": 1, "size": 3})
        assert fake_api.paths == [path]
        assert fake_api.params(fake_api.last) == {"searchText": "Queen", "page": "1", "size": "3"}


# --- Batch lookups ------------------------------------------------------------------


class TestLookups:
    @pytest.mark.parametrize(
        ("tool", "path"),
        [
            ("get_tracks", "/track"),
            ("get_artists", "/artist"),
            ("get_albums", "/album"),
            ("get_audio_features", "/audio-features"),
        ],
    )
    async def test_ids_are_normalized(self, mcp_client, fake_api, tool, path):
        ids = [
            f"https://open.spotify.com/track/{TRACK}?si=abc",
            f"spotify:artist:{ARTIST}",
            f"  {UUID} ",
            ISRC,
        ]
        await call(mcp_client, tool, {"ids": ids})
        assert fake_api.paths == [path]
        assert fake_api.params(fake_api.last) == {"ids": [TRACK, ARTIST, UUID, ISRC]}

    async def test_result_is_returned(self, mcp_client, fake_api):
        fake_api.route("/track", {"content": [{"id": UUID, "trackTitle": "x"}]})
        assert await call(mcp_client, "get_tracks", {"ids": [UUID]}) == {
            "content": [{"id": UUID, "trackTitle": "x"}]
        }


# --- Relationships ------------------------------------------------------------------

RELATIONSHIP_TOOLS = [
    # tool, ID argument, kind looked up, path suffix, default page size, spotify id
    ("get_artist_tracks", "artist_id", "artist", "track", "25", ARTIST),
    ("get_artist_albums", "artist_id", "artist", "album", "25", ARTIST),
    ("get_album_tracks", "album_id", "album", "track", "50", ALBUM),
    ("get_track_albums", "track_id", "track", "album", "25", TRACK),
]


class TestRelationships:
    @pytest.mark.parametrize(("tool", "arg", "kind", "suffix", "size", "_"), RELATIONSHIP_TOOLS)
    async def test_uuid_is_used_directly(self, mcp_client, fake_api, tool, arg, kind, suffix, size, _):
        await call(mcp_client, tool, {arg: UUID})
        assert fake_api.paths == [f"/{kind}/{UUID}/{suffix}"]
        assert fake_api.params(fake_api.last) == {"page": "0", "size": size}

    @pytest.mark.parametrize(("tool", "arg", "kind", "suffix", "_", "spotify_id"), RELATIONSHIP_TOOLS)
    async def test_spotify_id_is_resolved_first(
        self, mcp_client, fake_api, tool, arg, kind, suffix, _, spotify_id
    ):
        fake_api.route(f"/{kind}", {"content": [{"id": UUID}]})
        await call(mcp_client, tool, {arg: f"spotify:{kind}:{spotify_id}", "page": 3, "size": 7})
        assert fake_api.paths == [f"/{kind}", f"/{kind}/{UUID}/{suffix}"]
        assert fake_api.params(fake_api.requests[0]) == {"ids": spotify_id}
        assert fake_api.params(fake_api.last) == {"page": "3", "size": "7"}

    async def test_isrc_is_rejected(self, mcp_client, fake_api):
        result = await mcp_client.call_tool("get_track_albums", {"track_id": ISRC})
        assert result.is_error
        assert "get_tracks" in result.content[0].text
        assert fake_api.requests == []

    async def test_unknown_id(self, mcp_client, fake_api):
        result = await mcp_client.call_tool("get_album_tracks", {"album_id": ALBUM})
        assert result.is_error
        assert f"No album found in ReccoBeats for id '{ALBUM}'" in result.content[0].text
        assert fake_api.paths == ["/album"]


# --- Recommendations ------------------------------------------------------------------


class TestRecommendations:
    async def test_defaults(self, mcp_client, fake_api):
        await call(mcp_client, "get_recommendations", {"seeds": [f"spotify:track:{TRACK}"]})
        assert fake_api.paths == ["/track/recommendation"]
        assert fake_api.params(fake_api.last) == {"seeds": TRACK, "size": "20"}

    async def test_all_parameters_are_mapped(self, mcp_client, fake_api):
        await call(
            mcp_client,
            "get_recommendations",
            {
                "seeds": [f"https://open.spotify.com/track/{TRACK}", UUID],
                "size": 5,
                "negative_seeds": [f"spotify:track:{TRACK}", UUID2],
                "acousticness": 0.1,
                "danceability": 0.2,
                "energy": 0.3,
                "instrumentalness": 0.4,
                "liveness": 0.5,
                "speechiness": 0.6,
                "valence": 0.7,
                "key": 9,
                "mode": 0,
                "loudness": -8.5,
                "tempo": 120,
                "popularity": 80,
                "feature_weight": 3,
            },
        )
        assert fake_api.params(fake_api.last) == {
            "seeds": [TRACK, UUID],
            "size": "5",
            "negativeSeeds": [TRACK, UUID2],
            "acousticness": "0.1",
            "danceability": "0.2",
            "energy": "0.3",
            "instrumentalness": "0.4",
            "liveness": "0.5",
            "speechiness": "0.6",
            "valence": "0.7",
            "key": "9",
            "mode": "0",
            "loudness": "-8.5",
            "tempo": "120.0",
            "popularity": "80",
            "featureWeight": "3.0",
        }

    async def test_zero_targets_are_sent(self, mcp_client, fake_api):
        # 0 is a meaningful target and must not be dropped like None.
        await call(mcp_client, "get_recommendations", {"seeds": [UUID], "energy": 0, "key": 0, "mode": 0})
        params = fake_api.params(fake_api.last)
        assert (params["energy"], params["key"], params["mode"]) == ("0.0", "0", "0")

    async def test_include_available_countries(self, mcp_client, fake_api):
        fake_api.route("/track/recommendation", {"content": [{"id": UUID, "availableCountries": "DE,IT"}]})
        default = await call(mcp_client, "get_recommendations", {"seeds": [UUID]})
        included = await call(
            mcp_client, "get_recommendations", {"seeds": [UUID], "include_available_countries": True}
        )
        assert default == {"content": [{"id": UUID}]}
        assert included == {"content": [{"id": UUID, "availableCountries": "DE,IT"}]}


# --- Audio extraction -----------------------------------------------------------------


class TestExtractAudioFeatures:
    async def test_uploads_file(self, mcp_client, fake_api, wav_file):
        fake_api.route("/analysis/audio-features", {"energy": 0.42, "tempo": 120.0})
        result = await call(mcp_client, "extract_audio_features", {"file_path": str(wav_file)})
        assert result == {"energy": 0.42, "tempo": 120.0}
        assert fake_api.paths == ["/analysis/audio-features"]

    async def test_missing_file_is_reported(self, mcp_client, fake_api, tmp_path):
        result = await mcp_client.call_tool("extract_audio_features", {"file_path": str(tmp_path / "x.mp3")})
        assert result.is_error
        assert "Audio file not found" in result.content[0].text
        assert fake_api.requests == []
