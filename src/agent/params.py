"""What a typed sentence is allowed to change.

Every tool in the registry declares the arguments it takes, and until this file existed none of
them could hear them: both planners decided *which* tools to run and then handed each one ``{}``,
so "put this in spanish and do not translate GlucoLove" ran The Translator against whatever she had
last ticked on the Languages page, and "give me 5 cunty ones for tiktok" ran the Writer with the
saved defaults. Seventeen tools had a parameter surface that nothing in the app could reach.

The rule is the one the rest of the app keeps to itself: an argument is set only on evidence in the
sentence, and the evidence has to be a word that **names** the value - a language, a platform, a
tone, a look, a date, a count, a line inside quotation marks. Nothing here reads a subject, a topic
or a version body out of a noun it recognised, because a caption about the thing this app inferred is
a line she has to read and then explain. An argument that is not found stays absent, and the tool's
own fallback - the staged post, the interview, her saved defaults, or the refusal that names what is
missing - runs exactly as it did before this file existed.

``FINDERS`` is keyed by argument name, not by tool, because three tools ask for ``platform`` and
none of them should have its own copy of what "ig" means. ``NOT_FROM_A_SENTENCE`` holds the
arguments that deliberately have no finder; a test walks every declared argument in the registry and
fails if one lands in neither table, so an argument added later has to be decided about rather than
silently ignored.
"""

import re
import unicodedata
from datetime import date, timedelta

from src import accounts
from src.captions import tone as tones
from src.language import localise
from src.media.edit import PRESETS

# Arguments that stay the tool's own business. Each one is here because the honest source is
# something this app already holds (the staged line, the interview, the collab list) rather than
# something it could recognise in a sentence.
NOT_FROM_A_SENTENCE = ("subject", "topic", "version", "name", "why", "ask", "shape")

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}

# Extra spellings the app should answer to on top of the name and the endonym in the language
# table. "Kreyòl" is stored with the accent she types on a phone, not the one in a font file.
EXTRA_LANGUAGES = {"es": ("espanol",), "fr": ("francais",), "ht": ("kreyol", "kreole", "creole"),
                   "pt": ("portugues",)}

PLATFORM_WORDS = (("tiktok", ("tiktok", "tik tok")), ("instagram", ("instagram", "insta", "ig")),
                  ("youtube", ("youtube", "shorts")), ("pinterest", ("pinterest",)),
                  ("x", ("twitter", "x")))

VIDEO_WORDS = ("video", "clip", "footage", "vlog", "livestream", "stream")
PHOTO_WORDS = ("selfie", "photo", "picture", "pic", "pics", "image", "portrait", "flatlay",
               "flat lay", "carousel")

COUNT_NOUNS = ("tags", "hashtags", "ideas", "options", "cuts", "versions", "niches", "notes",
               "things", "cards", "posts", "lines", "suggestions", "takes", "looks", "rounds")

# Where a quoted line ends and her apostrophe starts: only straight and curly double quotes are
# treated as quoting, because she writes don't and idc inside single quotes every day.
QUOTE = re.compile(r'["“”](.+?)["“”]', re.S)


def _low(asked: str) -> str:
    return (asked or "").lower()


def _flat(value: str) -> str:
    """Lower-case with the accents taken off, so Kreyòl answers to kreyol."""
    return "".join(c for c in unicodedata.normalize("NFKD", value)
                   if not unicodedata.combining(c)).lower()


def _first(found) -> str:
    """The earliest of several spellings, so the first thing she said wins the argument."""
    hits = [(m.start(), v) for v, m in found if m]
    return min(hits)[1] if hits else ""


def _quote(asked: str) -> str:
    hit = QUOTE.search(asked or "")
    return hit.group(1).strip() if hit and len(hit.group(1).strip()) >= 3 else ""


def _codes(asked: str) -> str:
    """The language codes named in the sentence, in the order she named them.

    Both spellings of the endonym are needles: she stores Kreyòl with the accent her phone gives
    her and types kreyol with the one she doesn't, and a finder that folds only its own list would
    read one of the two as a sentence in no language at all.
    """
    low = _low(asked)
    hits = []
    for one in localise.languages():
        spellings = {one.name.lower(), _flat(one.name), one.typed_as.lower(),
                     _flat(one.typed_as), *EXTRA_LANGUAGES.get(one.code, ())}
        # "Kreyòl Ayisyen" and "Haitian Creole" are two words; she writes one of them. The first
        # word of each spelling is a language name on its own, and the only thing it can point at
        # in this table is the same language.
        spellings |= {value.split()[0] for value in spellings if value.split()}
        needles = {one.code.lower(), *spellings}
        for needle in sorted(needles, key=len, reverse=True):
            hit = re.search(r"(?<![\w-])" + re.escape(needle) + r"(?![\w-])", low)
            if hit:
                hits.append((hit.start(), one.code))
                break
    out, seen = [], set()
    for _pos, code in sorted(hits):
        if code not in seen:
            seen.add(code)
            out.append(code)
    return " ".join(out)


def _code(asked: str) -> str:
    picked = _codes(asked).split()
    return picked[0] if picked else ""


def _keep(asked: str) -> str:
    """The words she said not to translate, straight out of the sentence.

    Only three phrasings count, because all of them say what is protected: "don't translate X",
    "leave X alone", "translate everything except X". "Keep the hashtags" is not a keep-list -
    the locked tokens are already scanned off her line and do not need her to ask.

    The sentence is matched in lower case so GlucoLove answers to her typing in any case, but the
    words come out of the string she sent. The check fails a version for changing the casing of a
    locked token, so a finder that lower-cased it would be quoting her wrong to the model.
    """
    low = _low(asked)
    patterns = (r"(?:don'?t|dont|do not|never)\s+(?:translate|touch|change|rewrite)\s+"
                r"([^.,;]+?)(?:\s+(?:in|into|to)\s+\w+|\s+(?:please|pls|ty|thx)|[.,;]|$)",
                r"leave\s+([^.,;]+?)\s+alone",
                r"translate\s+everything\s+(?:but|except)\s+([^.,;]+?)(?:[.,;]|$)")
    words = []
    for pattern in patterns:
        for hit in re.finditer(pattern, low):
            span = asked[hit.start(1):hit.end(1)]
            for word in span.replace(" and ", " ").replace(",", " ").split():
                if word.lower() not in [w.lower() for w in words]:
                    words.append(word)
    return " ".join(words)


def _platform(asked: str) -> str:
    return _first((pid, re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", _low(asked)))
                  for pid, words in PLATFORM_WORDS for word in words)


def _media(asked: str) -> str:
    return _first((kind, re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", _low(asked)))
                  for kind, words in (("video", VIDEO_WORDS), ("photo", PHOTO_WORDS))
                  for word in words)


def _number(token: str) -> int:
    return int(token) if token.isdigit() else WORDS.get(token, 0)


def _limit(asked: str) -> int:
    """A count she gave, and only where the number is doing counting work.

    Either the number comes before a plural this app can hand out ("5 hashtags") or it follows a
    word that asks for a number of them ("top three"). Everything else - a ratio, a date, a size -
    is left alone, because "9:16" is not a request for nine of anything.
    """
    low = _low(asked)
    hits = []
    for hit in re.finditer(r"\b(\d{1,2}|" + "|".join(WORDS) + r")\s+(?:"
                           + "|".join(COUNT_NOUNS) + r")\b", low):
        hits.append((hit.start(), _number(hit.group(1))))
    for hit in re.finditer(r"\b(?:top|first|last|give me|gimme|need|want|only|just|about)\s+"
                           r"(?:the\s+)?(\d{1,2}|" + "|".join(WORDS) + r")\b", low):
        hits.append((hit.start(), _number(hit.group(1))))
    for _pos, value in sorted(hits):
        if 0 < value <= 25:
            return value
    return 0


def _tone_id(asked: str) -> str:
    return _first((one.id, re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", _low(asked)))
                  for one in tones.TONES for word in {one.id, _flat(one.name)})


def _look(asked: str) -> str:
    return _first((name, re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", _low(asked)))
                  for name in sorted(PRESETS))


def _on(asked: str) -> str:
    """The day she named, as the ISO date the tool needs. Only words that mean one day."""
    low = _low(asked)
    today = date.today()
    for word, offset in (("yesterday", -1), ("today", 0), ("tomorrow", 1)):
        if re.search(r"(?<!\w)" + word + r"(?!\w)", low):
            return (today + timedelta(days=offset)).isoformat()
    hit = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", low)
    if hit:
        try:
            return date.fromisoformat(hit.group(1)).isoformat()
        except ValueError:
            return ""
    return ""


FINDERS = {"codes": _codes, "code": _code, "keep": _keep, "platform": _platform, "media": _media,
           "limit": _limit, "text": _quote, "tone_id": _tone_id, "look": _look, "on": _on}


def fill(tool, args, asked: str) -> dict:
    """The planner's arguments, with anything this sentence names written over them.

    Only keys the tool actually declares come out of this; ``execute`` filters again on the way in.

    The sentence wins where the two disagree. A plan is a reading of what she typed, and a model
    that reports "instagram" under a line that says "for tiktok" is a misread, not a second
    opinion - and a rulebook chain that sets a value on purpose is no excuse for running it against
    the placement she just asked for. What the sentence does not name is left exactly as the planner
    set it, which is how her saved defaults and the staged post keep working.
    """
    out = dict(args or {})
    for key in tool.args:
        finder = FINDERS.get(key)
        if finder is None:
            continue
        value = finder(asked)
        if value not in (None, "", (), [], 0):
            out[key] = value
    return out
