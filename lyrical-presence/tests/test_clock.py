from lyrical_presence.clock import PlaybackClock
from lyrical_presence.models import Track


def test_playback_clock_extrapolates_when_os_position_is_stale():
    clock = PlaybackClock()
    first = Track("Song", "Artist", duration_seconds=100, position_seconds=10.0, playing=True)
    resolved = clock.resolve(first, now=100.0)
    assert resolved.position_seconds == 10.0

    stale = Track("Song", "Artist", duration_seconds=100, position_seconds=10.0, playing=True)
    resolved = clock.resolve(stale, now=100.8)
    assert abs(resolved.position_seconds - 10.8) < 0.001


def test_playback_clock_resyncs_on_seek():
    clock = PlaybackClock()
    clock.resolve(
        Track("Song", "Artist", duration_seconds=100, position_seconds=10.0, playing=True),
        now=50.0,
    )
    seeked = Track("Song", "Artist", duration_seconds=100, position_seconds=40.0, playing=True)
    resolved = clock.resolve(seeked, now=50.5)
    assert resolved.position_seconds == 40.0


def test_playback_clock_resets_on_track_change():
    clock = PlaybackClock()
    clock.resolve(
        Track("Song A", "Artist", duration_seconds=100, position_seconds=20.0, playing=True),
        now=10.0,
    )
    other = Track("Song B", "Artist", duration_seconds=100, position_seconds=1.0, playing=True)
    resolved = clock.resolve(other, now=12.0)
    assert resolved.position_seconds == 1.0
