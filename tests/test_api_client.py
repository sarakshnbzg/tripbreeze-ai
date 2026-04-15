"""Tests for presentation/api_client.py."""

from presentation import api_client


class DummyResponse:
    def __init__(self, *, json_payload=None, lines=None):
        self._json_payload = json_payload or {}
        self._lines = lines or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_payload

    def iter_lines(self):
        for line in self._lines:
            yield line


class DummyClient:
    def __init__(self, timeout=None):
        self.timeout = timeout
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, files=None):
        self.calls.append(("post", url, json, files))
        if files is not None:
            return DummyResponse(json_payload={"text": "hello world"})
        return DummyResponse(json_payload={"ok": True})

    def get(self, url):
        self.calls.append(("get", url))
        return DummyResponse(json_payload={"thread_id": "abc"})

    def stream(self, method, url, json=None):
        self.calls.append(("stream", method, url, json))
        return DummyResponse(
            lines=[
                "event: node_start",
                'data: {"label":"Planning"}',
                "",
                "event: done",
                'data: {"status":"ok"}',
                "",
            ]
        )


class TestParseSSELines:
    def test_parses_multiple_events(self):
        events = list(
            api_client._parse_sse_lines(
                [
                    "event: node_start",
                    'data: {"label":"Planning"}',
                    "",
                    "event: done",
                    'data: {"status":"ok"}',
                    "",
                ]
            )
        )

        assert events == [
            ("node_start", {"label": "Planning"}),
            ("done", {"status": "ok"}),
        ]

    def test_falls_back_to_raw_text_for_invalid_json(self):
        events = list(
            api_client._parse_sse_lines(
                [
                    "event: message",
                    "data: not-json",
                    "",
                ]
            )
        )

        assert events == [("message", {"raw": "not-json"})]


class TestAPIClientRequests:
    def test_transcribe_audio_posts_file_and_returns_text(self, monkeypatch):
        created = []

        def fake_client(timeout=None):
            client = DummyClient(timeout=timeout)
            created.append(client)
            return client

        monkeypatch.setattr(api_client.httpx, "Client", fake_client)

        result = api_client.transcribe_audio(b"audio-bytes", filename="clip.wav")

        assert result == "hello world"
        call = created[0].calls[0]
        assert call[0] == "post"
        assert call[3]["file"][0] == "clip.wav"

    def test_stream_search_parses_sse_response(self, monkeypatch):
        monkeypatch.setattr(api_client.httpx, "Client", lambda timeout=None: DummyClient(timeout=timeout))

        events = list(api_client.stream_search({"free_text_query": "Paris"}))

        assert events[0] == ("node_start", {"label": "Planning"})
        assert events[1] == ("done", {"status": "ok"})

    def test_get_state_returns_json(self, monkeypatch):
        monkeypatch.setattr(api_client.httpx, "Client", lambda timeout=None: DummyClient(timeout=timeout))

        result = api_client.get_state("abc")

        assert result == {"thread_id": "abc"}
