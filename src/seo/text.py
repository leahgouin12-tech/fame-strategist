"""Nothing here reaches a search engine, and that is the whole design.

A "SEO" panel in a tool like this is normally a list of guessed keywords with a fake volume
number next to each one. This app cannot get either: no platform tells a laptop with no server
and no session what a phrase is searched for, how often, or where her post sits for it. So the
two questions this module answers are the two that can be answered from files already on this
machine:

    which words could a search land on, and what put each one on the list
    does the post in front of me carry them - and does it carry them early enough to be read

The words are evidence-gated the way the tags on /captions are. A phrase is here because it is
the hypothesis one of her own posts ran under, because it is in the captions she pasted, or
because it is the format her plan is running this week. Nothing is imported from a keyword tool:
a volume figure is an estimate of queries nobody ran, and an app that cannot check one does not
print one.
"""
from dataclasses import asdict, dataclass
from datetime import date
from statistics import median
import re

from src.captions.tags import limit_for, slug
from src.experiment import ledger as experiment
from src.strategist.daily import BANNED_HASHTAGS, FORMATS
from src.strategist.voice import PLATFORM_RULES, STOP, WORD

# The part of a caption a reader sees before the platform folds the rest away. No platform prints
# the count, so this is this app's own reading and the page labels it as one.
FRONT = 90
# Below three letters a token is an article, not a search.
MIN_WORD = 3
# How much of an alt field may be the same word over before it reads as a keyword list. Ours,
# again: no style guide gives a ratio.
REPEAT_LIMIT = 0.4
UNNAMED = ("", "logged", "unknown")
# The words that mean an entry in the library is actually about text, and so is quotable here.
TEXT_WORDS = ("caption", "keyword", "search", "alt text", "hashtag", "title", "text on",
              "describ")

# What this module will never pretend to know. Printed on the page rather than left out, because
# a discoverability panel with no limits in it is the thing being criticised.
CANNOT = (
    "how many people search a phrase - no keyword tool is reachable from this machine, and a "
    "volume number here would be an estimate of queries nobody ran",
    "whether the post is indexed at all, or where it sits for any phrase",
    "what the accounts above you in a search page wrote - this app reads your text, not theirs",
    "the alt field of a post that is already live - the exports this app reads do not carry it",
    "whether the platform's own feed, as opposed to its search, shows the post to anybody",
)


@dataclass(frozen=True)
class Term:
    """One phrase a search could land on, with the thing that put it here."""
    phrase: str
    source: str        # your posts | your captions | your plan
    evidence: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Finding:
    """One check, what it found, and the smallest fix."""
    check: str
    verdict: str       # carried | missing | weak | unreadable
    line: str
    fix: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def words(text: str) -> list:
    return [w.lower() for w in WORD.findall(text or "")]


def parts(phrase: str) -> list:
    """The searchable content of a phrase: not the stop words, not the two-letter fragments."""
    out = [w for w in words(phrase) if len(w) >= MIN_WORD and w not in STOP]
    return out or [w for w in words(phrase) if len(w) >= MIN_WORD]


def _carried(term: Term, caption_words: set, tag_bodies: set) -> str:
    """Where the phrase turned up. Every content word of it in the caption counts, in any order -
    nobody writes "outfit and style" in a caption, they write the outfit and the style."""
    need = parts(term.phrase)
    if need and all(w in caption_words for w in need):
        return "the caption"
    if term.phrase.replace(" ", "").replace("-", "") in tag_bodies:
        return "a tag"
    if need and all(w in (" ".join(tag_bodies)) for w in need):
        return "a tag"
    return ""


def terms(rows, samples, plan, week=None) -> list:
    """Every phrase this app can account for, strongest evidence first, no duplicates.

    ``rows`` are her imported posts, ``samples`` the captions she pasted on the Writer page, and
    ``plan``/``week`` the eight weeks and the one it is running now.
    """
    out: list[Term] = []
    seen: set[str] = set()

    def add(phrase, source, evidence):
        clean = " ".join((phrase or "").lower().split())
        if not clean or clean in seen or not parts(clean):
            return
        seen.add(clean)
        out.append(Term(clean, source, evidence))

    by_tag: dict[str, list] = {}
    for r in rows or []:
        tag = (getattr(r, "hypothesis", "") or "").strip().lower()
        if tag and tag not in UNNAMED:
            # views, not reach: views is the one number every import path has to carry (it is in
            # REQUIRED) and the one the app's own re-save keeps, so this line is never quietly
            # quoting a column that arrived empty.
            by_tag.setdefault(tag, []).append(int(getattr(r, "views", 0) or 0))
    for tag, plays in sorted(by_tag.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        live = sorted(v for v in plays if v > 0)
        add(tag.replace("-", " "), "your posts",
            f"{len(plays)} of your posts ran under {tag!r}"
            + (f", median {int(median(live)):,} views" if live
               else ", no views read on them yet"))

    got = experiment.ledger(rows or [])
    for arm in got.arms[1:4]:
        if arm.n >= 2:
            add(arm.label.replace("-", " "), "your posts",
                f"{arm.n} posts, {arm.rate_text} per post - {arm.watch}% watched on average")

    counts: dict[str, int] = {}
    for text in samples or []:
        # One token counts once per caption, not once per appearance: a caption that says the
        # same word three times is one caption she wrote, and "6 times" would be a lie about it.
        tokens = {slug(t).lstrip("#").lower() for t in _tags(text)} | set(words(text))
        for token in tokens:
            if len(token) >= MIN_WORD and token not in STOP:
                counts[token] = counts.get(token, 0) + 1
    for token, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if n >= 2 and len(out) < 24:
            add(token, "your captions",
                f"it is in {n} of the {len(samples or [])} captions you pasted, so it is your "
                "wording")

    if week is not None and plan is not None:
        # A plan lends its hypothesis NAMES, never its goal sentences: "Experiment: run
        # hypothesis 1 of 6 - lifestyle day in life" is an instruction to her, and the words a
        # search could land on inside it are the hypothesis name the plan already stores.
        names = [str(h).strip().replace("-", " ")
                 for h in (getattr(plan, "hypotheses", []) or []) if str(h).strip()]
        running = (getattr(week, "experiment", "") or "").strip().replace("-", " ")
        if running and running in names:
            add(running, "your plan",
                f"week {week.week_no} of the eight weeks is running it as the hypothesis, so "
                "this post is meant to feed it")
        chosen = str(getattr(plan, "chosen", "") or "").strip().replace("-", " ")
        if chosen:
            add(chosen, "your plan",
                "the eight weeks were built on it, so every week of the plan is meant to feed it")
    return out


def _tags(text: str) -> list:
    """The hashtags in one pasted caption, with the # taken off."""
    out, i = [], 0
    low = text or ""
    while True:
        at = low.find("#", i)
        if at < 0:
            return out
        run = ""
        for ch in low[at + 1:]:
            if ch.isalnum() or ch == "_":
                run += ch
            else:
                break
        if run:
            out.append(run)
        i = at + 1 + len(run)


def split(text: str) -> tuple:
    """A pasted block into the sentence and its tags.

    The tags come out before the caption is read, because "#thrifted" contains the word
    thrifted: an audit that read the raw paste would report every tag it carries as a phrase
    written in the sentence, which is exactly the claim this page is supposed to be able to
    tell apart.
    """
    bodies = _tags(text)
    if not bodies:
        return (text or "").strip(), []
    return re.sub(r"#[A-Za-z0-9_]+", " ", text or "").strip(), ["#" + b for b in bodies]


def rules(entries, today=None) -> list:
    """What the sourced library actually says about text, quoted with its citation.

    A stale entry or a folklore one does not get quoted as guidance: the first has no live date
    behind it and the second is a habit nobody measured.
    """
    today = today or date.today()
    out = []
    for e in entries or []:
        if e.is_stale(today) or e.confidence.value == "folklore":
            continue
        text = " ".join((e.claim, e.mechanism)).lower()
        if not any(w in text for w in TEXT_WORDS):
            continue
        src = e.sources[0] if e.sources else None
        out.append({"claim": e.claim, "confidence": e.confidence.value,
                    "mechanism": e.mechanism, "source": src.title if src else "",
                    "where": src.url if src else "", "tier": src.tier.value if src else "",
                    "does_not_claim": e.does_not_claim})
    return out


def _join(items: list) -> str:
    """The list, and the verb that agrees with it."""
    return ", ".join(items) + (" is" if len(items) == 1 else " are")


def _fold(front: list, late: list, tag_only: list) -> Finding:
    """Whether the phrases sit where a reader is actually shown them.

    Three different problems, so they are told apart instead of flattened into one "not before
    the fold": a phrase written at the end of a caption is an ordering fix, a phrase that lives
    only in a tag is a different fix, and a phrase that is nowhere in the text is not a fold
    question at all.
    """
    fold = f"the first {FRONT} characters, the part a reader sees before the platform folds the " \
           f"rest away"
    if front:
        return Finding("said before the fold", "carried",
                       f"{', '.join(front)} appear{'s' if len(front) == 1 else ''} inside {fold}.")
    if late:
        return Finding("said before the fold", "weak",
                       f"{_join(late)} written in the caption but after {fold} - so the sentence "
                       "a reader is shown does not contain them.",
                       f"Move the phrase up into the first {FRONT} characters.")
    if tag_only:
        return Finding("said before the fold", "weak",
                       f"{_join(tag_only)} only in a tag, never said in the caption itself. The "
                       f"fold is a line in the caption; a tag list is not behind it, so nothing "
                       "here can claim the words were placed early.",
                       "Say the phrase in the first line of the caption, not only inside a tag.")
    return Finding("said before the fold", "missing",
                   f"There is nothing to place inside {fold}: no phrase this app can account for "
                   "is in the post at all.")


def audit(caption="", hashtags=(), alt="", found=(), platform="instagram",
          shape="reels") -> dict:
    """Read one post the way a search surface would, and say what cannot be seen.

    ``found`` is the list from ``terms``; the audit never invents a phrase to check against.
    """
    cap_words = set(words(caption))
    bodies = [slug(t).lstrip("#").lower() for t in hashtags or [] if t]
    tag_bodies = set(bodies)
    vocab = {w for t in found for w in parts(t.phrase)}
    alt_words = words(alt)
    head = " ".join(words(caption[:FRONT])).lower()

    carried, missed = [], []
    for t in found:
        where = _carried(t, cap_words, tag_bodies)
        (carried if where else missed).append({"phrase": t.phrase, "where": where,
                                               "source": t.source, "evidence": t.evidence})

    cap_carried = [c["phrase"] for c in carried if c["where"] == "the caption"]
    front = [p for p in cap_carried if all(w in head for w in parts(p))]
    late = [p for p in cap_carried if p not in front]
    tag_only = [c["phrase"] for c in carried if c["where"] != "the caption"]
    out: list[Finding] = []
    if not (caption.strip() or alt.strip() or bodies):
        out.append(Finding("text on the post", "unreadable",
                           "Nothing to read: no caption, no tags and no alt field. A post with no "
                           "text on it cannot be landed on by a search of words.",
                           "Write the caption here, or stage the post on the composer first."))
        return {"findings": [f.as_dict() for f in out], "carried": [], "missed": [],
                "front": [], "late": [], "tagOnly": [], "spent": [], "head": "",
                "cannot": CANNOT}

    if found:
        names = [c["phrase"] for c in carried]
        if len(found) == 1:
            # One phrase and one post is the same sentence in two languages, and "none of the 1"
            # is not English.
            line = (f"The one phrase this app can account for is on the post: {names[0]}."
                    if names else
                    "The one phrase this app can account for is not in the text you wrote. That "
                    "is not a rule you broke - it comes from your own posts and your own "
                    "captions, so it is what your last posts trained on.")
        else:
            line = (f"{len(names)} of the {len(found)} phrases this app can account for are on "
                    f"the post: {', '.join(names)}." if names else
                    f"None of the {len(found)} phrases it can account for are in the text you "
                    "wrote. That is not a rule you broke - those phrases come from your own posts "
                    "and your own captions, so they are what your last posts trained on.")
        out.append(Finding("words a search could land on", "carried" if carried else "missing",
                           line, "" if carried else
                           "Put one of the phrases in the first line, in words, not only in "
                           "a tag."))
        out.append(_fold(front, late, tag_only))
    else:
        out.append(Finding("words a search could land on", "unreadable",
                           "No phrase to check against: this app builds the list out of your "
                           "imported posts, the captions you paste and the week your plan is "
                           "running, and none of those have given it a word yet.",
                           "Import numbers on the Numbers page or paste captions on the Writer."))

    if not alt.strip():
        out.append(Finding("alt field", "missing",
                           "The alt field is empty, so the picture itself carries no text at all. "
                           "It is the one field here that describes the frame rather than the "
                           "post.",
                           "One sentence naming the thing in the frame and one of the phrases "
                           "above."))
    else:
        uniq = set(alt_words)
        repeat = 1 - (len(uniq) / max(1, len(alt_words)))
        in_alt = [t.phrase for t in found
                  if all(w in set(alt_words) for w in parts(t.phrase))]
        if repeat > REPEAT_LIMIT:
            out.append(Finding("alt field", "weak",
                               f"The alt text repeats itself: {len(alt_words)} words, {len(uniq)} "
                               f"of them different. That reads as a list of keywords rather than a "
                               f"description, which is the shape a platform treats as spam in this "
                               f"field.",
                               "Say it as one sentence about the frame."))
        elif not in_alt:
            out.append(Finding("alt field", "weak",
                               "The alt text describes the picture but carries none of the phrases "
                               "this app can account for.",
                               "Name the thing in the frame in the words you used for it "
                               "elsewhere."))
        else:
            out.append(Finding("alt field", "carried",
                               f"The alt text is a sentence and carries {in_alt[0]!r}."))

    spent = []
    for tag, body in zip([t for t in hashtags or [] if t], bodies):
        if body in BANNED_HASHTAGS or f"#{body}" in BANNED_HASHTAGS:
            spent.append({"tag": tag, "why": "the tags this app drops from every list because "
                                             "they are how a post reads as chasing the feed"})
            continue
        known = [w for w in vocab if w in body]
        if not known:
            spent.append({"tag": tag, "why": "this app cannot split this tag into words it knows, "
                                             "so it cannot say whether it adds anything"})
        elif not [w for w in known if w not in cap_words]:
            spent.append({"tag": tag, "why": "every word in it is already in the caption, so it "
                                             "spends a tag slot on a restatement"})
    cap_limit = limit_for(platform)
    if len(bodies) > cap_limit:
        spent.append({"tag": f"{len(bodies)} tags",
                      "why": f"{cap_limit} is what this app reads as the most a {platform} post "
                             f"carries before it looks like a wall"})
    budget = PLATFORM_RULES.get(shape, PLATFORM_RULES["reels"])["words"]
    wrote = len(words(caption))
    if wrote > budget:
        out.append(Finding("caption length", "weak",
                           f"{wrote} words, over the {budget} this app reads a "
                           f"{platform} caption as holding. The fold cuts the rest, and the cut "
                           "lands mid-sentence.",
                           "Cut to the line, not the paragraph."))
    return {"findings": [f.as_dict() for f in out], "carried": carried, "missed": missed,
            "front": front, "late": late, "tagOnly": tag_only, "spent": spent, "head": head,
            "cannot": CANNOT}


def gaps(rows, samples, plan) -> list:
    """Why the list is as short as it is, said out loud."""
    out = []
    rows = list(rows or [])
    if not rows:
        out.append("Nothing has been imported yet, so there is no post of yours whose numbers "
                   "could rank a phrase. The Numbers page reads a CSV or three typed lines.")
    elif not any((getattr(r, "hypothesis", "") or "").strip() for r in rows):
        out.append("None of the posts you imported carries a hypothesis, so nothing here can be "
                   "ranked by what your own numbers did. The Lab files them.")
    if not samples:
        out.append("Nothing you have written is pasted, so the app has no wording of yours to "
                   "read phrases out of.")
    if plan is None:
        out.append("There is no eight-week plan, so no week is running and no format is feeding "
                   "this post.")
    return out
