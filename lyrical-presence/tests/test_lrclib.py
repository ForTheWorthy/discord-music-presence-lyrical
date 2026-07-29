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
    def __init__(self, handler):
        self.handler = handler
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return self.handler(url, params or {})


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

    def handler(url, params):
        assert "/api/get" in url
        return DummyResponse(200, payload)

    client = LrclibClient(session=DummySession(handler))
    track = Track("Song", "Artist", "Album", duration_seconds=120)
    lyrics = client.fetch_for_track(track)
    assert lyrics is not None
    assert lyrics.has_synced
    assert [line.text for line in lyrics.synced_lines] == ["hello", "world"]


def test_normalizes_apple_music_artist_before_search():
    search_payload = [
        {
            "id": 1,
            "trackName": "Good Life (feat. T-Pain)",
            "artistName": "Kanye West",
            "albumName": "Graduation",
            "duration": 207,
            "instrumental": False,
            "syncedLyrics": "[00:01.00] welcome\n",
            "plainLyrics": "welcome",
        }
    ]

    def handler(url, params):
        if "/api/get" in url:
            return DummyResponse(404, {"code": 404})
        # After normalization, artist should no longer include the album.
        assert params.get("artist_name") == "Kanye West"
        assert params.get("album_name") == "Graduation"
        return DummyResponse(200, search_payload)

    client = LrclibClient(session=DummySession(handler))
    track = Track(
        "Good Life (feat. T-Pain)",
        "Kanye West — Graduation",
        album="",
        duration_seconds=207,
    )
    lyrics = client.fetch_for_track(track)
    assert lyrics is not None
    assert lyrics.synced_lines[0].text == "welcome"


def test_falls_back_to_q_search():
    calls = {"n": 0}

    def handler(url, params):
        calls["n"] += 1
        if "/api/get" in url:
            return DummyResponse(404, {"code": 404})
        if "q" in params:
            return DummyResponse(
                200,
                [
                    {
                        "id": 9,
                        "trackName": "Song",
                        "artistName": "Artist",
                        "albumName": "Album",
                        "duration": 100,
                        "syncedLyrics": "[00:01.00] hi\n",
                        "plainLyrics": "hi",
                    }
                ],
            )
        return DummyResponse(200, [])

    client = LrclibClient(session=DummySession(handler))
    lyrics = client.fetch_for_track(Track("Song", "Artist", "Album", duration_seconds=100))
    assert lyrics is not None
    assert lyrics.synced_lines[0].text == "hi"
