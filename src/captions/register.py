"""The part that decides whether a line is something you would actually type.

A caption generator fails in three ways, and all three were happening here. It recited the whole
descriptive phrase back into a spoken sentence ("the black ribbed tank did something to me" -
nobody says the colour, the fabric and the item in one breath unless they are writing a product
listing). It shipped copywriting formulas that have been on the internet so long they read as
generated ("me: I'll do X once. also me:", "does X look better in this light or does everything").
And it wrote in full formal grammar with terminal periods, because a generator does that by default
and a person does not.

So this file holds three separate jobs:

* ``say`` - what the line calls the thing. Inside a sentence it is the head noun, not the whole
  description she typed for the generator to read.
* ``flatten`` - how the line is typed. Contractions always (an uncontracted "it is" is the loudest
  machine tell there is), then her own abbreviations - and only the ones she uses. Nothing pasted
  means no fake "ur": inventing somebody's spelling is the exact failure this rewrite exists to
  kill, so the app's default is contractions and no terminal period, with abbreviations off until
  she either types captions of her own or switches them on herself.
* ``tells`` - the shapes and words that get refused rather than softened. A line matching one of
  these is dropped and counted, not printed with a note beside it.

Nothing here calls a model. Every change is a rule applied to the sentence she typed, and every
rule can name the sample it came from.
"""

from dataclasses import dataclass, field
import re

# The descriptive words, in the order a person would actually drop them. Colour and fabric go
# first: "the black ribbed tank" said back whole is a product title, "the tank" is what she types.
MODIFIER = re.compile(r"\b(black|white|grey|gray|beige|brown|navy|red|green|blue|pink|cream|"
                      r"olive|burgundy|ribbed|knit|cotton|denim|silk|satin|linen|mesh|cropped|"
                      r"oversized|slim|fitted|vintage|thrifted|old|new|little|big)\b", re.I)

# Full grammar -> the way it is typed, longest first so "it is not" cannot be left half-done.
# These carry no information away, so they are safe on anybody's sentence. The abbreviations in
# ABBREVIATIONS are not safe that way and are gated on her actually typing them.
CONTRACTIONS = (
    ("cannot", "can't"), ("do not", "don't"), ("does not", "doesn't"), ("is not", "isn't"),
    ("are not", "aren't"), ("was not", "wasn't"), ("it is", "it's"), ("that is", "that's"),
    ("there is", "there's"), ("what is", "what's"), ("i am", "i'm"), ("i have", "i've"),
    ("i will", "i'll"), ("you are", "you're"), ("we are", "we're"), ("they are", "they're"),
)
REDUCTIONS = (("going to", "gonna"), ("want to", "wanna"), ("let us", "let's"),
              ("kind of", "kinda"), ("sort of", "sorta"), ("right now", "rn"),
              ("because", "bc"), ("about to", "bout to"), ("out of", "outta"))
# (word, casual spelling). Applied only when she has typed the casual spelling herself, or has
# switched the set on. `not` -> `no` is deliberately absent: "i'm not sorry" becoming "i'm no sorry"
# is not casual typing, it is a sentence that no longer works. Neither is `with` -> `w/`, which is
# note-taking shorthand and reads like one in a caption.
ABBREVIATIONS = (
    ("you", "u"), ("your", "ur"), ("yours", "urs"), ("what", "wat"),
    ("and", "n"), ("please", "plz"), ("little", "lil"), ("them", "dem"),
    ("these", "dis"), ("tonight", "tn"), ("forever", "fer"),
)
ALL_ABBREVS = {rep for _pat, rep in ABBREVIATIONS}
# Marker words only decorate a line that already carries the idea, so each one names the condition
# it needs. Nothing here adds a claim: `idc` waits for a line that already does not care.
MARKERS = (
    ("fr", r"(really|actually|literally|unreal|insane|wild|the best)", "agreeing with it"),
    ("tbh", r"(i think|i'd say|not sorry|to be honest|i am|im)", "admitting something"),
    ("rn", r"(today|now|day|lately|again|currently)", "about right now"),
    ("idc", r"(dont|don't|not).{0,24}(care|mind|sorry|for you|your business)", "not caring"),
    ("lowkey", r"(obsessed|cant stop|wearing it|again|love)", "hedging a big claim"),
    ("highkey", r"(obsessed|cant stop|need|love)", "not even pretending"),
    ("omg", r"(unreal|insane|wild|stop|look|actually)", "a real reaction"),
    ("lmao", r"(nobody asked|joke|again|once|borrow)", "the line is a joke"),
    ("no cap", r"(really|actually|the best|unreal|swear)", "swearing to it"),
    ("deadass", r"(really|actually|not joking|i mean it|swear)", "meaning it literally"),
)
MARKER_ORDER = tuple(m for m, _need, _why in MARKERS)
MARKER_NEEDS = {m: re.compile(need, re.I) for m, need, _why in MARKERS}
MARKER_WHY = {m: why for m, _need, why in MARKERS}
# Where each marker sits, because they are different words grammatically: `tbh` opens, `fr` answers
# the claim from behind it, and `idc` trails it after a comma. Glued to the front, "idc no it's not
# for you" reads like a translation instead of a text.
MARKER_TAIL = frozenset(("fr", "no cap", "deadass"))
MARKER_TRAIL = frozenset(("idc",))
EMPHASIS = ("actually", "literally", "litterally", "really", "genuinely", "straight up", "deadass")
# The kinds of claim a booster word can attach to. Anything else is left alone, because a booster
# in front of a plain statement is the app deciding the post matters more than she said it does.
CLAIM = re.compile(r"\b(really|unreal|insane|wild|love|best|the whole ask|did something)\b", re.I)
# The structural machine tells: shapes that have circulated long enough to read as generated, plus
# the vocabulary of a content calendar, plus lines that speak for strangers or put down the reader.
TELLS = (
    (r"\bme:\s.*\balso me\b", "the `me: / also me:` meme, which is a template and not a sentence"),
    (r"\bor does everything\b", "the `does X or does everything` copywriting question"),
    (r"\bthat'?s the (whole )?(point|post)\b", "`that's the point` used as a punchline"),
    (r"\belevat\w+|must-?have|game.?changer|level up\b", "content-calendar vocabulary"),
    (r"\bobsessed\b", "`obsessed`, the word every brand caption reaches for"),
    (r"\bit'?s giving\b|\bserving\b", "`it's giving` / `serving`, which is not the app's voice"),
    (r"\bunbothered\b|\bbaddie\b|\bslay(?:s|ing)?\b", "the influencer persona words"),
    (r"\blow sun\b|\bquiet \w+\b", "the `fragment, low sun` aesthetic caption"),
    (r"\bthis is the one\b", "`this is the one`, which is an ad for nothing"),
    (r"\bnot a request\b", "`not a request, a photo of X`, a line nobody has ever typed"),
    (r"\bhas seen more of the (city|world)\b", "the `has seen more of the city than me` joke"),
    (r"\blike it'?s the last\b", "the `like it's the last warm day` line from a listicle"),
    (r"\byou(?: will|'ll) ask\b", "speaking for what strangers will do, which is invented"),
    (r"\bno hair done\b", "a dig at the reader's own grooming, which reads mean rather than dry"),
    (r"\bdid more than yours\b", "putting down the person reading it"),
    (r"\bif you know the \w+, you know\b", "`if you know you know` dressed up as a detail"),
    (r"\bthe rest of (it|me) is\b", "a writerly simile the app would have to own"),
)
FORMAL = (r"\b(thus|moreover|whether|therefore|utilize\w*|commence\w*|endeavou?\w*|one another)\b")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]{1,}")


@dataclass
class Register:
    """How she types: what her own captions measured, what she switched on, and what is the app's
    own default because neither happened."""
    source: str
    learned: bool
    case_style: str
    end_period: bool
    question_rate: float
    abbrevs: tuple = ()
    markers: tuple = ()
    emphasis: tuple = ()
    openers: tuple = ()
    caps: bool = False
    repeated: bool = False
    corrections: tuple = ()
    notes: tuple = ()
    typed: tuple = ()

    def uses(self, token: str) -> bool:
        return token in self.abbrevs or token in self.markers or token in self.emphasis

    def provenance(self, token: str) -> str:
        """Where an allowed spelling came from, said straight.

        A marker she switched on from the page is not one she types, and telling her "you type it"
        is how a personalization feature starts gaslighting her into owning a line she never wrote.
        """
        if token in self.typed:
            return "you type it"
        if self.uses(token):
            return "you switched it on"
        return "the app's default"


def fixes(rows) -> tuple:
    """Her saved corrections, read back as (the line, the way she says it) pairs.

    Stored as `old => new` in the notes table by whoever records them, so a correction she typed
    once on any tone changes every later line that contains it. A body with no arrow is skipped:
    it is a note, not an edit, and guessing which half is which is how her wording gets inverted.
    """
    out = []
    for r in rows or []:
        body = str(r.get("body") if isinstance(r, dict) else r or "")
        if "=>" not in body:
            continue
        bad, good = body.split("=>", 1)
        bad, good = bad.strip(), good.strip()
        if bad and good:
            out.append((bad, good))
    return tuple(out)


def corrected(text: str, reg: Register) -> str:
    """Apply her own rewrites, once each, left to right."""
    out = text
    for bad, good in reg.corrections:
        if bad in out:
            out = out.replace(bad, good, 1)
    return out


def _has(low: str, token: str) -> bool:
    """Whether she typed this spelling as its own word. `n` needs spaces around it because a lone
    `n` inside anything else is just a letter."""
    edge = r"(?<=\s)" if len(token) == 1 else r"(?<!\w)"
    tail = r"(?=\s|$)" if len(token) == 1 else r"(?!\w)"
    return bool(re.search(edge + re.escape(token) + tail, low))


def scan(samples) -> dict:
    """The counts a register is built from, over the raw text she pasted."""
    clean = [s.strip() for s in (samples or []) if s and s.strip()]
    low = "\n".join(clean).lower()
    abbrevs = tuple(sorted(rep for rep in ALL_ABBREVS if _has(low, rep)))
    marks = tuple(sorted(m for m in MARKER_ORDER if _has(low, m)))
    emph = tuple(sorted(e for e in EMPHASIS if _has(low, e)))
    ends = re.findall(r"\S+([.!?])(?:\s|$)", low)
    periods = sum(1 for e in ends if e == ".")
    questions = sum(1 for e in ends if e == "?")
    openers = tuple(o for o in dict.fromkeys(
        re.split(r"[\s,.!?]+", s)[0].lower() for s in clean
        if WORD_RE.match(re.split(r"[\s,.!?]+", s)[0])) if o and len(o) > 2)[:4]
    n = max(len(ends), 1)
    return {"samples": len(clean), "abbrevs": abbrevs, "markers": marks, "emphasis": emph,
            "end_period": bool(ends) and periods >= max(len(clean) * 0.5, questions),
            "question_rate": round(questions / n, 2),
            "caps": bool(re.search(r"\b[A-Z]{4,}\b", "\n".join(clean))),
            "repeated": bool(re.search(r"(?i)(\b(\w+) \2\b)", low)),
            "openers": openers}


def of(profile, samples=None, want_abbrevs: bool = False, want_markers: bool = False,
       corrections: tuple = ()) -> Register:
    """The register the writer is allowed to use.

    ``want_*`` are hers to switch on from the page. An abbreviation the app guessed is a spelling
    she would then have to own, so without either her samples or her explicit choice it stays out.
    """
    got = scan(samples)
    learned = bool(got["samples"])
    typed = tuple(set(got["abbrevs"]) | set(got["markers"]) | set(got["emphasis"]))
    abbrevs = got["abbrevs"] or (tuple(sorted(ALL_ABBREVS)) if want_abbrevs else ())
    marks = tuple(sorted(set(got["markers"]) | (set(MARKER_ORDER) if want_markers else set())))
    notes = []
    if not learned:
        notes.append("Nothing pasted yet, so this is the app's own typing: contracted, no fake "
                     "abbreviations, no terminal periods. Paste a few captions you have actually "
                     "written and the spelling becomes yours.")
    elif not abbrevs:
        notes.append(f"{got['samples']} of your captions measured, none of them abbreviated, so "
                     "nothing here is shortened beyond contractions.")
    return Register(
        source=f"{got['samples']} of your own captions" if learned else
               "switched on by you, not measured" if (want_abbrevs or want_markers) else
               "the app's default, because nothing is pasted",
        learned=learned,
        case_style=profile.case_style if learned else "lowercase",
        end_period=got["end_period"],
        question_rate=got["question_rate"],
        abbrevs=abbrevs,
        markers=marks,
        emphasis=got["emphasis"] or (("actually",) if want_markers else ()),
        openers=got["openers"],
        caps=got["caps"],
        repeated=got["repeated"],
        corrections=tuple(corrections or ()),
        notes=tuple(notes),
        typed=typed,
    )


def say(thing: str, part: str) -> str:
    """What the line calls the item when it is inside a sentence, without the article.

    The descriptive modifiers are stripped on purpose: "the black ribbed tank" is a description
    she typed so the generator would know what to point at, not a phrase anybody puts in a caption,
    so this gives back "tank". A compound she chose is not a description though - "sex shop" keeps
    both words, because taking the first one out changes which shop it is. With one word left there
    is nothing to collapse, so it passes through.
    """
    bits = [w for w in re.split(r"\s+", (thing or "").strip()) if w]
    if bits and bits[0] in ("the", "a", "an"):
        bits = bits[1:]
    if len(bits) <= 1:
        return " ".join(bits)
    keep = [w for w in bits if not MODIFIER.search(w)]
    if len(keep) >= 2:
        return " ".join(keep)
    return " ".join(keep or bits)


def contracted(text: str) -> str:
    """Every shape typed the way she types: `it is` becomes `it's`, `going to` becomes `gonna`.

    A contraction that would land at the very end of the line is left alone. "the tank is doing
    more work than i am" is a sentence; "…than i'm" is a clause with nothing after it, and a
    caption that reads half-finished is exactly the thing this module was rebuilt to kill."""
    out = text
    for formal, short in CONTRACTIONS:
        pattern = (r"(?i)\b" + formal.replace(" ", r"\s+") + r"\b(?!\s*[.,!?;]\s*$)(?!\s*$)")
        out = re.sub(pattern, short, out)
    for formal, short in REDUCTIONS:
        out = re.sub(r"(?i)\b" + formal.replace(" ", r"\s+") + r"\b", short, out)
    return out


def abbreviate(text: str, reg: Register) -> str:
    """Only the spellings she has typed herself, or switched on.

    The lookahead matters: `\\byou\\b` matches the `you` inside `you'd`, and turning that into `u'd`
    produces a spelling nobody has ever typed.
    """
    out = text
    for word, rep in ABBREVIATIONS:
        if rep not in reg.abbrevs:
            continue
        out = re.sub(rf"(?<!\w){word}(?![\w'])", rep, out, flags=re.I)
    return out


def punctuate(text: str, reg: Register) -> str:
    """Her terminal punctuation, not the generator's. A caption ending on a period when none of
    her samples do is the tell; a question mark is never added on speculation either, because the
    shape asks the question or it does not.

    Only the period at the very end comes off. The one in the middle of a video caption - "stop.
    the tank." - is what makes the hook a separate beat instead of the order "stop the tank", so
    the switch that says her lines do not end on one never reaches inside a line."""
    out = re.sub(r"\s+", " ", (text or "").strip())
    if not reg.end_period and out.endswith("."):
        out = out[:-1].rstrip()
    return out.strip(" ,")


def soften(text: str) -> str:
    """The few grammar repairs a contraction pass can leave behind, so no shipped line is broken."""
    return re.sub(r"\bthis's\b", "this is", text)


def flatten(text: str, reg: Register) -> tuple:
    """One line into the way she would type it, plus what the rewrite changed and why."""
    said = []
    out = soften(contracted(text))
    if out != text:
        said.append("contracted - `it is` and `it's` are not the same person typing")
    raw = out
    out = abbreviate(out, reg)
    if out != raw:
        said.append("shortened with spellings " +
                    ("from your own captions" if reg.learned else "you switched on"))
    raw = out
    if reg.case_style == "lowercase":
        out = out.lower()
    elif reg.case_style == "capitalised":
        out = out[:1].upper() + out[1:]
    if out != raw:
        said.append(f"cased like your samples ({reg.case_style})" if reg.learned else
                    "left lowercase - the app's default casing, not a style picked for you")
    raw = out
    out = punctuate(out, reg)
    if out != raw:
        said.append("the period is gone because your lines do not end on one")
    return out, said


def place(text: str, mark: str) -> str:
    """The marker goes where it is a real word in that sentence, not at the front of it."""
    if mark in MARKER_TAIL:
        return f"{text} {mark}"
    if mark in MARKER_TRAIL:
        return f"{text}, {mark}"
    return f"{mark} {text}"


def marker_for(text: str, reg: Register) -> tuple:
    """One marker this line has earned, or None.

    Chosen by the condition in ``MARKERS`` rather than at random, so `idc` only ever lands on a
    line that already says it does not care. Nothing is added when her register carries no markers.
    """
    for mark in reg.markers:
        need = MARKER_NEEDS.get(mark)
        if need and need.search(text):
            return mark, MARKER_WHY[mark]
    return None, ""


def emphasis_for(text: str, reg: Register) -> tuple:
    """Whether this line is making the kind of claim her booster words go on."""
    return bool(CLAIM.search(text or ""))


def emphasize(text: str, reg: Register) -> tuple:
    """Her own booster word, in front of the claim it strengthens.

    Not at the head of the sentence: `actually` opening a line is a different word from `actually`
    standing in front of an adjective. And nothing is added when the line already carries one of
    her boosters - two of them in eight words is not emphasis, it is a generator overcorrecting.
    """
    if not reg.emphasis or not CLAIM.search(text or ""):
        return text, None
    word = reg.emphasis[0]
    if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.I):
        return text, None
    hit = CLAIM.search(text)
    return f"{text[:hit.start()]}{word} {text[hit.start():]}".strip(), word


def tells(text: str) -> list:
    """Why this line is not going on the page."""
    low = (text or "").lower()
    bad = [why for pat, why in TELLS if re.search(pat, low)]
    if re.search(FORMAL, low):
        bad.append("written in formal grammar, which is the loudest machine tell there is")
    return bad
