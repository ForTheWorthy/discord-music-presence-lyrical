from lyrical_presence.lrc import line_at, parse_lrc
from lyrical_presence.models import LyricLine


def test_parse_lrc_basic():
    raw = """
    [00:12.00] First line
    [00:15.50] Second line
    [01:02.123] Third line
    """
    lines = parse_lrc(raw)
    assert lines == (
        LyricLine(12.0, "First line"),
        LyricLine(15.5, "Second line"),
        LyricLine(62.123, "Third line"),
    )


def test_parse_lrc_skips_empty_and_metadata():
    raw = """
    [ar:Artist]
    [00:01.00]
    [00:02.00] Hello
    not a lyric
    """
    lines = parse_lrc(raw)
    assert lines == (LyricLine(2.0, "Hello"),)


def test_line_at_selects_current_and_holds():
    lines = (
        LyricLine(1.0, "one"),
        LyricLine(5.0, "two"),
        LyricLine(9.0, "three"),
    )
    assert line_at(lines, 0.5) is None
    assert line_at(lines, 1.0).text == "one"
    assert line_at(lines, 4.9).text == "one"
    assert line_at(lines, 5.0).text == "two"
    assert line_at(lines, 100.0).text == "three"


def test_parse_lrc_empty():
    assert parse_lrc(None) == ()
    assert parse_lrc("") == ()
    assert parse_lrc("   ") == ()
