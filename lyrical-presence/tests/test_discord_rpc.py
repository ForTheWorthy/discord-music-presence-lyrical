import logging

from lyrical_presence.discord_rpc import DiscordPresence
from lyrical_presence.models import Track


class FakeTransport:
    def __init__(self):
        self.updates = []
        self.fail_next = False

    def update(self, **payload):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("boom")
        self.updates.append(payload)

    def clear(self):
        pass

    def close(self):
        pass


def test_update_lyrics_reports_sent_then_skipped_unchanged():
    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    presence.connect()
    track = Track("Song", "Artist", playing=True)

    assert presence.update_lyrics(track, "hello", show_progress=False) == "sent"
    assert len(transport.updates) == 1

    assert presence.update_lyrics(track, "hello", show_progress=False) == "skipped_unchanged"
    assert len(transport.updates) == 1


def test_update_lyrics_reports_failed(caplog):
    transport = FakeTransport()
    presence = DiscordPresence("123", transport=transport)
    presence.connect()
    track = Track("Song", "Artist", playing=True)
    transport.fail_next = True

    with caplog.at_level(logging.WARNING):
        assert presence.update_lyrics(track, "hello", show_progress=False) == "failed"
    assert transport.updates == []
