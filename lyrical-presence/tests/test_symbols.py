from lyrical_presence.symbols import format_music_only, music_symbol_at


def test_music_symbol_cycles_with_position():
    symbols = ("♪", "♫", "♬")
    assert music_symbol_at(0.0, symbols, 1.5) == "♪"
    assert music_symbol_at(1.5, symbols, 1.5) == "♫"
    assert music_symbol_at(3.0, symbols, 1.5) == "♬"
    assert music_symbol_at(4.5, symbols, 1.5) == "♪"


def test_format_music_only_repeats_symbol():
    assert format_music_only(0.0, ("♪",), 1.0, repeat=3) == "♪ ♪ ♪"
    assert format_music_only(2.0, ("♫", "♬"), 2.0, repeat=2) == "♬ ♬"
