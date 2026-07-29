from lyrical_presence.textfit import chunk_at_progress, split_lyric_chunks


def test_split_lyric_chunks_wraps_on_words():
    text = "Like we always do at this time I look so lonely"
    chunks = split_lyric_chunks(text, 20)
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert " ".join(chunks) == text


def test_split_lyric_chunks_hard_splits_long_words():
    chunks = split_lyric_chunks("supercalifragilisticexpialidocious", 10)
    assert chunks == ("supercalif", "ragilistic", "expialidoc", "ious")


def test_chunk_at_progress_cycles_through_window():
    chunks = ("one", "two", "three")
    assert chunk_at_progress(chunks, elapsed_seconds=0.0, window_seconds=9) == "one"
    assert chunk_at_progress(chunks, elapsed_seconds=3.0, window_seconds=9) == "two"
    assert chunk_at_progress(chunks, elapsed_seconds=6.0, window_seconds=9) == "three"
    assert chunk_at_progress(chunks, elapsed_seconds=100.0, window_seconds=9) == "three"
