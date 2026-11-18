from typing import Annotated, Any, Literal

from pydantic import Field

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from . import client

mcp = MCPServer(
    name="reccobeats",
    instructions=(
        "Tools for the ReccoBeats music database and recommendation API. Typical flow: search "
        "for a track/artist/album to get its ID, then fetch details, audio features, or "
        "recommendations. Every tool accepts ReccoBeats IDs (UUIDs) and Spotify IDs, URIs or "
        "URLs. To find tracks by ISRC, call get_tracks with it. Paginated results are 0-indexed and report page, "
        "size, totalElements and totalPages."
    ),
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True, idempotent_hint=True)

TrackId = Annotated[
    str,
    Field(
        description="ReccoBeats track ID or Spotify track ID/URI/URL. Not an ISRC: "
        "resolve ISRCs with get_tracks first."
    ),
]
ArtistId = Annotated[str, Field(description="ReccoBeats artist ID or Spotify artist ID/URI/URL.")]
AlbumId = Annotated[str, Field(description="ReccoBeats album ID or Spotify album ID/URI/URL.")]
Page = Annotated[int, Field(ge=0, le=1000, description="0-based page number.")]
PageSize = Annotated[int, Field(ge=1, le=50, description="Results per page.")]
SearchText = Annotated[str, Field(min_length=3, max_length=1000)]
Unit = Annotated[float | None, Field(ge=0, le=1)]
IncludeCountries = Annotated[
    bool,
    Field(
        description="Include availableCountries (comma-separated ISO 3166-1 alpha-2 codes "
        "where each item is available). Off by default because it's a long list per item; "
        "enable it only when regional availability matters."
    ),
]

AUDIO_FEATURES_DOC = """\
Audio features are numbers computed from the audio signal that describe how a
track sounds.

- energy (0-1): intensity and liveliness, influenced by tempo, loudness and
  the overall drive of the music. 0 is a very calm, relaxed song; 1 is a
  high-energy, intense one.
- valence (0-1): emotional tone. 0 feels negative, sad or dark; 1 feels
  positive, happy or uplifting.
- danceability (0-1): how suitable the track is for dancing, based on tempo,
  rhythm, beat consistency and energy. 0 is not danceable at all; 1 is highly
  danceable.
- tempo (BPM): estimated tempo in beats per minute, typically 0-250.
- key (-1 to 11): pitch class of the key: 0=C, 1=C#/Db, 2=D, 3=D#/Eb, 4=E,
  5=F, 6=F#/Gb, 7=G, 8=G#/Ab, 9=A, 10=A#/Bb, 11=B; -1 if no key was detected.
- mode (0 or 1): 1 = major, 0 = minor. Combined with key it gives the full
  key, e.g. key=9, mode=0 is A minor.
- loudness (dB): average loudness across the track, typically -60 to 0; values
  closer to 0 are louder. Useful for comparing tracks.
- acousticness (0-1): confidence that the track is acoustic; higher values mean
  more natural, non-electronic sound.
- instrumentalness (0-1): likelihood that the track has no vocals. "Ooh" and
  "aah" count as instrumental; rap and spoken word count as vocal. Above 0.5
  suggests an instrumental track, with confidence rising toward 1.
- speechiness (0-1): presence of spoken words. Above 0.66 is probably entirely
  speech (talk show, audiobook, poetry); 0.33-0.66 mixes music and speech
  (e.g. rap); below 0.33 is most likely music.
- liveness (0-1): probability that an audience is present, i.e. a live
  recording. Above 0.8 strongly suggests live."""


def with_audio_features_doc(fn):
    """Substitute `{audio_features}` in the tool's docstring, which MCPServer uses as its description."""
    fn.__doc__ = fn.__doc__.replace("{audio_features}", AUDIO_FEATURES_DOC)
    return fn


def _ids(ids: list[str]) -> list[str]:
    return [client.normalize_id(i) for i in ids]


# --- Search -----------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def search_tracks(
    query: Annotated[SearchText, Field(description="Track title to search for.")],
    artist: Annotated[
        SearchText | None,
        Field(
            description="Only return tracks by this artist name. Unreliable for some artists; "
            "prefer artist_id when known.",
        ),
    ] = None,
    artist_id: Annotated[
        str | None,
        Field(description="Only return tracks by this artist (ReccoBeats/Spotify ID)"),
    ] = None,
    sort: Annotated[
        Literal["asc", "desc"],
        Field(description="Popularity order, applied after search relevance."),
    ] = "desc",
    page: Page = 0,
    size: PageSize = 10,
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """Search tracks by title, optionally filtered by artist."""
    if artist_id:
        artist_id = await client.resolve_id("artist", artist_id)
    return await client.get(
        "/track/search",
        params={
            "searchText": query,
            "artist": artist,
            "artistId": artist_id,
            "sort": sort,
            "page": page,
            "size": size,
        },
        include_countries=include_available_countries,
    )


@mcp.tool(annotations=READ_ONLY)
async def search_artists(
    query: Annotated[SearchText, Field(description="Artist name to search for.")],
    page: Page = 0,
    size: PageSize = 10,
) -> dict[str, Any]:
    """Search artists by name."""
    return await client.get(
        "/artist/search", params={"searchText": query, "page": page, "size": size}
    )


@mcp.tool(annotations=READ_ONLY)
async def search_albums(
    query: Annotated[SearchText, Field(description="Album name to search for.")],
    page: Page = 0,
    size: PageSize = 10,
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """Search albums by name."""
    return await client.get(
        "/album/search",
        params={"searchText": query, "page": page, "size": size},
        include_countries=include_available_countries,
    )


# --- Lookups ----------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def get_tracks(
    ids: Annotated[list[str], Field(min_length=1, max_length=40, description="Up to 40 track IDs (ReccoBeats, Spotify, or ISRC).")],
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """Get track details (title, artists, duration, ISRC, popularity, Spotify link) for one or more tracks."""
    return await client.get(
        "/track", params={"ids": _ids(ids)}, include_countries=include_available_countries
    )


@mcp.tool(annotations=READ_ONLY)
async def get_artists(
    ids: Annotated[list[str], Field(min_length=1, max_length=40, description="Up to 40 artist IDs (ReccoBeats or Spotify).")],
) -> dict[str, Any]:
    """Get artist details for one or more artists."""
    return await client.get("/artist", params={"ids": _ids(ids)})


@mcp.tool(annotations=READ_ONLY)
async def get_albums(
    ids: Annotated[list[str], Field(min_length=1, max_length=40, description="Up to 40 album IDs (ReccoBeats or Spotify).")],
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """Get album details (type, artists, track count, release date, label, popularity) for one or more albums."""
    return await client.get(
        "/album", params={"ids": _ids(ids)}, include_countries=include_available_countries
    )


@mcp.tool(annotations=READ_ONLY)
@with_audio_features_doc
async def get_audio_features(
    ids: Annotated[list[str], Field(min_length=1, max_length=40, description="Up to 40 track IDs (ReccoBeats, Spotify, or ISRC).")],
) -> dict[str, Any]:
    """Get audio features for one or more tracks.

    Tracks without analysed features are omitted from the result.

    {audio_features}
    """
    return await client.get("/audio-features", params={"ids": _ids(ids)})


# --- Relationships ----------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def get_artist_tracks(
    artist_id: ArtistId,
    page: Page = 0,
    size: PageSize = 25,
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """List an artist's tracks (paginated)."""
    rid = await client.resolve_id("artist", artist_id)
    return await client.get(
        f"/artist/{rid}/track",
        params={"page": page, "size": size},
        include_countries=include_available_countries,
    )


@mcp.tool(annotations=READ_ONLY)
async def get_artist_albums(
    artist_id: ArtistId,
    page: Page = 0,
    size: PageSize = 25,
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """List an artist's albums, singles and compilations (paginated)."""
    rid = await client.resolve_id("artist", artist_id)
    return await client.get(
        f"/artist/{rid}/album",
        params={"page": page, "size": size},
        include_countries=include_available_countries,
    )


@mcp.tool(annotations=READ_ONLY)
async def get_album_tracks(
    album_id: AlbumId,
    page: Page = 0,
    size: PageSize = 50,
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """List the tracks on an album (paginated)."""
    rid = await client.resolve_id("album", album_id)
    return await client.get(
        f"/album/{rid}/track",
        params={"page": page, "size": size},
        include_countries=include_available_countries,
    )


@mcp.tool(annotations=READ_ONLY)
async def get_track_albums(
    track_id: TrackId,
    page: Page = 0,
    size: PageSize = 25,
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """List the albums a track appears on (paginated)."""
    rid = await client.resolve_id("track", track_id)
    return await client.get(
        f"/track/{rid}/album",
        params={"page": page, "size": size},
        include_countries=include_available_countries,
    )


# --- Recommendations & analysis ---------------------------------------------


@mcp.tool(annotations=READ_ONLY)
@with_audio_features_doc
async def get_recommendations(
    seeds: Annotated[
        list[str],
        Field(min_length=1, max_length=5, description="1-5 seed track IDs (ReccoBeats or Spotify) to base recommendations on."),
    ],
    size: Annotated[int, Field(ge=1, le=100, description="Number of tracks to return.")] = 20,
    negative_seeds: Annotated[
        list[str] | None,
        Field(min_length=1, max_length=5, description="Up to 5 track IDs the listener dislikes; results steer away from them."),
    ] = None,
    acousticness: Annotated[Unit, Field(description="Target acousticness, 0 (electronic) to 1 (acoustic).")] = None,
    danceability: Annotated[Unit, Field(description="Target danceability, 0 to 1.")] = None,
    energy: Annotated[Unit, Field(description="Target energy, 0 (calm) to 1 (intense).")] = None,
    instrumentalness: Annotated[Unit, Field(description="Target instrumentalness; >0.5 suggests no vocals.")] = None,
    liveness: Annotated[Unit, Field(description="Target liveness; >0.8 suggests a live recording.")] = None,
    speechiness: Annotated[Unit, Field(description="Target speechiness; >0.66 is mostly spoken word.")] = None,
    valence: Annotated[Unit, Field(description="Target mood, 0 (sad/dark) to 1 (happy/uplifting).")] = None,
    key: Annotated[int | None, Field(ge=-1, le=11, description="Target key as pitch class (0=C, 1=C#/Db, ... 11=B).")] = None,
    mode: Annotated[int | None, Field(ge=0, le=1, description="1 = major, 0 = minor.")] = None,
    loudness: Annotated[float | None, Field(ge=-60, le=2, description="Target loudness in dB.")] = None,
    tempo: Annotated[float | None, Field(ge=0, le=250, description="Target tempo in BPM.")] = None,
    popularity: Annotated[int | None, Field(ge=0, le=100, description="Target popularity, 0 to 100.")] = None,
    feature_weight: Annotated[
        float | None,
        Field(ge=1, le=5, description="How strongly the target audio features influence results (1-5)."),
    ] = None,
    include_available_countries: IncludeCountries = False,
) -> dict[str, Any]:
    """Recommend tracks similar to the seed tracks, optionally nudged toward target audio features.

    {audio_features}
    """
    return await client.get(
        "/track/recommendation",
        params={
            "seeds": _ids(seeds),
            "size": size,
            "negativeSeeds": _ids(negative_seeds) if negative_seeds else None,
            "acousticness": acousticness,
            "danceability": danceability,
            "energy": energy,
            "instrumentalness": instrumentalness,
            "liveness": liveness,
            "speechiness": speechiness,
            "valence": valence,
            "key": key,
            "mode": mode,
            "loudness": loudness,
            "tempo": tempo,
            "popularity": popularity,
            "featureWeight": feature_weight,
        },
        include_countries=include_available_countries,
    )


# Technically read-only per the MCP spec (it doesn't modify the environment), but it uploads a
# local file to a third party, so it's marked not read-only to make clients cautious.
@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
)
async def extract_audio_features(
    file_path: Annotated[
        str,
        Field(
            description="Absolute path to a local audio file (MP3, OGG Vorbis, WAV or "
            "AIFF/AIFC), max 5 MB."
        ),
    ],
) -> dict[str, Any]:
    """Upload a local audio file to ReccoBeats and return its computed audio features.

    Useful for music that isn't in the catalog. The file is sent to ReccoBeats'
    servers. ReccoBeats analyses at most 30 seconds of audio; for longer tracks,
    split them into 30-second clips and average the results.
    """
    return await client.upload_audio(file_path)
