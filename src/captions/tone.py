"""Six temperatures, one post.

A caption is not "written" so much as chosen: the same mirror photo can be a dare, a fragment,
or a joke about the same tank worn for the sixth time. Each tone here is a small grammar - a
handful of sentence shapes with the slots left open - and the slots are filled from the words
she used to describe the shot, so the line is built out of her sentence and not out of a
persona somebody configured.

Five things keep it honest:

* the casing still comes from the voice profile, so a shouted shape goes quiet unless she
  actually types in caps - and the card says which way it went;
* a video gets a spoken hook in front of the line, and if hook plus line will not fit the
  placement's word budget the hook goes alone, because a caption cut off mid-sentence is the
  fingerprint of a machine;
* a shape that needs something she never gave - a detail, a number - is skipped and counted, not
  padded with "it", with the word "mirror", or with a count she did not say;
* the word for the post follows what she is posting, so a Story line never calls it a photo;
* nothing is filtered. An adult line is written when she asks for one, and the app adds the one
  word a caption filter is likely to look at, as a note beside the line instead of a refusal of
  it.
"""
from dataclasses import dataclass, field
import random
import re

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


TONES = (
    Tone("cunty", "Cunty",
         "Dry, unbothered, slightly mean. It is a filter, not a net: the people it attracts are "
         "the ones who already get it.",
         ("{thing}. that is the whole post.",
          "no, it is not for you",
          "you will ask where the {thing} is from and i will not answer",
          "the {thing} again. you have seen it twice, make it three",
          "not a request, a {form} of the {thing}",
          "no hair done for the {thing} and it still did more than yours"),
         ("you are about to see the {thing} {count} times",
          "no context for the {thing}, that is the point",
          "the {thing} is the whole {form}, sorry"),
         (), False,
         "Reads cold to strangers, so it grows a smaller, stickier audience than a warm line."),
    Tone("lit", "Lit",
         "High energy, straight hype. Works when the thing really is the reason for the post.",
         ("the {thing} is actually unreal",
          "i have not stopped with the {thing} since {day}",
          "this is the one. {thing}. that is it. that is the post",
          "the {thing} did something to me",
          "{count} tries and the {thing} still won"),
         ("stop. the {thing}.",
          "the {thing} is why you are watching this"),
         ("🔥", "🫶", "😭"), True,
         "Shouts on a quiet feed. It wins on a good frame and looks like nothing on a bad one."),
    Tone("funny", "Funny",
         "Misdirection: the setup is the post, the turn is the caption. The joke is on her own "
         "habit, which is the only kind that does not read mean.",
         ("me: i will wear the {thing} once. also me:",
          "{thing}: bought for one thing, worn to six",
          "the {thing} is doing work the rest of me is not",
          "nobody asked for this {thing} and everybody looked",
          "i own {count} of the {thing} and wear the same one",
          "the {thing} has seen more of the city than i have"),
         ("the {thing} has a plot now",
          "watch the {thing}, not me"),
         ("😭", "🙃"), False,
         "A joke that lands costs the information: nobody remembers what the post was actually "
         "about."),
    Tone("niche", "Niche",
         "Insider. It names the detail a stranger would not notice, which is exactly why the "
         "right people stop on it. This is the tone that cannot work off a two-word description, "
         "and it says so instead of faking one.",
         ("{detail}. that is why it sits like that",
          "{part} - that is the point, the rest of it is a room",
          "{thing}, and the part you can only see in person",
          "if you know the {part}, you know",
          "not the {thing} for everyone"),
         ("close enough to see the {part}",
          "{part} is the whole reason for this {form}"),
         (), False,
         "Invisible to anyone outside the thing. That is the trade, not a fault."),
    Tone("aesthetic", "Aesthetic",
         "A fragment. Two or four words, no first person, nothing explained - the frame is "
         "doing the talking.",
         ("{thing}, low sun",
          "the {thing} edit",
          "{part}, nothing else",
          "{thing}, twice",
          "quiet {thing}"),
         ("{thing}, {count} frames",
          "nothing about the {thing} is explained"),
         ("🕯", "🤍"), False,
         "Saves well and comments badly: there is nothing in it for a stranger to answer."),
    Tone("soft", "Soft",
         "Warm and full-sentence, with the line left open at the end. The one that gets replies "
         "from people who do not know her.",
         ("the {thing} on a day that asked nothing of me",
          "i kept coming back to the {thing}",
          "wearing the {thing} like it is the last warm day",
          "does the {thing} look better in this light or does everything",
          "nothing happened today so it is the {thing}"),
         ("the {thing}, and the rest of the day",
          "it is only the {thing}"),
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

    ``thing`` is the tail run (the whole phrase she pointed at), ``part`` its head noun and
    ``detail`` the modifiers standing in front of it. With no detail the key comes back empty on
    purpose: the shapes that need one are then skipped and counted, not padded out. ``count`` is
    empty unless her own sentence names a number, and ``day`` is empty unless a date was given,
    so a line never calls a Story a photo, claim three tries when she said two, or set a Tuesday
    that nobody picked.
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
    low = (media or "").strip().lower()
    count = DIGIT.search(subject or "")
    return {"thing": thing, "part": part, "detail": " ".join(modifiers),
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


def _shout(text: str, got: Tone, profile) -> str:
    """A shouted shape only shouts if she shouts. Caps from a woman who types in lowercase read
    as a different person, so the shout waits for evidence."""
    if not got.shout:
        return text
    return text.upper() if profile.case_style == "capitalised" else text.lower()


def _dedup(head: str, body: str, fills: dict) -> tuple:
    """Say it once. A hook and a line both built from her own three words come out as "stop. the
    black ribbed tank. the black ribbed tank did something to me", which is how a template sounds.
    The line keeps the noun and loses the phrase, and says which word it swapped."""
    thing = fills.get("thing") or ""
    part = fills.get("part") or ""
    if not (head and body and thing) or thing not in head or thing not in body:
        return body, ""
    if f"the {thing}" in body:
        return body.replace(f"the {thing}", "it", 1), "it"
    if part and part != thing:
        return body.replace(thing, part, 1), part
    return body, ""


def lines(tone_id: str, subject: str, profile, platform: str = "reels", media: str = "photo",
          today=None, n: int = 3) -> list:
    """`n` caption candidates in this tone, cut to the placement's word budget."""
    got = tone(tone_id)
    if got is None:
        return []
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
    for i in range(max(len(shapes), len(hooks))):
        if len(out) >= n:
            break
        shape = shapes[i % len(shapes)] if shapes else ""
        head = f"{hooks[i % len(hooks)].format(**fills).rstrip('. !')}." if hooks else ""
        body, said = _dedup(head, shape.format(**fills) if shape else "", fills)
        pair = f"{head} {body}" if head and body else (body or head)
        # A hook and a line that will not both fit means the hook alone. Truncating the pair is
        # how a caption ends on "and the new", which is the tell this whole module exists to kill.
        text = head if head and body and len(pair.split()) > budget else pair
        notes = []
        if said:
            notes.append(f"The hook already names it, so the line says {said!r} instead of "
                         f"running {fills['thing']!r} twice in one caption.")
        if text == head and body:
            notes.append(f"The hook went on its own: hook and line together run past the "
                         f"{budget} words this placement holds, and a caption cut off in the "
                         "middle is not a caption.")
        text = _shout(text, got, profile)
        cut = _fit(text, budget)
        if cut != text and not (text == head and body):
            notes.append(f"Trimmed to {budget} words, which is what this placement reads as. The "
                         "cut lands on a whole word, not inside one.")
        text = recase(cut, profile)
        if got.emoji and profile.emoji_per_sample >= 0.4:
            text = f"{text} {got.emoji[len(out) % len(got.emoji)]}"
            notes.append(f"The emoji is there because your samples run about "
                         f"{profile.emoji_per_sample} per message. Take it out if this post is "
                         "the exception.")
        elif got.emoji:
            notes.append("No emoji on it, because none of your samples carry them. Put your own "
                         "in if this post wants one.")
        if not profile.learned:
            notes.append("Voice unlearned: you have not pasted captions of your own, so this "
                         "casing is the app's, not yours.")
        if short:
            notes.append(f"{len(short)} of this tone's shapes ask for a detail of the thing "
                         "itself or a count, and your description did not give one. Name the item "
                         "and what is specific about it, or say how many, and the same tone writes "
                         "more of them.")
        out.append(Candidate(text, got, shape, platform, media, notes, fills))
    return out


@dataclass
class Candidate:
    """One line, with the shape it came from so the page can say why it reads like that."""
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
            out.append("Shouted in caps, because your samples are not lowercase."
                       if profile.case_style == "capitalised" else
                       "Kept lowercase - the shout is in the words, not the caps. It goes loud "
                       "only when your own captions do.")
        if self.watched:
            out.append("The word a caption filter looks at is "
                       + ", ".join(f"'{w}'" for w in self.watched)
                       + ". This list is ours, not a published one, and the line still posts - "
                         "what it risks is reach, not the account.")
        return out + self.notes
