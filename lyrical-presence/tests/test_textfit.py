from lyrical_presence.textfit import split_lyric_chunks


def test_split_lyric_chunks_wraps_on_words():
    text = "Like we always do at this time I look so lonely"
    chunks = split_lyric_chunks(text, 20)
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert " ".join(chunks) == text


def test_split_lyric_chunks_hard_splits_long_words():
    chunks = split_lyric_chunks("supercalifragilisticexpialidocious", 10)
    assert chunks == ("supercalif", "ragilistic", "expialidoc", "ious")
