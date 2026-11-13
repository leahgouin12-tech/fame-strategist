"""Engagement drafting - the legitimate half of "do things for my account".

The app writes the labour around a reply, never the facts inside it. What only she knows
stays a marked blank, and a comment that does not deserve a reply is refused one. Nothing
in this module sends, schedules, posts or logs into anything: the queue is a list she works
through with her own thumbs.
"""

from dataclasses import dataclass
import re

from src.strategist.voice import VoiceProfile, recase

LINE = re.compile(r"^\s*@?([^:\-\n]{1,28})[:\-]\s*(.+)$")
URL = re.compile(r"https?://|www\.|\.com\b", re.I)

SPAM = ("follow back", "f4f", "sub4sub", "check my", "dm for", "earn", "crypto",
        "free followers", "promotion service", "guest post")
DEMAND = ("price", "how much", "where is", "where’d", "where'd", "link", "buy", "order",
          "size", "code", "ship", "store", "shop", "what jacket", "what pants")
# The thing a commenter says they are about to stop doing is detected from what they say
# around it, never from the word itself: that verb is banned from this codebase by
# tests/test_guardrails.py precisely so no code path here can ever act on it.
CRITICISM = ("cringe", "hate", "worse", "trash", "bot", "fake", "clickbait", "mid",
             "tryhard", "awkward", "annoying", "ugly", "cancel", "basic", "unsubscribe",
             "block you", "mute you", "done following")
PRAISE = ("love", "obsessed", "gorgeous", "need", "queen", "slay", "best", "saved",
          "cute", "amazing", "goal", "quality", "thanks for", "helped")
QUESTION_WORDS = ("who", "what", "where", "when", "how", "why", "is", "does", "can",
                  "do", "will", "should", "could")

# Reply priority: the ones that convert, then the ones that keep a section alive, then the
# one that is only worth closing politely. Spam is refused and never queued.
PRIORITY = ["demand", "question", "praise", "human", "criticism"]


@dataclass
class Draft:
    author: str
    comment: str
    intent: str
    line: str
    fills: list[str]
    why: str
    refused: bool = False
    replied: bool = False

    @property
    def key(self) -> str:
        """What a tick attaches to. The text itself, not a row number: deleting one comment
        off the paste would shift every number below it and mark the wrong replies."""
        return f"{self.author}|{self.comment}"


FRAMES = {
    "question": ("the answer is ____ - it is also in the bio now, so nobody has to ask twice.",
                 ["the answer only you have"],
                 "A question in your section is the only audience you can see out loud. "
                 "Answering it in public is free content and it gives the next person "
                 "permission to ask."),
    "demand": ("everything in this one is in the bio - the piece you mean is ____.",
               ["which piece it is"],
               "Price, stock and sizing are not this app's to guess, and a different answer "
               "per DM is how a section turns into a queue. One place, same answer, every time."),
    "praise": ("thank you - the ____ is the part I actually worked on.",
               ["the detail you care about"],
               "Naming the detail turns a thank-you into a reason to stay, and it tells the "
               "next viewer which part to look at."),
    "criticism": ("fair - not every one lands. the next one tests the version that ____.",
                  ["what you would change"],
                  "One line, no argument. Arguing with a critic costs you the people watching "
                  "the exchange, and this app will not draft a defence or a dig back."),
    "human": ("____ - that is the whole reason I post these.",
              ["the part you agree with"],
              "A short echo keeps the thread alive without pretending there was a question in it."),
}

SPAM_WHY = ("No reply, on purpose. Every answer to a link comment teaches your section to "
            "bring more of them, and it costs the two minutes you would have spent on a real one.")


def _said(tokens: set[str], low: str, entry: str) -> bool:
    """Short flags count only as whole words - "bot" is not a critic inside "both", and "mid"
    is not an insult inside "middle". Longer phrases still match inside a word, which is how
    "shipping" still reaches "ship"."""
    return entry in tokens if len(entry) <= 4 else entry in low


def _has(group: tuple[str, ...], low: str) -> bool:
    tokens = set(re.split(r"[^a-z']+", low))
    return any(_said(tokens, low, entry) for entry in group)


def classify(text: str) -> str:
    low = text.lower()
    if (URL.search(text) or _has(SPAM, low)
            or sum(c.isupper() for c in text) > len(text) * 0.6):
        return "spam"
    if _has(DEMAND, low):
        return "demand"
    if _has(CRITICISM, low):
        return "criticism"
    words = low.split()
    if "?" in text or (words and words[0] in QUESTION_WORDS):
        return "question"
    if _has(PRAISE, low):
        return "praise"
    return "human"


def parse(text: str) -> list[dict]:
    """One comment per line, either bare or as `name: text` - what a screen gives you when
    you copy it off the app, and what an export looks like after a save-as."""
    out = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        hit = LINE.match(line)
        out.append({"author": hit.group(1).strip() if hit else "someone",
                    "text": (hit.group(2) if hit else line).strip()})
    return out


def draft(comment: dict, profile: VoiceProfile) -> Draft:
    intent = classify(comment.get("text", ""))
    if intent == "spam":
        return Draft(comment.get("author", "someone"), comment.get("text", ""), intent, "", [],
                     SPAM_WHY, refused=True)
    line, fills, why = FRAMES[intent]
    return Draft(comment.get("author", "someone"), comment.get("text", ""), intent,
                 recase(line, profile), fills, why)


def plan(comments: list[dict], profile: VoiceProfile) -> list[Draft]:
    drafts = [draft(c, profile) for c in comments]
    return sorted(drafts, key=lambda d: (d.refused,
                                         PRIORITY.index(d.intent) if d.intent in PRIORITY else 9))


def queue_note(drafts: list[Draft]) -> str:
    worth = [d for d in drafts if not d.refused]
    blocked = len(drafts) - len(worth)
    if not drafts:
        return ("Nothing pasted yet. Copy the comments off your post - every platform lets you "
                "select and copy them, and this app needs no login to work with the text.")
    return (f"{len(drafts)} comment{'s' if len(drafts) != 1 else ''} read, {len(worth)} worth a "
            f"reply, {blocked} refused"
            + (" - answer what you can inside one sitting and leave the rest; a reply two days "
               "late still counts." if len(worth) > 3 else "."))


ASKS = ("link in bio", "link in my bio", "dm me", "message me", "shop", "buy now", "use my code",
        "join my", "subscribe", "early access", "waitlist")


def bio_review(bio: str, target_posts: int | None = None) -> list[dict]:
    """Checks that can be measured from the words she pasted. Nothing here is a taste claim:
    each line says which rule it applied and what the text did."""
    low = (bio or "").lower()
    asks = sum(1 for a in ASKS if a in low)
    out = [{
        "name": "one ask, or none",
        "passed": int(asks == 1),
        "note": (f"{asks} call{'s' if asks != 1 else ''} to action found. "
                 + ("One is enough - a bio with three asks lands none of them." if asks > 1 else
                    "One ask is the right number." if asks == 1 else
                    "No ask at all: a stranger reading this has been told nothing to do next.")),
    }, {
        "name": "who it is for",
        "passed": int(any(p in low for p in ("for ", "if you", "helping", "for people", "you "))),
        "note": ("Names an audience." if any(p in low for p in ("for ", "if you", "helping")) else
                 "Nobody is named. The line that decides a follow is the one that says who this "
                 "is for - not what it is about."),
    }, {
        "name": "a word they would search",
        "passed": int(len([w for w in re.findall(r"[a-z]{4,}", low) if w not in
                           {"this", "that", "with", "from", "have", "just", "like"}]) > 3),
        "note": "Bio text is indexed. A noun someone would type (the niche, the city, the craft) "
                "is worth more here than an adjective.",
    }, {
        "name": "length against the platform limit",
        "passed": int(len(bio or "") <= 150),
        "note": f"{len(bio or '')} characters. TikTok's bio is 80, Instagram's 150, X's 160 - "
                "so the same sentence does not fit all three, and the shortest version is the "
                "one worth writing first.",
    }]
    if target_posts:
        promised = any(p in low for p in ("new every", "daily", "each week", "weekly", "every day"))
        out.append({
            "name": "a cadence you can actually keep",
            "passed": int(promised and target_posts >= 3),
            "note": (f"The plan holds {target_posts} posts a week. "
                     + ("A public cadence promise is a debt - only make one the plan can pay."
                        if promised else
                        "No cadence promised here, which is the safe default until the posting "
                        "data says what you really keep.")),
        })
    return out


WATCH_FRAME = ("the ____ in your last one is the part I stopped scrolling for - which is the "
               "only reason I am in your comments at all.")
WATCH_WHY = ("Accounts you listed, not accounts the app found: it has no login and browses "
             "nothing, so naming them here would be guessing. What it can do is keep the "
             "comment from being generic - the detail has to come from something you saw.")


def watch_rows(text: str, profile: VoiceProfile) -> list[dict]:
    """One account per line, optionally `handle: what they posted`. The note is her memory,
    kept for her own reading; the draft never quotes it back as if the app had seen the post."""
    out = []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        hit = LINE.match(raw)
        who = (hit.group(1) if hit else raw).strip().lstrip("@").strip()
        if not who:
            continue
        out.append({"who": who, "note": (hit.group(2) if hit else "").strip(),
                    "line": recase(WATCH_FRAME, profile),
                    "fills": ["the one detail you actually noticed"], "why": WATCH_WHY})
    return out


def series_rows(best: dict, profile: VoiceProfile) -> list[dict]:
    """Continuations proposed from her own best post - titles and reasons, not scripts."""
    ref = best.get("post_ref", "that post")
    label = best.get("hypothesis") or "whatever format it was"
    rows = [{
        "title": recase(f"part two - the part of {ref} people asked about", profile),
        "why": "The comments on a winner are a brief. Answering the loudest question with a post "
               "is the cheapest follow-up there is.",
    }, {
        "title": recase(f"the same {label} with the thing I got wrong", profile),
        "why": "A mistake shown in public is the format that keeps the same audience and adds a "
               "reason to come back.",
    }, {
        "title": recase(f"{label}, but the version that costs half as much time", profile),
        "why": "A series has to survive your week. If the winner took two hours, the second "
               "installment has to take twenty minutes or it dies after one.",
    }]
    return rows
