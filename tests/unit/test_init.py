import pytest

from reccobeats_mcp import main, parse_args, server


class TestParseArgs:
    def test_defaults_to_stdio(self):
        args = parse_args([], env={})
        assert args.transport == "stdio"
        assert args.host == "127.0.0.1"
        assert args.port == 8000
        assert args.path == "/mcp"

    def test_flags(self):
        args = parse_args(
            ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000", "--path", "/x"],
            env={},
        )
        assert (args.transport, args.host, args.port, args.path) == ("streamable-http", "0.0.0.0", 9000, "/x")

    def test_env_fallback(self):
        env = {
            "RECCOBEATS_TRANSPORT": "streamable-http",
            "RECCOBEATS_HOST": "::1",
            "RECCOBEATS_PORT": "1234",
            "RECCOBEATS_PATH": "/y",
        }
        args = parse_args([], env=env)
        assert (args.transport, args.host, args.port, args.path) == ("streamable-http", "::1", 1234, "/y")

    def test_flag_overrides_env(self):
        args = parse_args(["--transport", "stdio"], env={"RECCOBEATS_TRANSPORT": "streamable-http"})
        assert args.transport == "stdio"

    def test_rejects_unknown_transport(self):
        with pytest.raises(SystemExit):
            parse_args(["--transport", "carrier-pigeon"], env={})

    def test_rejects_non_numeric_port_from_env(self):
        with pytest.raises(SystemExit):
            parse_args([], env={"RECCOBEATS_PORT": "abc"})


class TestMain:
    @pytest.fixture
    def run_calls(self, monkeypatch):
        for var in ("RECCOBEATS_TRANSPORT", "RECCOBEATS_HOST", "RECCOBEATS_PORT", "RECCOBEATS_PATH"):
            monkeypatch.delenv(var, raising=False)
        calls = []
        monkeypatch.setattr(server.mcp, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
        return calls

    def test_stdio(self, run_calls):
        main([])
        assert run_calls == [((), {})]

    def test_streamable_http(self, run_calls, capsys):
        main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9001", "--path", "/m"])
        assert run_calls == [
            (("streamable-http",), {"host": "0.0.0.0", "port": 9001, "streamable_http_path": "/m"})
        ]
        assert "http://0.0.0.0:9001/m" in capsys.readouterr().err
