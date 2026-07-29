from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def configure_windows_console() -> None:
    """Avoid the Windows console freezing the app until the user clicks/types.

    Windows Quick Edit Mode pauses console apps when the window is selected
    for text selection. Disable it and prefer line-buffered stdout so logs
    appear promptly.
    """
    if sys.platform != "win32":
        return

    _disable_quick_edit_mode()
    _enable_line_buffered_stdio()


def _disable_quick_edit_mode() -> None:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # STD_INPUT_HANDLE = -10
        handle = kernel32.GetStdHandle(-10)
        if handle in (0, -1):
            return

        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return

        enable_extended_flags = 0x0080
        enable_quick_edit_mode = 0x0040
        enable_mouse_input = 0x0010

        new_mode = mode.value
        new_mode &= ~enable_quick_edit_mode
        new_mode &= ~enable_mouse_input
        new_mode |= enable_extended_flags

        if new_mode != mode.value:
            if kernel32.SetConsoleMode(handle, new_mode):
                log.debug("Disabled Windows console Quick Edit Mode")
            else:
                log.debug("Could not disable Quick Edit Mode (SetConsoleMode failed)")
    except Exception as exc:  # noqa: BLE001 - best-effort console tweak
        log.debug("Could not adjust Windows console mode: %s", exc)


def _enable_line_buffered_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(line_buffering=True, write_through=True)
        except Exception:  # noqa: BLE001
            continue
