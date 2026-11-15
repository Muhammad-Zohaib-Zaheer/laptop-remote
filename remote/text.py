"""Small helpers for understanding spoken text: words, numbers, names, durations."""
from __future__ import annotations

import difflib
import re

SMALL = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
UNITS = {"second": 1, "minute": 60, "hour": 3600}
LONGEST_NAME = 4                     # words; "visual studio code" has three
HALF = 0.5


def clean(text: str) -> list[str]:
    """Lower-case words without punctuation: "Hey, Computer!" -> [hey, computer]."""
    return re.findall(r"[\w']+", text.lower().replace("_", " "))


def digits(text: str) -> str:
    """Spoken numbers as digits: "twenty five minutes" -> "25 minutes"."""
    out: list[str] = []
    for word in clean(text):
        last = int(out[-1]) if out and out[-1].isdigit() else None
        if word in SMALL:
            value = SMALL.index(word)
            if last in range(20, 100, 10) and 0 < value < 10:
                out[-1] = str(last + value)              # twenty + five
            else:
                out.append(str(value))
        elif word in TENS:
            out.append(str((TENS.index(word) + 2) * 10))
        elif word == "hundred":
            out[-1:] = [str(last * 100)] if last in range(1, 10) else out[-1:] + ["100"]
        else:
            out.append(word)
    return " ".join(out)


def seconds_in(text: str) -> int:
    """Length of a spoken duration: "a minute and 30 seconds" -> 90."""
    text = digits(text).replace("half an hour", "30 minutes").replace("half a minute", "30 seconds")
    text = re.sub(r"\b(a|an) (second|minute|hour)", r"1 \2", text)
    return sum(int(n) * UNITS[unit] for n, unit in re.findall(r"(\d+) (second|minute|hour)", text))


def span(seconds: int) -> str:
    """A duration the way it is said: 90 -> "1 minute 30 seconds"."""
    parts = []
    for unit, size in sorted(UNITS.items(), key=lambda item: -item[1]):
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count} {unit}{'s' if count != 1 else ''}")
    return " ".join(parts)


def close(a: str, b: str) -> bool:
    """The same word, allowing for a slip of speech recognition ("crome", "chrome")."""
    if a == b:
        return True
    # The cheap checks first: comparing letter by letter is the slow part.
    return (a[0] == b[0] and abs(len(a) - len(b)) <= 2
            and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8)


def best_match(said: str, names) -> tuple[str | None, float]:
    """The name that contains every spoken word, and how much of that name was said.

    Of several names, the one said most completely wins: "chrome" is all of the
    nickname "chrome" but only half of "Chrome Remote Desktop".
    """
    wanted = clean(said)
    best, most = None, 0.0
    for name in names:
        parts = clean(name.replace("-", " "))
        if all(any(close(a, b) for b in parts) for a in wanted) and len(wanted) / len(parts) > most:
            best, most = name, len(wanted) / len(parts)
    return best, most


def find_name(said: str, names) -> str | None:
    """A known name mentioned anywhere in a sentence, or None.

    Every run of up to four words is tried. "get the calculator on screen"
    finds Calculator (said completely) rather than On-Screen Keyboard (two of
    its three words).
    """
    words = clean(said)
    found, rank = None, (0.0, 0)
    for size in range(min(LONGEST_NAME, len(words)), 0, -1):
        for start in range(len(words) - size + 1):
            name, said_share = best_match(" ".join(words[start:start + size]), names)
            # At least half of a name must be said: the word "on" in a
            # sentence is not a request for the On-Screen Keyboard.
            if name and said_share >= HALF and (said_share, size) > rank:
                found, rank = name, (said_share, size)
    return found
