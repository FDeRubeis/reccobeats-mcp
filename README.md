# ReccoBeats MCP Server

An [MCP](https://modelcontextprotocol.io) server that provides integration with [ReccoBeats](https://reccobeats.com/docs/documentation/introduction), a free music database and recommendation API. This server lets the AI assistant in any MCP client (such as Claude Desktop, Claude Code, Cursor or VS Code) look up music, read how tracks sound and recommend new ones. It doesn't need an API key or an account.

> **Unofficial project.** This server is not affiliated with or endorsed by ReccoBeats.

## What you can do

Ask your assistant things like:

- *"Find Bohemian Rhapsody by Pentatonix and tell me its tempo and key."*
- *"Recommend 10 tracks like this one, but more upbeat:* `https://open.spotify.com/track/0lrkMvRttmoXjMNS8YONvj`*"*
- *"List Daft Punk's albums and compare the energy of their tracks."*
- *"Analyse `~/Music/demo.mp3` and suggest released songs that sound similar."*

In plain terms, the server enables the assistant to:

- **Search** for tracks, artists and albums by name.
- **Look up details**, such as a track's artists, duration and popularity, or an album's label and release date.
- **Read audio features**: numbers that describe how a track sounds, such as energy, mood, danceability, tempo and key.
- **Get recommendations** from up to 5 seed tracks, optionally steered toward a target sound (for example "calmer" or "more danceable").
- **Analyse your own audio files** by uploading a short local clip to ReccoBeats and getting its audio features back.

When talking to the assistant, you can refer to tracks, albums and artists by their name. To avoid ambiguity, you can also use ReccoBeats IDs or Spotify IDs, URIs (`spotify:track:…`) or links (`https://open.spotify.com/…`). For tracks you can also use ISRCs.

## Tools

| Tool | What it does |
| --- | --- |
| `search_tracks` | Search tracks by title, optionally filtered by artist. |
| `search_artists` | Search artists by name. |
| `search_albums` | Search albums by name. |
| `get_tracks` | Get details for up to 40 tracks (by ReccoBeats ID, Spotify ID or ISRC). |
| `get_artists` | Get details for up to 40 artists. |
| `get_albums` | Get details for up to 40 albums. |
| `get_audio_features` | Get audio features (energy, valence, tempo, key, …) for up to 40 tracks. |
| `get_artist_tracks` | List an artist's tracks. |
| `get_artist_albums` | List an artist's albums, singles and compilations. |
| `get_album_tracks` | List the tracks on an album. |
| `get_track_albums` | List the albums a track appears on. |
| `get_recommendations` | Recommend tracks similar to 1–5 seed tracks, optionally steered by target audio features. |
| `extract_audio_features` | Upload a local audio file and return its audio features. |

`extract_audio_features` accepts MP3, OGG (Vorbis), WAV and AIFF/AIFC files up to 5 MB, and the server checks the format from the file's content before uploading. ReccoBeats analyses at most 30 seconds of audio.

## Usage

### Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)

### Install

```sh
git clone <repository-url> reccobeats-mcp
cd reccobeats-mcp
uv sync
```

### Connect your client

Add the following configuration to your MCP client (e.g. Claude Desktop, Claude Code, Cursor or VS Code).

```json
{
  "mcpServers": {
    "reccobeats": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/reccobeats-mcp", "reccobeats-mcp"]
    }
  }
}
```

Restart the client, then ask it something like *"Search ReccoBeats for Bohemian Rhapsody"* to check that it works.

### Run as an HTTP server

By default the client starts the server itself and talks to it over stdio. You can instead run one long-lived server over Streamable HTTP, for example for a remote client or for several clients sharing one process:

```sh
uv run reccobeats-mcp --transport streamable-http
# ReccoBeats MCP server listening on http://127.0.0.1:8000/mcp
```

Then point your client at `http://127.0.0.1:8000/mcp`.

> **Security:** the HTTP endpoint has no authentication. It listens only on your own machine by default. If you bind another address (such as `--host 0.0.0.0`) or expose it through a tunnel, put authentication and rate limiting in front of it. In HTTP mode, `extract_audio_features` reads files from the server's disk, not the caller's.

### Configuration

Options can be set with a command-line flag or an environment variable. If both are set, the flag wins.

| Flag | Environment variable | Default | Description |
| --- | --- | --- | --- |
| `--transport` | `RECCOBEATS_TRANSPORT` | `stdio` | `stdio` or `streamable-http`. |
| `--host` | `RECCOBEATS_HOST` | `127.0.0.1` | Address to listen on in HTTP mode. |
| `--port` | `RECCOBEATS_PORT` | `8000` | Port to listen on in HTTP mode. |
| `--path` | `RECCOBEATS_PATH` | `/mcp` | URL path of the MCP endpoint in HTTP mode. |
| | `RECCOBEATS_BASE_URL` | `https://api.reccobeats.com/v1` | ReccoBeats API base URL. |
| | `RECCOBEATS_TIMEOUT` | `30` | Timeout for ReccoBeats API requests, in seconds. |

To set environment variables from a client configuration, add an `env` block next to `args`:

```json
"env": { "RECCOBEATS_TIMEOUT": "60" }
```

## License and disclaimer

Released under the [MIT License](LICENSE).

This is an independent, community project. It is not affiliated with, endorsed by or sponsored by ReccoBeats. "ReccoBeats" and "Spotify" are names of their respective owners and are used here only to describe what the software works with. Use of the ReccoBeats API is subject to ReccoBeats' own terms.
