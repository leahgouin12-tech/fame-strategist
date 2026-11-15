"""Six temperatures, one post, in the way she actually types.

A caption is not "written" so much as chosen: the same mirror photo can be a dare, a fragment, or a
joke about the same tank worn for the sixth time. Each tone here is a small grammar - a handful of
sentence shapes with the slots left open - and the slots are filled from the words she used to
describe the shot, so the line is built out of her sentence and not out of a persona somebody
configured.

Everything in this file exists to answer one complaint: the lines were unusable. So the shapes are
written the way a person types (contracted, no terminal period, the head noun instead of the whole
description), and three layers stand between a shape and the page:

* ``register.say`` - a sentence says "the tank", not "the black ribbed tank". The modifiers she
  typed are used by the shapes that are actually about the detail, and by nothing else.
* ``register.flatten`` - contractions, her own casing, her own abbreviations, her own punctuation.
* ``register.tells`` - the shapes that read like a template or a content calendar are dropped and
  counted, not printed with an apology next to them.

Still true from before: the casing comes from her measured voice profile; a video gets a spoken hook
in front of the line, and when the pair will not fit the placement's word budget the line ships and
the hook is written underneath it rather than the caption being cut off mid-sentence; a shape that
needs something she never gave - a detail, a number - is skipped and counted, never padded with "it"
or with a count she did not say; the word for the post follows what she is posting, so a Story line
never calls it a photo; and nothing is filtered - an adult line is written when she asks for one,
with the one word a caption filter is likely to look at named beside it.
"""
from dataclasses import dataclass, field
import random
import re

from src.captions import register
from src.strategist.voice import PLATFORM_RULES, _fit, recase

# Stop words live in the voice module, which counts them; this file needs the same list to find
# the concrete part of "mirror selfie in the black ribbed tank", so it imports rather than
# keeping a second copy that can drift.
from src.strategist.voice import STOP as _STOP

WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]{2,}")
# A number she spelled is still a number she said, so the count slot reads words as well as
# digits - "three clips of the same latte" should not come back as "no number in your sentence".
# "one" is left out: it is the article half the time, and a wrong count reads as a mishear.
DIGIT = re.compile(r"\b(\d{1,3}|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
                   re.I)
SPOKEN = {w: str(i) for i, w in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
     "eleven", "twelve"), 0)}
SLOT = re.compile(r"\{(\w+)\}")
FORM_WORDS = {"photo": "photo", "picture": "photo", "selfie": "photo", "post": "post",
              "video": "video", "clip": "clip", "reel": "reel", "story": "story"}
VIDEO_MEDIA = ("video", "clip", "reel", "story", "tiktok")

# The words a caption filter on any of these platforms is likely to look at. This is this app's
# own list, not a published one - no platform publishes the list it applies - and it never
# blocks: it names the word so she can decide whether the reach is worth it.
WATCHED = ("sex", "sexual", "nude", "naked", "topless", "drunk", "hookup", "onlyfans",
           "weed", "high", "vape", "kill", "hate", "slut", "bitch", "cum", "period", "crack")

# How a photo was taken is not a detail of what is in it. "mirror selfie" is a fine subject for a
# caption and a useless answer to "which part specifically", so the detail slot looks past these
# words - and says so when there is nothing else to find.
CAMERA_WORDS = frozenset(("selfie", "mirror", "photo", "pics", "picture", "shot", "video",
                          "clip", "reel", "story", "post", "ootd", "grwm", "angle", "frame",
                          "fitcheck", "casual", "cute", "nice", "loose"))


@dataclass(frozen=True)
class Tone:
    """One temperature: the shapes it writes, what it is for, and what it tends to cost."""
    id: str
    name: str
    line: str
    shapes: tuple
    hooks: tuple
    emoji: tuple
    shout: bool
    cost: str

    def is_video(self, media: str) -> bool:
        return (media or "").strip().lower() in VIDEO_MEDIA


# The shapes are written already contracted and already lowercase, because that is the sentence a
# person types. They take {thing} (the head noun) rather than {thing} (the whole description) for
# the same reason a friend does not repeat the colour, the fabric and the item back to you.
TONES = (
    Tone("cunty", "Cunty",
         "Dry, short, slightly mean. It is a filter, not a net: the people it attracts are the "
         "ones who already get it.",
         ("no it's not for you",
          "i'm not answering where the {thing} is from, sorry",
          "the {thing} again and i'm not even sorry",
          "if you're asking about the {thing}, it's already gone",
          "i said what i said about the {thing}",
          "the {thing} stays, everything else goes",
          "i already posted the {thing} {count} times this week",
          "the {thing} is the whole {form}"),
         ("you're gonna ask about the {thing}",
          "no context for the {thing}",
          "the link on the {thing} stays with me"),
         (), False,
         "Reads cold to strangers, so it grows a smaller, stickier audience than a warm line."),
    Tone("lit", "Lit",
         "High energy, straight hype. Works when the thing really is the reason for the post.",
         ("okay but the {thing} did something to me",
          "the {thing} is unreal, i'm not even exaggerating",
          "i'm not gonna shut up about the {thing} this month",
          "been wearing the {thing} since {day}, no notes",
          "i need the {thing} in every color, that's the whole ask",
          "{count} tries and the {thing} still won",
          "the {thing} won and i just let it"),
         ("stop. the {thing}.",
          "the {thing} is why you're watching this"),
         ("🔥", "🫶", "😭"), True,
         "Shouts on a quiet feed. It wins on a good frame and looks like nothing on a bad one."),
    Tone("funny", "Funny",
         "Misdirection: the setup is the post, the turn is the caption. The joke is on her own "
         "habit, which is the only kind that does not read mean.",
         ("bought the {thing} for one thing, wore it to everything",
          "the {thing} is doing more work than i am",
          "nobody asked about the {thing} and everybody looked",
          "i told myself the {thing} was a once thing",
          "i own {count} of the {thing} and still wear the same one",
          "the {thing} has its own schedule now",
          "my camera roll is {count} photos of the {thing}"),
         ("the {thing} has a plot now",
          "watch the {thing}, not me"),
         ("😭", "🙃"), False,
         "A joke that lands costs the information: nobody remembers what the post was actually "
         "about."),
    Tone("niche", "Niche",
         "Insider. It names the detail a stranger would not notice, which is exactly why the right "
         "people stop on it. This is the tone that cannot work off a two-word description, and it "
         "says so instead of faking one.",
         ("{piece} - that's why it sits the way it does",
          "the {piece} is the part you can't see on a screen",
          "you'd only notice the {piece} in person",
          "the {piece} is the whole reason for this {form}",
          "{detail} - that's the part a phone kills"),
         ("close enough to see the {piece}",
          "{piece} is the reason for this {form}"),
         (), False,
         "Invisible to anyone outside the thing. That is the trade, not a fault."),
    Tone("aesthetic", "Aesthetic",
         "A fragment. Two or four words, no first person, nothing explained - the frame is doing "
         "the talking.",
         ("{thing}, nothing else",
          "the {detail} one",
          "{thing} and the light",
          "{thing}, {count} frames",
          "no caption for the {thing}"),
         ("{thing}, {count} frames",
          "nothing about the {thing} explained"),
         ("🕯", "🤍"), False,
         "Saves well and comments badly: there is nothing in it for a stranger to answer."),
    Tone("soft", "Soft",
         "Warm and full-sentence, with the line left open at the end. The one that gets replies "
         "from people who do not know her.",
         ("the {thing} on a day that didn't ask much",
          "i kept coming back to the {thing}",
          "wore the {thing} like it owes me something",
          "the {thing} and nothing else today",
          "does the {thing} look better in this light"),
         ("the {thing}, and the rest of the day",
          "it's only the {thing}"),
         ("🌤",), False,
         "Easy to scroll past. It reads kind, not interesting, when the frame is quiet."),
)

BY_ID = {t.id: t for t in TONES}
# The day slot in the lit shapes: a real weekday or nothing at all. The page and the agent both
# pass today's date, so the line names a day she can check; a bare slots() call leaves the shape
# out rather than printing a Tuesday nobody picked.
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def tone(tone_id: str):
    return BY_ID.get((tone_id or "").strip().lower())


def phrases(subject: str) -> list:
    """The concrete runs in her own description, in the order she said them.

    "mirror selfie in the black ribbed tank" gives ["mirror selfie", "black ribbed tank"] - the
    tail is what a person is actually pointing at, so it becomes the subject of the sentence."""
    keep = [w for w in re.split(r"[\s,;/]+", (subject or "").strip()) if w]
    runs, cur = [], []
    for w in keep:
        if WORD.fullmatch(w) and w.lower().strip(".,!") not in _STOP:
            cur.append(w)
        elif cur:
            runs.append(" ".join(cur))
            cur = []
    if cur:
        runs.append(" ".join(cur))
    return runs


def slots(subject: str, today=None, media: str = "photo") -> dict:
    """What each shape fills itself with, every value traceable to a word she typed.

    ``thing`` is the tail run as she described it, ``part`` is what a sentence calls it - the head
    noun, with the colour and the fabric taken back out - and ``detail`` is those modifiers alone.
    ``piece`` is the modifiers and the head noun together, which is the one place the full
    description belongs: in the niche tone the detail *is* the caption, and "the black ribbed" on
    its own is an adjective with nothing left standing behind it. With no detail the key comes back
    empty on purpose: the shapes that need one are then skipped and counted, not padded out.
    ``count`` is empty unless her own sentence names a number, and ``day`` is empty unless a date
    was given, so a line never calls a Story a photo, claim three tries when she said two, or set a
    Tuesday that nobody picked.
    """
    runs = phrases(subject)
    thing = (runs[-1].lower() if runs else (subject or "").strip().lower()) or "it"
    bits = thing.split()
    part = bits[-1] if bits else ""
    modifiers = [w for w in bits[:-1] if w not in CAMERA_WORDS]
    if not modifiers:
        for run in reversed(runs[:-1]):
            found = [w for w in run.lower().split() if w not in CAMERA_WORDS]
            if found:
                modifiers = found
                break
    detail = " ".join(modifiers)
    said = register.say(thing, part)
    low = (media or "").strip().lower()
    count = DIGIT.search(subject or "")
    return {"thing": said, "part": part, "full": thing, "detail": detail,
            "piece": f"{detail} {part}".strip() or said,
            "count": SPOKEN.get(count.group(1).lower(), count.group(1)) if count else "",
            "form": FORM_WORDS.get(low, "video" if low in VIDEO_MEDIA else "photo"),
            "day": DAYS[today.weekday()] if today is not None else ""}


def _fits(shape: str, fills: dict) -> bool:
    """Whether every slot this shape asks for actually has a word behind it."""
    return all(fills.get(name) for name in SLOT.findall(shape))


def _seed(tone_id, subject, platform, n) -> random.Random:
    """Deterministic on purpose: the same ask twice gives the same three lines, so a reload is
    not a slot machine and the line she copied is still on the page."""
    return random.Random(f"{tone_id}|{(subject or '').lower()}|{platform}|{n}")


def _dedup(head: str, body: str, fills: dict) -> tuple:
    """Say it once. A hook and a line both built from her own words come out as "stop. the tank.
    the tank did something to me", which is how a template sounds. The line keeps the noun and
    loses the phrase, and says which word it swapped - but only when the noun is not what the
    sentence is standing on. Swapping a leading "the tank" gives "it again and i'm not even
    sorry", a caption with no subject."""
    thing = fills.get("thing") or ""
    if not (head and body and thing) or thing not in head or thing not in body:
        return body, ""
    lead = f"the {thing}"
    if lead in body and not body.startswith(lead):
        return body.replace(lead, "it", 1), "it"
    return body, ""


def _words(text: str) -> list:
    return [w for w in (t.strip(".,!?;:") for t in (text or "").lower().split()) if w]


def _echo(head: str, body: str) -> int:
    """How many words a hook and the line it fronts say twice.

    Two shapes built out of the same noun collide two ways: at the front, where both clauses open
    on "the black ribbed tank", and at the seam, where the hook ends naming the thing and the line
    opens naming it. Three words is the number that reads as a template; two is one noun used
    twice in one caption, which a person does not notice."""
    left, right = _words(head), _words(body)
    prefix = 0
    while prefix < len(left) and prefix < len(right) and left[prefix] == right[prefix]:
        prefix += 1
    seam = 0
    for k in range(1, min(len(left), len(right)) + 1):
        if left[-k:] == right[:k]:
            seam = k
    return max(prefix, seam)


def lines(tone_id: str, subject: str, profile, platform: str = "reels", media: str = "photo",
          today=None, n: int = 3, reg=None, report=None) -> list:
    """`n` caption candidates in this tone, cut to the placement's word budget.

    ``reg`` is the typing register (see ``src.captions.register``); callers that have her pasted
    captions in hand should pass one built from them, or the app's own default is used and says so.
    ``report``, if given, collects the lines that were dropped for reading like a template, so the
    page can count them instead of hiding the refusal."""
    got = tone(tone_id)
    if got is None:
        return []
    reg = reg or register.of(profile, [])
    fills = slots(subject, today, media)
    rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["reels"])
    video = got.is_video(media)
    budget = max(9, int(rules["words"] * 0.75)) if video else rules["words"]
    shapes = [s for s in got.shapes if _fits(s, fills)]
    hooks = [h for h in got.hooks if _fits(h, fills)] if video else []
    short = [s for s in got.shapes if not _fits(s, fills)]
    rng = _seed(got.id, subject, platform, n)
    rng.shuffle(shapes)
    rng.shuffle(hooks)
    out = []
    seen = set()
    for i in range(max(len(shapes), len(hooks))):
        if len(out) >= n:
            break
        shape = shapes[i % len(shapes)] if shapes else ""
        filled = shape.format(**fills) if shape else ""
        head = f"{hooks[i % len(hooks)].format(**fills).rstrip('. !')}." if hooks else ""
        body, said = _dedup(head, filled, fills)
        pair = f"{head} {body}" if head and body else (body or head)
        # When hook and line will not both fit, the line stays and the hook waits in a note under
        # it. Dropping the line instead was the failure this replaced: a long hook plus a short
        # shape meant the page filled with the same hook four times and her actual caption never
        # appeared. Truncating the pair is how a caption ends on "and the new", which is the tell
        # this whole module exists to kill.
        hook_off = ""
        twice = _echo(head, body) if head and body else 0
        if head and body and (twice >= 3 or len(pair.split()) > budget):
            text, hook_off = body, head
        else:
            text = pair
        if not text or text.strip().lower() in seen:
            continue
        bad = register.tells(text)
        if bad:
            if report is not None and text:
                report.setdefault("tells", []).append({"line": text, "why": bad[0]})
            continue
        seen.add(text.strip().lower())
        notes = []
        if said:
            notes.append(f"The hook already names it, so the line says {said!r} instead of running "
                         f"{fills['thing']!r} twice in one caption.")
        if hook_off:
            if twice >= 3:
                notes.append(f"The hook says the same {twice} words this line opens or closes on, "
                             f"so the line went alone - twice the same phrase in one caption is how "
                             f"a template reads. The pair would be: {pair}")
            else:
                notes.append(f"Just the line: hook and line together run past the {budget} words "
                             f"this placement holds. The hook in front of it would be: "
                             f"{hook_off.strip()}")
        if fills.get("full") and fills["full"] != fills.get("thing"):
            notes.append(f"The line calls it {fills['thing']!r} rather than repeating "
                         f"{fills['full']!r} - a sentence doesn't recite the colour, the fabric "
                         "and the item in one breath.")
        mark, why = register.marker_for(text, reg)
        if mark:
            text = register.place(text, mark)
            notes.append(f"{mark!r} is in there because {reg.provenance(mark)} - it goes "
                         f"there, {why}.")
        else:
            text, said_word = register.emphasize(text, reg)
            if said_word:
                notes.append(f"{said_word!r} was put in front of the claim, because "
                             f"{reg.provenance(said_word)} and this line is making one.")
        text, said_by = register.flatten(text, reg)
        fixed = register.corrected(text, reg)
        if fixed != text:
            notes.append("You said this once already, so the wording changed for good: "
                         f"{text!r} -> {fixed!r}.")
            text = fixed
        if got.shout and (reg.caps or profile.case_style == "capitalised"):
            # Caps only when her own samples use them; a shout typed quietly still reads. The
            # profile is checked as well as the register because a caller can hand over a measured
            # profile with a register built from nothing, and an unlearned voice is not shouted
            # either way.
            text = text.upper()
        if said_by:
            notes.extend(said_by)
        cut = _fit(text, budget)
        if cut != text:
            notes.append(f"Trimmed to {budget} words, which is what this placement reads as. The "
                         "cut lands on a whole word, not inside one.")
        text = cut
        if got.emoji and profile.emoji_per_sample >= 0.4:
            text = f"{text} {got.emoji[len(out) % len(got.emoji)]}"
            notes.append(f"The emoji is there because your samples run about "
                         f"{profile.emoji_per_sample} per message. Take it out if this post is "
                         "the exception.")
        elif got.emoji:
            notes.append("No emoji on it, because none of your samples carry them. Put your own "
                         "in if this post wants one.")
        if not reg.learned:
            notes.append("Voice unlearned: you have not pasted captions of your own, so this "
                         "typing is the app's default and every abbreviation stayed out.")
        if short:
            notes.append(f"{len(short)} of this tone's shapes ask for a detail of the thing itself "
                         "or a count, and your description did not give one. Name the item and what "
                         "is specific about it, or say how many, and the same tone writes more of "
                         "them.")
        out.append(Candidate(text, got, filled, platform, media, notes, fills))
    return out


@dataclass
class Candidate:
    """One line, with the filled sentence it was built from so the page can say why it reads like
    that - the sentence, never the template with its holes still in it."""
    text: str
    tone: Tone
    shape: str
    platform: str
    media: str
    notes: list = field(default_factory=list)
    fills: dict = field(default_factory=dict)

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def watched(self) -> list:
        low = self.text.lower()
        return sorted({w for w in WATCHED if re.search(r"(?i)\b" + re.escape(w) + r"\b", low)})

    def explain(self, profile) -> list:
        """The card under the line: the grammar it came from, what the tone costs, and every call
        this generator made on her behalf."""
        out = [f"{self.tone.name}: {self.shape}" if self.shape else self.tone.name,
               self.tone.cost]
        if self.tone.shout:
            out.append("Shouted in caps, because your samples shout."
                       if profile.case_style == "capitalised" else
                       "Kept lowercase - the shout is in the words, not the caps. It goes loud "
                       "only when your own captions do.")
        if self.watched:
            out.append("The word a caption filter looks at is "
                       + ", ".join(f"'{w}'" for w in self.watched)
                       + ". This list is ours, not a published one, and the line still posts - "
                         "what it risks is reach, not the account.")
        return out + self.notes
