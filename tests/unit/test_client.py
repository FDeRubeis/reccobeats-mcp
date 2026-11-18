import httpx
import pytest

from mcp.server.mcpserver.exceptions import ToolError
from reccobeats_mcp import client
from reccobeats_mcp.client import normalize_id

TRACK = "0lrkMvRttmoXjMNS8YONvj"
ARTIST = "1dfeR4HaWDbWqFHLkxsg1d"
ALBUM = "7HVoV2lgVsmuiHsjbbUJB4"
UUID = "387bbec0-a716-4457-ba12-3a260fe3c032"
ISRC = "USRC11700356"

pytestmark = pytest.mark.anyio


# --- normalize_id -------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (f"spotify:artist:{ARTIST}", ARTIST),
        (f"https://open.spotify.com/album/{ALBUM}", ALBUM),
        (f"open.spotify.com/track/{TRACK}?si=abc123", TRACK),
        (f"https://open.spotify.com/intl-de/track/{TRACK}", TRACK),
        (f" \tspotify:track:{TRACK}\n", TRACK),
        (f"  {UUID}  ", UUID),
        (ISRC, ISRC),
        ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",) * 2,
        (f"https://example.com/track/{TRACK}",) * 2,
        (f"spotify:track:{TRACK}X",) * 2,
    ],
    ids=[
        "uri",
        "url",
        "url-no-scheme-with-query",
        "url-locale-prefix",
        "whitespace",
        "bare-id",
        "isrc",
        "unsupported-kind",
        "other-domain",
        "id-too-long",
    ],
)
def test_normalize_id(value, expected):
    assert normalize_id(value) == expected


# --- ID regexes ---------------------------------------------------------------


class TestIdPatterns:
    @pytest.mark.parametrize(
        ("value", "is_uuid", "is_isrc"),
        [
            (UUID, True, False),
            (UUID.upper(), True, False),
            (ISRC, False, True),
            (ISRC.lower(), False, True),
            ("GBUM71029604", False, True),
            (TRACK, False, False),
            (ARTIST, False, False),
            (ALBUM, False, False),
            (UUID[:-1], False, False),
            (f"{UUID}x", False, False),
            ("US-RC1-17-00356", False, False),
            ("USRC1170035", False, False),  # too short
        ],
    )
    def test_classification(self, value, is_uuid, is_isrc):
        assert bool(client._UUID_RE.match(value)) is is_uuid
        assert bool(client._ISRC_RE.match(value)) is is_isrc


# --- request / get ------------------------------------------------------------


class TestRequest:
    async def test_none_params_are_dropped(self, fake_api):
        await client.request("GET", "/x", params={"a": 1, "b": None, "c": "z"})
        assert fake_api.params(fake_api.last) == {"a": "1", "c": "z"}

    async def test_timeout(self, fake_api):
        fake_api.route("/x", httpx.ReadTimeout("slow"))
        with pytest.raises(ToolError, match=rf"timed out after {client.TIMEOUT:.0f}s"):
            await client.request("GET", "/x")

    async def test_connection_error(self, fake_api):
        fake_api.route("/x", httpx.ConnectError("refused"))
        with pytest.raises(ToolError, match=r"^Could not reach the ReccoBeats API: refused$"):
            await client.request("GET", "/x")

    async def test_rate_limit_with_retry_after(self, fake_api):
        fake_api.route("/x", httpx.Response(429, headers={"Retry-After": "7"}))
        with pytest.raises(ToolError, match=r"^ReccoBeats rate limit exceeded\. Retry after 7s\.$"):
            await client.request("GET", "/x")

    async def test_rate_limit_without_retry_after(self, fake_api):
        fake_api.route("/x", httpx.Response(429))
        with pytest.raises(ToolError, match=r"^ReccoBeats rate limit exceeded\.$"):
            await client.request("GET", "/x")

    async def test_error_body_is_truncated(self, fake_api):
        fake_api.route("/x", httpx.Response(500, text="  " + "x" * 600 + "  "))
        with pytest.raises(ToolError) as exc_info:
            await client.request("GET", "/x")
        assert str(exc_info.value) == f"ReccoBeats API error 500: {'x' * 500}"

    async def test_error_without_body_uses_reason_phrase(self, fake_api):
        fake_api.route("/x", httpx.Response(503))
        with pytest.raises(ToolError, match=r"^ReccoBeats API error 503: Service Unavailable$"):
            await client.request("GET", "/x")

    async def test_returns_json(self, fake_api):
        fake_api.route("/x", {"content": [{"id": 1}]})
        assert await client.request("GET", "/x") == {"content": [{"id": 1}]}

    async def test_non_json_success_response(self, fake_api):
        fake_api.route("/x", httpx.Response(200, text="<html>proxy error</html>"))
        with pytest.raises(ToolError, match="invalid JSON"):
            await client.request("GET", "/x")


class TestGet:
    async def test_strips_available_countries_by_default(self, fake_api):
        fake_api.route("/x", {"content": [{"id": 1, "availableCountries": "DE,IT"}, {"id": 2}]})
        assert await client.get("/x") == {"content": [{"id": 1}, {"id": 2}]}

    async def test_keeps_available_countries_when_requested(self, fake_api):
        body = {"content": [{"id": 1, "availableCountries": "DE,IT"}]}
        fake_api.route("/x", body)
        assert await client.get("/x", include_countries=True) == body

    @pytest.mark.parametrize(
        "body",
        [
            [{"id": 1, "availableCountries": "DE"}],
            {"id": 1},
            {"content": None},
            {"content": ["a", 1, None]},
        ],
        ids=["list-response", "no-content", "null-content", "non-dict-items"],
    )
    async def test_returns_response_unchanged(self, fake_api, body):
        fake_api.route("/x", body)
        assert await client.get("/x") == body


# --- resolve_id ---------------------------------------------------------------


class TestResolveId:
    async def test_uuid_is_returned_without_lookup(self, fake_api):
        assert await client.resolve_id("artist", UUID) == UUID
        assert fake_api.requests == []

    async def test_isrc_track_is_rejected_without_lookup(self, fake_api):
        with pytest.raises(ToolError, match="is an ISRC.*get_tracks"):
            await client.resolve_id("track", ISRC)
        assert fake_api.requests == []

    @pytest.mark.parametrize(
        ("kind", "value", "spotify_id"),
        [
            ("track", f"https://open.spotify.com/track/{TRACK}?si=x", TRACK),
            ("artist", f"spotify:artist:{ARTIST}", ARTIST),
            ("album", ALBUM, ALBUM),
        ],
    )
    async def test_spotify_id_is_looked_up(self, fake_api, kind, value, spotify_id):
        fake_api.route(f"/{kind}", {"content": [{"id": UUID, "availableCountries": "DE"}]})
        assert await client.resolve_id(kind, value) == UUID
        assert fake_api.paths == [f"/{kind}"]
        assert fake_api.params(fake_api.last) == {"ids": spotify_id}

    async def test_not_found(self, fake_api):
        fake_api.route("/artist", {"content": []})
        with pytest.raises(ToolError, match=rf"^No artist found in ReccoBeats for id '{ARTIST}'$"):
            await client.resolve_id("artist", ARTIST)

    async def test_api_error_propagates(self, fake_api):
        fake_api.route("/album", httpx.Response(500, text="boom"))
        with pytest.raises(ToolError, match="ReccoBeats API error 500: boom"):
            await client.resolve_id("album", ALBUM)


# --- audio upload ---------------------------------------------------------------

class TestIsSupportedAudio:
    def test_supported_format(self, wav_file):
        assert client.is_supported_audio(wav_file) is True

    def test_unsupported_format(self, tmp_path):
        path = tmp_path / "notes.mp3"  # the extension must not matter
        path.write_text("not audio at all\n")
        assert client.is_supported_audio(path) is False

    def test_detection_error(self, tmp_path):
        path = tmp_path / "empty.wav"  # puremagic raises on empty files
        path.write_bytes(b"")
        assert client.is_supported_audio(path) is False


class TestUploadAudio:
    async def test_uploads_file(self, fake_api, wav_file):
        fake_api.route("/analysis/audio-features", {"energy": 0.5})
        assert await client.upload_audio(str(wav_file)) == {"energy": 0.5}

        request = fake_api.last
        assert request.method == "POST"
        assert fake_api.paths == ["/analysis/audio-features"]
        assert request.headers["content-type"].startswith("multipart/form-data")
        body = request.read()
        assert b'name="audioFile"; filename="clip.wav"' in body
        assert wav_file.read_bytes() in body

    async def test_missing_file(self, fake_api, tmp_path):
        missing = tmp_path / "nope.mp3"
        with pytest.raises(ToolError, match=rf"^Audio file not found: {missing}$"):
            await client.upload_audio(str(missing))
        assert fake_api.requests == []

    async def test_exactly_max_size_is_accepted(self, fake_api, wav_file):
        with wav_file.open("r+b") as f:
            f.truncate(client.MAX_UPLOAD_BYTES)
        await client.upload_audio(str(wav_file))
        assert fake_api.paths == ["/analysis/audio-features"]

    async def test_too_large(self, fake_api, wav_file):
        with wav_file.open("r+b") as f:
            f.truncate(client.MAX_UPLOAD_BYTES + 1)
        with pytest.raises(ToolError, match=r"^Audio file is 5\.0 MB; ReccoBeats accepts at most 5 MB\.$"):
            await client.upload_audio(str(wav_file))
        assert fake_api.requests == []

    async def test_unsupported_type(self, fake_api, tmp_path):
        path = tmp_path / "notes.mp3"
        path.write_text("not audio at all\n")
        with pytest.raises(ToolError, match=r"^Unsupported file type\. Supported formats: MP3"):
            await client.upload_audio(str(path))
        assert fake_api.requests == []

    async def test_api_error_propagates(self, fake_api, wav_file):
        fake_api.route("/analysis/audio-features", httpx.Response(422, text="audio too short"))
        with pytest.raises(ToolError, match="ReccoBeats API error 422: audio too short"):
            await client.upload_audio(str(wav_file))
