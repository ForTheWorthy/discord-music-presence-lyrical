from lyrical_presence.consoleutil import configure_windows_console


def test_configure_windows_console_is_safe_on_non_windows(monkeypatch):
    monkeypatch.setattr("lyrical_presence.consoleutil.sys.platform", "linux")
    # Should no-op without raising.
    configure_windows_console()
