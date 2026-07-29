# Lyrical Presence

Companion for [Music Presence](https://github.com/ungive/discord-music-presence) that shows **synced lyrics line-by-line** in Discord Rich Presence.

Music Presence itself is closed-source (this GitHub repo only ships docs and release assets). This companion reads whatever your OS reports as currently playing, fetches timed lyrics from [LRCLIB](https://lrclib.net), and updates Discord as each lyric line becomes active.

## What friends see

Discord activity fields:

| Field | Content |
| --- | --- |
| **Details** (first line) | Current lyric line, or cycling `♪ ♪ ♪` during instrumentals / missing lyrics |
| **State** (second line) | `Artist — Song · Player` |
| Activity type | Listening |

When synced lyrics are unavailable — or during intros / instrumental gaps — details show music symbols (`♪` `♫` `♬` `♩`) instead of an empty line.

## Requirements

- Python 3.10+
- Discord desktop app running on the same machine
- A Discord Application **Client ID** ([Developer Portal](https://discord.com/developers/applications) → New Application → copy Application ID)
- Media detection:
  - **Linux:** [`playerctl`](https://github.com/altdesktop/playerctl) (`sudo apt install playerctl`)
  - **Windows:** `pip install winsdk` (uses System Media Transport Controls)
  - **macOS:** Apple Music via `osascript` (other players may vary)

## Install

```bash
cd lyrical-presence
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Configure

1. Create a Discord application and copy its Application ID.
2. Copy the example config:

```bash
cp lyrical-presence.example.json lyrical-presence.json
```

3. Set `client_id` in that file, **or** export `DISCORD_CLIENT_ID`, **or** pass `--client-id`.

Optional: under Discord Developer Portal → your app → Rich Presence → Art Assets, you can add images later; lyrics work without them.

## Run

```bash
lyrical-presence --client-id YOUR_APPLICATION_ID -v
```

Play a song in any media player your OS exposes (Spotify, browsers with MPRIS/SMTC, VLC, etc.). When timed lyrics are found, Discord updates on each new line.

### Useful flags

| Flag | Meaning |
| --- | --- |
| `--poll-interval 0.5` | Poll media position more often |
| `--clear-on-pause` | Hide presence while paused |
| `--no-progress` | Disable Discord progress timestamps |
| `--no-music-symbols` | Disable ♪/♫ placeholders for instrumentals |
| `--dry-run` | Print lyric updates without connecting to Discord |
| `--config path.json` | Custom config path |
| `-v` | Debug logging |

## Using with Music Presence

Both apps can run at once because they use **different Discord application IDs**. Discord may show multiple activities; which one is featured depends on Discord client settings.

If you only want lyrics in your status, pause/disable Music Presence while Lyrical Presence runs.

## Privacy

- Lyrics are requested from `lrclib.net` using track title, artist, album, and duration.
- Nothing is uploaded to Discord except the Rich Presence payload (lyric line + track labels).
- No Discord user token is used (official local RPC only).

## Development

```bash
pytest
```

## Project layout

```
lyrical-presence/
  src/lyrical_presence/
    lrc.py           # LRC parser + line lookup
    lrclib.py        # LRCLIB API client
    media.py         # OS media backends
    discord_rpc.py   # Discord Rich Presence updates
    service.py       # Sync loop
    cli.py           # Entry point
  tests/
```
