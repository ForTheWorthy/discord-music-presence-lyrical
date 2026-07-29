from lyrical_presence.lrclib import LrclibClient
from lyrical_presence.models import Track


class DummyResponse:
    def __init__(self, status_code: int, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return self.responses.pop(0)


def test_exact_lookup_parses_synced_lyrics():
    payload = {
        "trackName": "Song",
        "artistName": "Artist",
        "albumName": "Album",
        "duration": 120,
        "instrumental": False,
        "plainLyrics": "hello\nworld",
        "syncedLyrics": "[00:01.00] hello\n[00:02.00] world\n",
    }
    session = DummySession([DummyResponse(200, payload)])
    client = LrclibClient(session=session)
    track = Track("Song", "Artist", "Album", duration_seconds=120)
    lyrics = client.fetch_for_track(track)
    assert lyrics is not None
    assert lyrics.has_synced
    assert [line.text for line in lyrics.synced_lines] == ["hello", "world"]


def test_falls_back_to_search_when_exact_missing():
    search_payload = [
        {
            "trackName": "Song",
            "artistName": "Artist",
            "albumName": "Album",
            "duration": 121,
            "instrumental": False,
            "syncedLyrics": "[00:01.00] hello\n",
            "plainLyrics": "hello",
        }
    ]
    session = DummySession(
        [
            DummyResponse(404, {"code": 404}),
            DummyResponse(200, search_payload),
        ]
    )
    client = LrclibClient(session=session)
    track = Track("Song", "Artist", "Album", duration_seconds=120)
    lyrics = client.fetch_for_track(track)
    assert lyrics is not None
    assert lyrics.synced_lines[0].text == "hello"
    assert len(session.calls) == 2


def test_score_prefers_duration_and_synced():
    track = Track("Song", "Artist", "Album", duration_seconds=200)
    good = {
        "trackName": "Song",
        "artistName": "Artist",
        "albumName": "Album",
        "duration": 201,
        "syncedLyrics": "[00:01.00] x",
    }
    bad = {
        "trackName": "Song",
        "artistName": "Someone Else",
        "albumName": "Other",
        "duration": 90,
        "syncedLyrics": None,
    }
    assert LrclibClient._score_result(good, track) > LrclibClient._score_result(bad, track)
