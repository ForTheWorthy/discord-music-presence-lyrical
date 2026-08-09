from __future__ import annotations

import re
from functools import lru_cache

# Common English profanity / slurs for Discord-facing lyric lines.
# Matching is whole-word and case-insensitive. Add extras via config.
_DEFAULT_PROFANITY: frozenset[str] = frozenset(
    {
        "asshole",
        "assholes",
        "bastard",
        "bastards",
        "bitch",
        "bitches",
        "bitching",
        "bullshit",
        "cock",
        "cocks",
        "cocksucker",
        "cunt",
        "cunts",
        "damn",
        "damned",
        "dammit",
        "dick",
        "dicks",
        "dickhead",
        "dumbass",
        "fag",
        "faggot",
        "fuck",
        "fucked",
        "fucker",
        "fuckers",
        "fuckin",
        "fucking",
        "motherfucker",
        "motherfuckers",
        "motherfucking",
        "nigga",
        "niggas",
        "nigger",
        "piss",
        "pissed",
        "pussy",
        "shit",
        "shits",
        "shitty",
        "slut",
        "sluts",
        "tit",
        "tits",
        "whore",
        "whores",
    }
)


def default_profanity_words() -> frozenset[str]:
    return _DEFAULT_PROFANITY


def mask_word(word: str, mask: str = "*") -> str:
    """Keep the first character; replace the rest (e.g. fuck → f***)."""
    if not word:
        return word
    if not mask:
        mask = "*"
    ch = mask[0]
    if len(word) == 1:
        return ch
    return word[0] + (ch * (len(word) - 1))


@lru_cache(maxsize=32)
def _compiled_pattern(words_key: tuple[str, ...]) -> re.Pattern[str] | None:
    if not words_key:
        return None
    # Longer phrases first so "motherfucker" wins over "fuck".
    escaped = [re.escape(word) for word in sorted(words_key, key=len, reverse=True)]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def censor_text(
    text: str,
    *,
    enabled: bool = True,
    words: frozenset[str] | set[str] | tuple[str, ...] | None = None,
    extra_words: frozenset[str] | set[str] | tuple[str, ...] | list[str] | None = None,
    mask: str = "*",
) -> str:
    """Replace whole-word profanity in ``text`` with a masked form."""
    if not enabled or not text:
        return text

    word_set = set(words) if words is not None else set(_DEFAULT_PROFANITY)
    if extra_words:
        word_set.update(w.strip().lower() for w in extra_words if w and w.strip())
    word_set = {w.lower() for w in word_set if w}

    pattern = _compiled_pattern(tuple(sorted(word_set)))
    if pattern is None:
        return text

    def _replace(match: re.Match[str]) -> str:
        return mask_word(match.group(0), mask=mask)

    return pattern.sub(_replace, text)
