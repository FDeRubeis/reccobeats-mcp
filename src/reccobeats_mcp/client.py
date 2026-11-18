"""Thin async client for the ReccoBeats REST API (https://reccobeats.com/docs)."""

import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

import httpx
import puremagic

from mcp.server.mcpserver.exceptions import ToolError

BASE_URL = os.environ.get("RECCOBEATS_BASE_URL", "https://api.reccobeats.com/v1")
TIMEOUT = float(os.environ.get("RECCOBEATS_TIMEOUT", "30"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# Formats documented at https://reccobeats.com/docs/documentation/Analysis/audio-features-extraction
SUPPORTED_AUDIO_FORMATS = "MP3, OGG (Vorbis), WAV, AIFF/AIFC"
SUPPORTED_AUDIO_MIME_TYPES = frozenset(
    {
        "audio/mpeg",
        "audio/ogg",
        "application/ogg",
        "audio/wav",
        "audio/x-wav",
        "audio/aiff",
        "audio/x-aiff",
    }
)

# ReccoBeats IDs are UUIDs (v4 in practice); Spotify IDs and ISRCs never match this regex.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$", re.IGNORECASE)
_SPOTIFY_REF_RE = re.compile(
    r"(?:spotify:(?:track|artist|album):|open\.spotify\.com/(?:[a-z-]+/)?(?:track|artist|album)/)"
    r"([A-Za-z0-9]{22})(?![A-Za-z0-9])"
)

Kind = Literal["track", "artist", "album"]

# MCPServer sets the root logger to INFO, which would log every API request.
logging.getLogger("httpx").setLevel(logging.WARNING)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=TIMEOUT,
            headers={"Accept": "application/json", "User-Agent": "reccobeats-mcp"},
        )
    return _client


def normalize_id(value: str) -> str:
    """Accept bare IDs as well as Spotify URIs/URLs and return the bare ID."""
    value = value.strip()
    if match := _SPOTIFY_REF_RE.search(value):
        return match.group(1)
    return value


async def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> Any:
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        response = await _get_client().request(method, path, params=clean_params, files=files)
    except httpx.TimeoutException as exc:
        raise ToolError(f"ReccoBeats API timed out after {TIMEOUT:.0f}s") from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"Could not reach the ReccoBeats API: {exc}") from exc

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        hint = f" Retry after {retry_after}s." if retry_after else ""
        raise ToolError(f"ReccoBeats rate limit exceeded.{hint}")
    if response.is_error:
        detail = response.text.strip()[:500] or response.reason_phrase
        raise ToolError(f"ReccoBeats API error {response.status_code}: {detail}")

    try:
        return response.json()
    except ValueError as exc:
        raise ToolError(
            f"ReccoBeats API returned invalid JSON (HTTP {response.status_code})"
        ) from exc


async def get(
    path: str, *, params: dict[str, Any] | None = None, include_countries: bool = False
) -> Any:
    """GET an endpoint. Optionally remove availableCountries field."""
    data = await request("GET", path, params=params)
    if not include_countries and isinstance(data, dict):
        for item in data.get("content") or []:
            if isinstance(item, dict):
                item.pop("availableCountries", None)
    return data


async def resolve_id(kind: Kind, value: str) -> str:
    """Return the ReccoBeats UUID for a ReccoBeats or Spotify ID.

    Path-parameter endpoints only accept ReccoBeats IDs, while the batch
    endpoints also accept Spotify IDs, so Spotify IDs are looked up first.
    ISRCs are rejected: one ISRC can match several tracks, so the model must
    look it up with get_tracks and pick one.
    """
    value = normalize_id(value)
    if _UUID_RE.match(value):
        return value
    if kind == "track" and _ISRC_RE.match(value):
        raise ToolError(
            f"'{value}' is an ISRC, which this tool doesn't accept. Call get_tracks with it to get "
            "the matching ReccoBeats/Spotify IDs, then pass one of them."
        )
    data = await get(f"/{kind}", params={"ids": [value]})
    items = data.get("content") or []
    if not items:
        raise ToolError(f"No {kind} found in ReccoBeats for id '{value}'")
    return items[0]["id"]


def is_supported_audio(path: Path) -> bool:
    """Check the file's magic bytes against the formats ReccoBeats accepts."""
    try:
        return puremagic.from_file(path, mime=True) in SUPPORTED_AUDIO_MIME_TYPES
    except (puremagic.PureError, ValueError):  # no known signature / empty file
        return False


async def upload_audio(file_path: str) -> Any:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise ToolError(f"Audio file not found: {path}")
    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise ToolError(
            f"Audio file is {size / 1024 / 1024:.1f} MB; ReccoBeats accepts at most 5 MB."
        )
    if not is_supported_audio(path):
        raise ToolError(f"Unsupported file type. Supported formats: {SUPPORTED_AUDIO_FORMATS}.")
    return await request(
        "POST", "/analysis/audio-features", files={"audioFile": (path.name, path.read_bytes())}
    )
