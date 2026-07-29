from pathlib import Path

from lyrical_presence.models import Lyrics, LyricLine, Track
from lyrical_presence.providers import LocalLrcProvider, LyricsFetcher, MusixmatchClient, NetEaseClient


class DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, mapping):
        self.mapping = mapping
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        for key, payload in self.mapping.items():
            if key in url:
                return DummyResponse(200, payload)
        return DummyResponse(404, {})


def test_lyrics_fetcher_falls_back_to_second_provider():
    class Empty:
        name = "empty"

        def fetch_for_track(self, track):
            return None

    class Hit:
        name = "hit"

        def fetch_for_track(self, track):
            return Lyrics(
                track_name=track.title,
                artist_name=track.artist,
                album_name=track.album,
                duration=None,
                instrumental=False,
                synced_lines=(LyricLine(1.0, "hello"),),
            )

    fetcher = LyricsFetcher([Empty(), Hit()])
    lyrics = fetcher.fetch_for_track(Track("Song", "Artist"))
    assert lyrics is not None
    assert lyrics.synced_lines[0].text == "hello"


def test_local_lrc_provider_reads_file(tmp_path: Path):
    path = tmp_path / "Artist - Song.lrc"
    path.write_text("[00:01.00] hello\n[00:02.00] world\n", encoding="utf-8")
    provider = LocalLrcProvider(tmp_path)
    lyrics = provider.fetch_for_track(Track("Song", "Artist"))
    assert lyrics is not None
    assert [line.text for line in lyrics.synced_lines] == ["hello", "world"]


def test_musixmatch_client_parses_search_and_subtitle():
    session = DummySession(
        {
            "track.search": {
                "message": {
                    "header": {"status_code": 200},
                    "body": {
                        "track_list": [
                            {
                                "track": {
                                    "track_id": 99,
                                    "track_name": "Song",
                                    "artist_name": "Artist",
                                    "album_name": "Album",
                                    "track_length": 120,
                                    "has_subtitles": 1,
                                }
                            }
                        ]
                    },
                }
            },
            "track.subtitle.get": {
                "message": {
                    "header": {"status_code": 200},
                    "body": {
                        "subtitle": {
                            "subtitle_body": "[00:01.00] hello\n[00:02.00] world\n"
                        }
                    },
                }
            },
        }
    )
    from lyrical_presence.providers import MusixmatchClient

    client = MusixmatchClient(session=session, user_token="test-token")
    lyrics = client.fetch_for_track(
        Track("Song", "Artist", "Album", duration_seconds=120)
    )
    assert lyrics is not None
    assert lyrics.synced_lines[0].text == "hello"


def test_netease_client_parses_search_and_lrc():
    session = DummySession(
        {
            "search/get/web": {
                "result": {
                    "songs": [
                        {
                            "id": 42,
                            "name": "Song",
                            "artists": [{"name": "Artist"}],
                            "album": {"name": "Album"},
                            "duration": 120000,
                        }
                    ]
                }
            },
            "song/lyric": {"lrc": {"lyric": "[00:01.00] hello\n[00:02.00] world\n"}},
        }
    )
    client = NetEaseClient(session=session)
    lyrics = client.fetch_for_track(
        Track("Song", "Artist", "Album", duration_seconds=120)
    )
    assert lyrics is not None
    assert lyrics.synced_lines[0].text == "hello"
