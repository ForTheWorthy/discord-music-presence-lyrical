from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from lyrical_presence.consoleutil import configure_windows_console
from lyrical_presence.discord_rpc import DiscordPresence
from lyrical_presence.media import create_media_backend
from lyrical_presence.providers import build_default_fetcher, default_lyrics_dir
from lyrical_presence.service import LyricPresenceService, SyncConfig
from lyrical_presence.symbols import DEFAULT_MUSIC_SYMBOLS

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATHS = (
    Path.cwd() / "lyrical-presence.json",
    Path.home() / ".config" / "lyrical-presence" / "config.json",
)


def load_config(path: Path | None) -> dict:
    candidates = [path] if path else list(DEFAULT_CONFIG_PATHS)
    for candidate in candidates:
        if candidate is None:
            continue
        if candidate.is_file():
            with candidate.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise SystemExit(f"Config file must contain a JSON object: {candidate}")
            log.info("Loaded config from %s", candidate)
            return data
    return {}


class _ConsoleTransport:
    """Dry-run transport that prints presence updates."""

    def update(self, **payload):
        details = payload.get("details")
        state = payload.get("state")
        print(f"[presence] {details} | {state}", flush=True)

    def clear(self):
        print("[presence] cleared", flush=True)

    def close(self):
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lyrical-presence",
        description=(
            "Show the currently playing song's lyrics line-by-line "
            "in Discord Rich Presence."
        ),
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("DISCORD_CLIENT_ID"),
        help="Discord application client ID (or set DISCORD_CLIENT_ID)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional JSON config path",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="How often to poll media playback (seconds)",
    )
    parser.add_argument(
        "--clear-on-pause",
        action="store_true",
        help="Clear Discord presence while media is paused",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Do not show a Discord playback progress bar",
    )
    parser.add_argument(
        "--lyrics-dir",
        type=Path,
        help="Folder of local .lrc files (default: AppData/Lyrical Presence/lyrics)",
    )
    parser.add_argument(
        "--no-album-cover",
        action="store_true",
        help="Do not look up or show album cover art in Discord",
    )
    parser.add_argument(
        "--show-player",
        action="store_true",
        help="Include the media player name in the activity state line",
    )
    parser.add_argument(
        "--status-display",
        choices=("details", "state", "name"),
        default=None,
        help="Which field Discord shows after 'Listening to' (default: details = lyrics)",
    )
    parser.add_argument(
        "--no-music-symbols",
        action="store_true",
        help="Disable ♪/♫ placeholders during instrumentals / missing lyrics",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print lyric updates to the console without connecting to Discord",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_windows_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    # Ensure log lines flush immediately on Windows consoles.
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.DEBUG if args.verbose else logging.INFO)
        flush = getattr(handler, "flush", None)
        stream = getattr(handler, "stream", None)
        if stream is not None:
            try:
                reconfigure = getattr(stream, "reconfigure", None)
                if callable(reconfigure):
                    reconfigure(line_buffering=True, write_through=True)
            except Exception:  # noqa: BLE001
                pass
        if callable(flush):
            flush()

    config = load_config(args.config)
    client_id = args.client_id or config.get("client_id")
    if not args.dry_run and not client_id:
        parser.error(
            "Discord client ID required. Pass --client-id, set DISCORD_CLIENT_ID, "
            "or add client_id to lyrical-presence.json (or use --dry-run)"
        )

    symbols = config.get("music_symbols", list(DEFAULT_MUSIC_SYMBOLS))
    if isinstance(symbols, str):
        symbols = [part for part in symbols.split() if part]
    sync = SyncConfig(
        poll_interval_seconds=float(
            args.poll_interval
            if args.poll_interval is not None
            else config.get("poll_interval_seconds", 0.25)
        ),
        clear_on_pause=bool(args.clear_on_pause or config.get("clear_on_pause", False)),
        show_progress=not bool(args.no_progress or config.get("show_progress") is False),
        show_music_symbols=not bool(
            args.no_music_symbols or config.get("show_music_symbols") is False
        ),
        music_symbols=tuple(symbols) or DEFAULT_MUSIC_SYMBOLS,
        music_symbol_interval_seconds=float(
            config.get("music_symbol_interval_seconds", 1.5)
        ),
        music_symbol_repeat=int(config.get("music_symbol_repeat", 3)),
        lyric_lead_seconds=float(config.get("lyric_lead_seconds", 0.35)),
        show_album_cover=not bool(
            args.no_album_cover or config.get("show_album_cover") is False
        ),
    )

    presence_kwargs = {
        "status_display": str(
            args.status_display or config.get("status_display", "details")
        ).lower(),
        "show_player_in_state": bool(
            args.show_player or config.get("show_player_in_state", False)
        ),
    }
    presence = (
        DiscordPresence(
            str(client_id or "dry-run"),
            transport=_ConsoleTransport(),
            **presence_kwargs,
        )
        if args.dry_run
        else DiscordPresence(str(client_id), **presence_kwargs)
    )
    lyrics_dir = args.lyrics_dir or (
        Path(config["lyrics_dir"]) if config.get("lyrics_dir") else default_lyrics_dir()
    )
    service = LyricPresenceService(
        media=create_media_backend(),
        presence=presence,
        config=sync,
        lyrics_fetcher=build_default_fetcher(lyrics_dir),
    )
    service.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
