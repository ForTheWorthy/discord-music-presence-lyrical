from lyrical_presence.covers import CoverArtClient
from lyrical_presence.models import Track


class DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return DummyResponse(200, self.payload)


def test_cover_client_upsamples_itunes_artwork():
    payload = {
        "results": [
            {
                "trackName": "Good Life (feat. T-Pain)",
                "artistName": "Kanye West",
                "collectionName": "Graduation",
                "artworkUrl100": "https://example.com/cover/100x100bb.jpg",
            }
        ]
    }
    client = CoverArtClient(session=DummySession(payload))
    url = client.cover_url_for(
        Track("Good Life (feat. T-Pain)", "Kanye West", "Graduation")
    )
    assert url == "https://example.com/cover/600x600bb.jpg"
    # Cached on second call.
    assert client.cover_url_for(
        Track("Good Life (feat. T-Pain)", "Kanye West", "Graduation")
    ) == url
    assert len(client.session.calls) == 1


def test_cover_client_returns_none_when_empty():
    client = CoverArtClient(session=DummySession({"results": []}))
    assert client.cover_url_for(Track("Song", "Artist", "Album")) is None
