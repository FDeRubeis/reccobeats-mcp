import argparse
import os
import sys
from collections.abc import Sequence


def parse_args(argv: Sequence[str] | None = None, env: dict[str, str] | None = None) -> argparse.Namespace:
    """Parse CLI flags."""
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(prog="reccobeats-mcp", description="ReccoBeats MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=env.get("RECCOBEATS_TRANSPORT", "stdio"),
        help="stdio (default; the client launches the server) or streamable-http "
        "(a long-running HTTP server). Env: RECCOBEATS_TRANSPORT",
    )
    parser.add_argument(
        "--host",
        default=env.get("RECCOBEATS_HOST", "127.0.0.1"),
        help="Address to bind in streamable-http mode (default 127.0.0.1). Env: RECCOBEATS_HOST",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=env.get("RECCOBEATS_PORT", "8000"),
        help="Port to bind in streamable-http mode (default 8000). Env: RECCOBEATS_PORT",
    )
    parser.add_argument(
        "--path",
        default=env.get("RECCOBEATS_PATH", "/mcp"),
        help="URL path of the MCP endpoint in streamable-http mode (default /mcp). Env: RECCOBEATS_PATH",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)

    from .server import mcp

    if args.transport == "stdio":
        mcp.run()
        return

    print(f"ReccoBeats MCP server listening on http://{args.host}:{args.port}{args.path}", file=sys.stderr)
    mcp.run("streamable-http", host=args.host, port=args.port, streamable_http_path=args.path)
