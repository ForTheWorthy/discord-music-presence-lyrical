from lyrical_presence.censor import censor_text, mask_word
from lyrical_presence.discord_rpc import DiscordPresence
from lyrical_presence.lrclib import LrclibClient
from lyrical_presence.media import StaticTrackBackend
from lyrical_presence.models import Lyrics, LyricLine, Track
from lyrical_presence.service import LyricPresenceService, SyncConfig


def test_mask_word_keeps_first_letter():
    assert mask_word("fuck") == "f***"
    assert mask_word("a") == "*"
    assert mask_word("shit", mask="#") == "s###"


def test_censor_text_masks_whole_words_only():
    assert censor_text("This is bullshit and classy") == "This is b******* and classy"
    assert censor_text("Fuck the system") == "F*** the system"
    assert censor_text("motherfucker") == "m***********"


def test_censor_text_can_be_disabled():
    assert censor_text("fuck this", enabled=False) == "fuck this"


def test_censor_text_supports_extra_words():
    assert censor_text("heck yeah", extra_words=("heck",)) == "h*** yeah"


def test_service_censors_profanity_in_discord_details():
    lines = (LyricLine(0.0, "what the fuck"),)
    lyrics = Lyrics(
        track_name="Song",
        artist_name="Artist",
        album_name="Album",
        duration=100,
        instrumental=False,
        synced_lines=lines,
    )

    def provider():
        return Track(
            title="Song",
            artist="Artist",
            duration_seconds=100,
            position_seconds=1.0,
            playing=True,
        )

    class FakeTransport:
        def __init__(self):
            self.updates = []

        def update(self, **payload):
            self.updates.append(payload)

        def clear(self):
            pass

        def close(self):
            pass

    class FakeLyricsClient(LrclibClient):
        def __init__(self):
            pass

        def fetch_for_track(self, track):
            return lyrics

    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    service = LyricPresenceService(
        media=StaticTrackBackend(provider),
        lyrics_client=FakeLyricsClient(),
        presence=presence,
        config=SyncConfig(
            show_progress=False,
            show_album_cover=False,
            lyric_lead_seconds=0,
            discord_min_interval_seconds=0,
            censor_profanity=True,
        ),
    )
    service.tick()
    assert transport.updates[0]["details"] == "what the f***"


def test_service_can_disable_censor():
    lines = (LyricLine(0.0, "what the fuck"),)
    lyrics = Lyrics(
        track_name="Song",
        artist_name="Artist",
        album_name="Album",
        duration=100,
        instrumental=False,
        synced_lines=lines,
    )

    def provider():
        return Track(
            title="Song",
            artist="Artist",
            duration_seconds=100,
            position_seconds=1.0,
            playing=True,
        )

    class FakeTransport:
        def __init__(self):
            self.updates = []

        def update(self, **payload):
            self.updates.append(payload)

        def clear(self):
            pass

        def close(self):
            pass

    class FakeLyricsClient(LrclibClient):
        def __init__(self):
            pass

        def fetch_for_track(self, track):
            return lyrics

    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    service = LyricPresenceService(
        media=StaticTrackBackend(provider),
        lyrics_client=FakeLyricsClient(),
        presence=presence,
        config=SyncConfig(
            show_progress=False,
            show_album_cover=False,
            lyric_lead_seconds=0,
            discord_min_interval_seconds=0,
            censor_profanity=False,
        ),
    )
    service.tick()
    assert transport.updates[0]["details"] == "what the fuck"
