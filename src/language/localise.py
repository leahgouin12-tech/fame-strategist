"""Another language, without inventing the translation.

She posts in English and sometimes wants the same caption in Spanish, French, Kreyòl or
Portuguese. There are two ways to build that, and one of them is a lie: a laptop with no server
has no dictionary, no slang authority and no idea whether ``ta quiet`` is good Kreyòl, so a page
that printed a translation it had assembled out of word lists would be printing guesses in a font
that looks like an answer.

So this file does two jobs and refuses the third.

* It knows what a translation is **not allowed to touch**: the hashtag, the @ handle, the link,
  the number, the brand written in caps, and the words she said to leave alone. Those are locked,
  and a version that loses one is reported as losing it rather than quietly shipped. ``locked`` is
  a scanner over her own line, so the list is always something she wrote and never something this
  app invented.
* It **checks** what a model hands back, and the check is the product: over the word budget for
  that placement, a terminal period the source does not use, a capital on a line she types in
  lowercase, an emoji that was not there, a number that moved, a locked token that vanished, and a
  version that came back still in English. A failing version stays on the page marked as needing a
  look, because the alternative - hiding it - is how an app ends up posting a sentence nobody read.

What it refuses is the translation itself. With no model configured, ``ask`` returns ``ran=False``
with the reason and a brief: the locked list, the budget, the register notes and the watch line for
each language. That brief is the honest offline deliverable - it is what she would write down and
hand to a person who speaks the language, and the page says so instead of apologising for not being
Google.

The word budgets come from ``PLATFORM_RULES``, the same table the caption generator cuts against,
so a 22-word TikTok line in Miami and a 22-word TikTok line in Santo Domingo are measured by the
same ruler. Each language carries a slack multiplier, which is **this app's own allowance** - a
translation needs more room than English because of what those languages are, not because of how
she writes, and cutting a Spanish line to an English budget would be the app's arithmetic charged
to her.
"""

from dataclasses import dataclass
import re

from src import accounts
from src.captions import register
from src.strategist.voice import PLATFORM_RULES

# How much longer a version may run than the English budget before this page calls it too long.
# An allowance the app grants, not a measurement it publishes: see the module docstring.
@dataclass(frozen=True)
class Language:
    code: str
    name: str
    typed_as: str
    slack: float
    markers: tuple
    watch: str


LANGUAGES = (
    Language("es", "Spanish", "Español", 1.35,
             ("que", "con", "para", "muy", "pero", "está", "gracias", "también", "no", "sí"),
             "Cuban and Dominican Spanish in Miami run words together and drop the final -s. A "
             "version that reads like a phrasebook is not wrong, it is just not from here."),
    Language("fr", "French", "Français", 1.4,
             ("le", "la", "les", "est", "avec", "pour", "très", "mais", "pas", "aussi", "c'est"),
             "Standard French capitalises the first word of a sentence. If her line is lowercase, "
             "the version has to stay lowercase - that is register, not grammar."),
    Language("ht", "Haitian Creole", "Kreyòl Ayisyen", 1.35,
             ("mwen", "ou", "li", "se", "pa", "ak", "pou", "trè", "men", "sa", "nan"),
             "Kreyòl spelling is not fully settled and accents get dropped on phones, so `se mwen` "
             "and `se mwen` are the same sentence. Never treat that as an error."),
    Language("pt", "Portuguese", "Português", 1.35,
             ("não", "que", "com", "para", "muito", "mas", "obrigado", "isto", "também", "você"),
             "Brazilian and European Portuguese differ in the everyday words. Ask which one the "
             "post is for; this app cannot hear the difference."),
)
BY_CODE = {lang.code: lang for lang in LANGUAGES}

# A line has to be this long, and the winner this far ahead of the runner-up, before this page is
# willing to name the language it is written in. Two shared words is not a language.
MIN_MARKERS = 3
MIN_WORDS = 4
TAG = re.compile(r"(?<!\w)#[\w]+")
MENTION = re.compile(r"(?<!\w)@[\w.]+")
LINK = re.compile(r"(?i)\b(?:https?://|www\.)[^\s]+")
# A number, with the unit or suffix stuck to it when there is one, because `3pm`, `20%` and `100k`
# are claims and a version that rounds them is not translating.
NUMBER = re.compile(r"\b\d+(?:[.,:]\d+)?\s*(?:%|k|m|b|pm|am|s|secs?|mins?|hrs?|x|px|fps)?\b", re.I)
CAPS = re.compile(r"\b[A-Z][A-Z'&.]{1,}\b")
TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2190-\u21FF]")
# Capitals that come back from a phone autocorrect rather than as a brand name, so shouting a word
# does not lock it.
SHOUTABLE = frozenset(("ok", "okay", "no", "yes", "lol", "omg", "wtf", "idc", "idk", "fr", "rn",
                       "tbh", "imo", "imho", "ngl", "smh", "fyi", "ps", "usa", "fl", "miami",
                       "nyc", "la", "vc", "dm", "ig", "tk", "ceo", "bff"))

# The two kinds of thing a locked list can hold. `must` has to appear in the version exactly, or
# the version is reported. `voice` cannot be locked that way - Spanish has its own shorthand, and
# demanding `rn` survive into it would flag every good translation - so it travels as an
# instruction to the model and a note on the page instead.
MUST_KINDS = ("tag", "mention", "link", "number", "brand", "keep")

# The abbreviations and markers she types, taken from the register module so there is one list and
# it cannot drift. These are also not English: `fr` is not `for` and `rn` is not `run`, so a
# detector or a cleaner that reads them as English will correct her voice away.
VOICE_TOKENS = frozenset(register.ALL_ABBREVS) | frozenset(register.MARKER_ORDER) | frozenset(
    ("lol", "omg", "wtf", "idk", "ngl", "imo", "yk", "wym", "bc", "af"))
VOICE_PHRASES = ("no cap", "straight up")

# Printed on the page, in these words, because a localisation panel that does not state its limits
# is the thing this category is usually guilty of.
CANNOT = (
    "the translation itself. This app keeps no dictionary and has no speaker on call, so with no "
    "model connected it prints what a version has to fit - the locked list, the budget, your "
    "register - and not a guess dressed up as an answer",
    "whether a version sounds native. The check compares your line against the version, so it can "
    "tell you a hashtag went missing and cannot tell you nobody in Miami talks like that",
    "a wrong claim that kept its numbers. A version that smooths your sentence into a different "
    "meaning still passes every rule here if the tags and the figures survived",
    "what the platform does after you post. Instagram and TikTok add their own translation under a "
    "caption; this page cannot see it, turn it off, or be blamed for it",
)


@dataclass(frozen=True)
class Locked:
    token: str
    kind: str

    def as_dict(self) -> dict:
        return {"token": self.token, "kind": self.kind}


@dataclass(frozen=True)
class Version:
    """One model-written version, with the verdict of the check attached to it.

    ``ok`` is the flag the page and the agent both read. A version that failed is not thrown away:
    the problems travel with it, so she can see that ``#thrifted`` went missing rather than being
    told, by an app, that nothing was wrong."""

    text: str
    note: str
    problems: tuple = ()
    language: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def words(self) -> int:
        return len(self.text.split())

    def as_dict(self) -> dict:
        return {"text": self.text, "note": self.note, "ok": self.ok, "words": self.words,
                "problems": list(self.problems), "language": self.language}


@dataclass(frozen=True)
class Detection:
    code: str
    why: str
    hits: int = 0

    def as_dict(self) -> dict:
        return {"code": self.code, "why": self.why, "hits": self.hits,
                "name": BY_CODE[self.code].name if self.code in BY_CODE else ""}


@dataclass(frozen=True)
class Brief:
    """What this app can hand her with no model: the constraints a translation has to fit."""

    language: str
    words: int
    tags: int
    locked: tuple
    voice: tuple
    watch: str
    shape: str

    def as_dict(self) -> dict:
        return {"language": self.language, "words": self.words, "tags": self.tags,
                "locked": [t.token for t in self.locked], "voice": [t.token for t in self.voice],
                "watch": self.watch, "shape": self.shape}


@dataclass(frozen=True)
class Localise:
    """Either versions, or the reason there are none plus what to do about it."""

    ran: bool
    why: str
    said_by: str = ""
    briefs: tuple = ()
    versions: tuple = ()

    def as_dict(self) -> dict:
        return {"ran": self.ran, "why": self.why, "said_by": self.said_by,
                "briefs": [b.as_dict() for b in self.briefs],
                "versions": [v.as_dict() for v in self.versions]}


def languages() -> tuple:
    return LANGUAGES


def get(code: str) -> Language:
    """The language by the code she chose, or None - so a bad value is a visible no rather than a
    silent default to Spanish."""
    return BY_CODE.get((code or "").strip().lower())


def tokens(text: str) -> list:
    """Lowercase word tokens, with a contraction kept whole.

    ``c'est`` stays one token: splitting it into ``c`` and ``est`` would let an English line score
    a French marker off an apostrophe."""
    return [m.group(0).lower() for m in TOKEN.finditer(text or "")]


def locked(text: str, extra: str = "") -> tuple:
    """What must survive the translation, read out of her own line.

    Order is the order she wrote them in, because a caption with three hashtags is a list she
    arranged. Nothing is added that is not in the sentence, except her keep-words, which she put on
    the list on purpose and may not have used in this line yet."""
    out, seen = [], set()

    def add(token, kind):
        clean = (token or "").strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            out.append(Locked(clean, kind))

    stripped = text or ""
    for pattern, kind in ((TAG, "tag"), (MENTION, "mention"), (LINK, "link")):
        for hit in pattern.finditer(stripped):
            add(hit.group(0), kind)
    rest = LINK.sub(" ", TAG.sub(" ", MENTION.sub(" ", stripped)))
    for hit in CAPS.finditer(rest):
        if hit.group(0).lower() not in SHOUTABLE and hit.group(0).lower() not in VOICE_TOKENS:
            add(hit.group(0), "brand")
    for hit in NUMBER.finditer(rest):
        add(hit.group(0), "number")
    for word in (extra or "").replace(",", " ").split():
        add(word, "keep")
    return tuple(out)


def voice_tokens(text: str) -> tuple:
    """The shorthand she types, named so a model can be told not to iron it out.

    These are not locked, and the page says why: another language has its own text-talk, so a
    version that swaps ``rn`` for ``ahorita`` is translating while one that swaps it for ``right
    now`` is correcting her."""
    found, seen = [], set()
    for word in tokens(text):
        bare = word.strip("'’")
        if bare in VOICE_TOKENS and bare not in seen:
            seen.add(bare)
            found.append(Locked(bare, "voice"))
    low = (text or "").lower()
    for phrase in VOICE_PHRASES:
        if phrase in low and phrase not in seen:
            seen.add(phrase)
            found.append(Locked(phrase, "voice"))
    return tuple(found)


def detect(text: str) -> Detection:
    """Name the language only when the words say so.

    This exists so a caption she wrote in Spanish is not measured against the English budget, and
    so the page can offer the other direction. It is a marker-word count and nothing more, so it
    stays quiet on a short line, on a line built only out of words two of these languages share,
    and on English."""
    words = tokens(text)
    if not words:
        return Detection("", "There is nothing here to read yet.")
    scored = []
    for lang in LANGUAGES:
        hits = len({w for w in words if w in lang.markers})
        if hits:
            scored.append((hits, lang.code))
    scored.sort(key=lambda pair: -pair[0])
    if not scored:
        return Detection("", "No marker word from any of these languages is in it. This reads as "
                             "English.")
    top, code = scored[0]
    named = BY_CODE[code].name
    if len(words) < MIN_WORDS:
        return Detection("", f"{named} is possible, but {len(words)} words is not enough to say "
                             "what language this is.")
    if top < MIN_MARKERS:
        return Detection("", f"{named} is possible - {top} of its marker words appear - but shared "
                             "words are not a language.")
    if len(scored) > 1 and scored[1][0] >= top:
        return Detection("", f"It lands on {named} and {BY_CODE[scored[1][1]].name} equally, which "
                             "is what a line written in two languages looks like to a word count.")
    return Detection(code, f"{top} of {named}'s marker words are in it.", top)


def budget_for(platform: str, code: str = "", media: str = "photo") -> int:
    """The word budget for this placement, in this language.

    The English number is ``PLATFORM_RULES``, with the same cut a video line gets from the caption
    generator. The language number is that times the language's allowance, and it is never smaller
    than the English one - a Spanish line over the English budget is this page's arithmetic running
    out, not her being wordy."""
    rules = PLATFORM_RULES.get(accounts.caption_key(platform), PLATFORM_RULES["reels"])
    base = rules["words"]
    if (media or "").strip().lower() in ("video", "clip", "reel", "story", "tiktok"):
        base = max(9, int(base * 0.75))
    lang = get(code)
    return base if lang is None else max(base, int(round(base * lang.slack)))


def tags_for(platform: str) -> int:
    return PLATFORM_RULES.get(accounts.caption_key(platform), PLATFORM_RULES["reels"])["tags"]


def shape_for(platform: str) -> str:
    return PLATFORM_RULES.get(accounts.caption_key(platform), PLATFORM_RULES["reels"])["shape"]


def brief(platform: str, media: str, text: str, code: str, keep: str = "") -> Brief:
    """The offline deliverable: everything a person - or a model - needs to write the version.

    Read it as an instruction sheet rather than an answer, which is what it is. Handing it to
    somebody who speaks the language gets a better result than a guess, and the page says that in
    those words."""
    lang = get(code)
    if lang is None:
        return Brief("", 0, 0, (), (), "", "")
    return Brief(language=lang.code, words=budget_for(platform, lang.code, media),
                 tags=tags_for(platform), locked=locked(text, keep), voice=voice_tokens(text),
                 watch=lang.watch, shape=shape_for(platform))


def check(source: str, version: str, code: str, platform: str = "instagram",
          media: str = "photo", keep: str = "", tags: tuple = None) -> tuple:
    """What is wrong with this version, in the order she should read it.

    Every rule here is a claim this app can verify by comparing the two strings. Nothing here
    judges whether the sentence is good Kreyòl, whether it lands in Santo Domingo, or whether a
    stranger would read it the way she meant it - so it cannot clear a version, only report on it.
    """
    text = (version or "").strip()
    if not text:
        return ("It came back empty.",)
    low = text.lower()
    must = tags if tags is not None else locked(source, keep)
    problems = []
    for item in must:
        if item.kind not in MUST_KINDS:
            continue
        if item.kind == "number":
            if not _digits_in(item.token, text):
                problems.append(f"the number {item.token.strip()} is not in it any more")
        elif item.token.lower() not in low:
            problems.append(f"{item.token} is gone")
    if not problems and low == (source or "").strip().lower():
        problems.append("it is the same words you gave - nothing was translated")
    budget = budget_for(platform, code, media)
    count = len(text.split())
    if count > budget:
        problems.append(f"it is {count} words against the {budget} this page allows for a "
                        f"{BY_CODE[code].name if code in BY_CODE else 'caption'} line here")
    if not _ends_period(source) and _ends_period(text):
        problems.append("it ends in a full stop, which your line does not do")
    if _is_lower(source) and re.search(r"(?:^|[\s\"'(\u00a1\u00bf])[A-ZÀ-Þ]", text):
        problems.append("it capitalises a line you type in lowercase")
    added = [e for e in EMOJI.findall(text) if e not in (source or "")]
    if added:
        problems.append("it added " + " ".join(added[:3]))
    return tuple(problems)


def ask(engine, source: str, codes, *, platform: str = "instagram", media: str = "photo",
        keep: str = "", n: int = 2) -> Localise:
    """Versions, or the brief and the reason.

    The offline branch is the whole point of the signature: an app that returns a canned phrase
    when it has no model is worse than one that says it did not run. Nothing here pretends -
    ``ran=False`` travels all the way to the page and into the agent's own report."""
    wanted = [code for code in (codes or []) if get(code)]
    if not (source or "").strip():
        return Localise(ran=False, why="There is no caption to localise yet.")
    if not wanted:
        return Localise(ran=False, why="No language was picked, so there was nothing to ask for.")
    briefs = tuple(brief(platform, media, source, code, keep) for code in wanted)
    if engine is None or engine.name == "offline":
        return Localise(
            ran=False,
            why="No model is connected, and this app keeps no dictionary of its own - so it wrote "
                "nothing in another language rather than guess. The briefs below are what a "
                "person, or a model, would need to write it for real.",
            briefs=briefs)
    versions = []
    for one in briefs:
        for draft in _ask_one(engine, source, one, keep, n):
            problems = check(source, draft.text, one.language, platform, media, keep, one.locked)
            versions.append(Version(text=draft.text, note=draft.note, problems=problems,
                                    language=one.language))
    good = sum(1 for v in versions if v.ok)
    return Localise(ran=True, said_by=engine.name, briefs=briefs, versions=tuple(versions),
                    why=(f"{good} of {len(versions)} versions passed the check." if versions
                         else "The model answered with nothing usable."))


@dataclass(frozen=True)
class Draft:
    text: str
    note: str


SCHEMA = {
    "type": "object",
    "required": ["versions"],
    "properties": {
        "versions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "note"],
                "properties": {"text": {"type": "string"}, "note": {"type": "string"}},
            },
        }
    },
}


def _ask_one(engine, source: str, one: Brief, keep: str, n: int) -> list:
    lang = BY_CODE[one.language]
    must = ", ".join(t.token for t in one.locked) or "nothing beyond the sentence itself"
    said = ", ".join(t.token for t in one.voice) or "none in this line"
    data = engine.complete_json(
        "You write social media captions in another language for a 24 year old American creator. "
        "The line you are given is hers and it is already how she talks. Your job is to carry it, "
        "not improve it.\n"
        "Rules that matter:\n"
        f"- Keep these exactly as written: {must}.\n"
        f"- She types in shorthand ({said}). Do not spell that out into formal language and do not "
        "correct it. If the target language has its own text shorthand, use that instead.\n"
        "- Match her casing and her punctuation. If her line has no capital and no full stop, "
        "yours has neither.\n"
        f"- Fit inside {one.words} words. The placement wants: {one.shape}.\n"
        f"- {one.watch}\n"
        "- Do not add an emoji, a claim, a hashtag, or a call to action she did not write.\n"
        "- If a word has two common spellings in the language, pick one and say nothing about it.\n"
        "In `note`, one short sentence: what you had to change to make it land, and anything you "
        "are unsure about. Do not claim it is perfect.",
        f"Language: {lang.name} ({lang.typed_as}).\n"
        f"Caption to carry: {source}\n"
        + (f"Words she said not to translate: {keep}.\n" if keep else "")
        + f"Give {n} versions that differ in rhythm, not in meaning.",
        SCHEMA)
    out = []
    for item in (data.get("versions") or [])[:max(1, n)]:
        text = str(item.get("text", "")).strip()
        if text:
            out.append(Draft(text=text[:400], note=str(item.get("note", "")).strip()[:300]))
    return out


def _digits_in(token: str, text: str) -> bool:
    """``3pm`` survives as ``3 de la tarde`` but not as ``2 de la tarde``, so the figures are
    compared and the unit is not."""
    wanted = re.findall(r"\d+", token)
    return bool(wanted) and all(w in re.findall(r"\d+", text) for w in wanted)


def _ends_period(text: str) -> bool:
    return bool((text or "").strip()) and (text or "").strip().endswith(".")


def _is_lower(text: str) -> bool:
    """Her line is lowercase when it has letters and none of them are capitals - a hashtag and an
    @ handle do not count against it, because those are typed with symbols by convention."""
    body = MENTION.sub(" ", TAG.sub(" ", text or ""))
    letters = [c for c in body if c.isalpha()]
    return bool(letters) and not any(c.isupper() for c in letters)
