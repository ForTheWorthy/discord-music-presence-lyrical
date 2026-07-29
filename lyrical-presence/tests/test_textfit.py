from lyrical_presence.textfit import split_lyric_chunks, split_lyric_for_presence


def test_split_lyric_chunks_wraps_on_words():
    text = "Like we always do at this time I look so lonely"
    chunks = split_lyric_chunks(text, 20)
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert " ".join(chunks) == text


def test_split_lyric_chunks_hard_splits_long_words():
    chunks = split_lyric_chunks("supercalifragilisticexpialidocious", 10)
    assert chunks == ("supercalif", "ragilistic", "expialidoc", "ious")


def test_split_lyric_for_presence_keeps_short_lines_on_details_only():
    details, state = split_lyric_for_presence("short lyric", first_line_chars=40)
    assert details == "short lyric"
    assert state is None


def test_split_lyric_for_presence_puts_overflow_on_state():
    text = "Like we always do at this time I look so lonely nevertheless"
    details, state = split_lyric_for_presence(text, first_line_chars=24)
    assert len(details) <= 24
    assert state is not None
    assert details in text
    assert state in text
    assert f"{details} {state}" == text or text.startswith(details)
