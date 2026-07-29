# Lyrical Presence

Companion for [Music Presence](https://github.com/ungive/discord-music-presence) that shows **synced lyrics line-by-line** in Discord Rich Presence.

Music Presence itself is closed-source (this GitHub repo only ships docs and release assets). This companion reads whatever your OS reports as currently playing, fetches timed lyrics from [LRCLIB](https://lrclib.net), and updates Discord as each lyric line becomes active.

## What friends see

Discord activity fields:

| Field | Content |
| --- | --- |
| **Listening to** | Current lyric line (or `♪ ♪ ♪` during instrumentals) |
| **Details** (first line) | Current lyric line / music symbols |
| **State** (second line) | `Artist — Song` |
| **State** (second line) | `Artist — Song` |
| **Large image** | Album cover (looked up via iTunes Search) |
| Activity type | Listening |

Discord normally shows **Listening to &lt;your app name&gt;**. This companion sets Discord's status display to the **details** field and also sets the activity `name` to the lyric, so friends see **Listening to &lt;lyric line&gt;** instead. Album artwork is fetched from the public iTunes Search API and passed to Discord as an external image URL (replacing the default app/question-mark icon).

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

If lyrics still feel a bit late, raise `lyric_lead_seconds` in the config (e.g. `0.75`) so lines switch slightly early to offset Discord update latency.

## Run

```bash
lyrical-presence --client-id YOUR_APPLICATION_ID -v
```

Play a song in any media player your OS exposes (Spotify, browsers with MPRIS/SMTC, VLC, etc.). When timed lyrics are found, Discord updates on each new line.

### Windows tip

If updates seem to pause until you click or type in the console window, that is Windows **Quick Edit Mode**. Lyrical Presence disables it on startup. You can also turn it off permanently: open the console menu (title-bar icon) → Properties → Options → uncheck **Quick Edit Mode**.

### Useful flags

| Flag | Meaning |
| --- | --- |
| `--poll-interval 0.1` | How often to poll media / refresh lyrics (default 0.1s) |
| `--clear-on-pause` | Hide presence while paused |
| `--no-progress` | Disable Discord progress timestamps |
| `--lyrics-dir path` | Folder of local `.lrc` overrides |
| `--no-album-cover` | Disable album cover lookup / display |
| `--status-display details` | Field used after "Listening to" (`details` = lyrics, default) |
| `--show-player` | Append the media player name to the state line |
| `--no-music-symbols` | Disable ♪/♫ placeholders for instrumentals |
| `--dry-run` | Print lyric updates without connecting to Discord |
| `--config path.json` | Custom config path |
| `-v` | Debug logging |

## Using with Music Presence

Both apps can run at once because they use **different Discord application IDs**. Discord may show multiple activities; which one is featured depends on Discord client settings.

If you only want lyrics in your status, pause/disable Music Presence while Lyrical Presence runs.

## Lyrics sources

Lyrical Presence cannot read Apple Music’s private lyric stream directly, but Apple Music
licenses lyrics from **Musixmatch**, so we query Musixmatch as well. Lookup order:

1. **Local `.lrc` files** in `%APPDATA%\Lyrical Presence\lyrics`  
   Name them like `Artist - Song Title.lrc`
2. **Musixmatch** (same lyric catalog Apple Music uses)
3. **[LRCLIB](https://lrclib.net)**
4. **NetEase Cloud Music** search (extra synced LRC fallback)

Optional: set `musixmatch_token` in config / `MUSIXMATCH_TOKEN` if automatic token fetch is rate-limited.

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
