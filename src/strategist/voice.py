"""Writer: it learns how she already talks, then writes inside that.

No model call and no persona. The profile is arithmetic over the samples she pasted -
sentence length, capitalisation, emoji, questions, the hashtags she already uses - and
the variants are cut to fit it. AI-sounding captions read as AI, so the only honest way
to sound like her is to measure her and use what the measurement says.
"""

from dataclasses import dataclass, field
from datetime import date
import re

from src.strategist.daily import BANNED_HASHTAGS, FORMATS, local_copy

WORD = re.compile(r"[A-Za-z][A-Za-z']+")
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")
HASHTAG = re.compile(r"#[A-Za-z0-9_]{2,24}")
FIRST_PERSON = {"i", "me", "my", "mine", "we", "us", "our"}
SECOND_PERSON = {"you", "your", "yours", "u", "ur"}
STOP = {"the", "and", "that", "this", "with", "from", "have", "been", "what", "when",
        "just", "like", "got", "can", "will", "would", "about", "into", "for", "are"}

# The same media, rewritten: each platform is read differently, so each gets its own
# word budget and tag count rather than one copy pasted three times.
PLATFORM_RULES = {
    "tiktok": {"words": 22, "tags": 5, "shape": "hook spoken in the first second, then the ask"},
    "reels": {"words": 16, "tags": 4, "shape": "hook first, one line of context, tags under it"},
    "x": {"words": 11, "tags": 1, "shape": "the claim alone - a thread you will not have to write"},
}
PLATFORMS = tuple(PLATFORM_RULES)


@dataclass
class VoiceProfile:
    samples: int
    words_per_sentence: float
    questions: float
    first_person: float
    second_person: float
    lowercase_starts: float
    emoji_per_sample: float
    emoji_kinds: list[str]
    tags: list[str]
    openers: list[str]
    habits: list[str]
    notes: list[str] = field(default_factory=list)

    @property
    def learned(self) -> bool:
        return self.samples > 0

    @property
    def case_style(self) -> str:
        """Sentence starts, not total letters: almost any text is mostly lowercase letters,
        which is why counting them says nothing about how somebody types."""
        if not self.learned:
            return "unknown"
        if self.lowercase_starts >= 0.9:
            return "lowercase"
        return "capitalised" if self.lowercase_starts <= 0.1 else "mixed"

    def signature(self) -> list[str]:
        """Plain-language rules, each one traceable to a number on the card."""
        if not self.learned:
            return ["Nothing pasted yet, so nothing has been learned. Until you do, the writer "
                    "is guessing at your voice and will say so on every line."]
        out = [f"{self.words_per_sentence} words per sentence, averaged over {self.samples} "
               f"of your own samples."]
        out.append(f"You start {round(100 * self.lowercase_starts)}% of sentences without a "
                   "capital." + (" So the writer does not either."
                                 if self.case_style == "lowercase" else
                                 "" if self.case_style == "mixed" else
                                 " - the writer keeps that."))
        out.append(f"You end {round(100 * self.questions)}% of sentences with a question.")
        out.append(f"First person in {round(100 * self.first_person)}% of your words, "
                   f"second person in {round(100 * self.second_person)}%.")
        if self.emoji_per_sample:
            out.append(f"You use about {self.emoji_per_sample} emoji per message"
                       + (f" ({', '.join(self.emoji_kinds)})" if self.emoji_kinds else "") + ".")
        else:
            out.append("You do not use emoji, so nothing gets one.")
        if self.tags:
            out.append("Your own hashtags: " + " ".join(self.tags))
        if self.openers:
            out.append("You often start with: " + ", ".join(self.openers))
        if self.habits:
            out.append("Words you reach for: " + ", ".join(self.habits))
        return out


@dataclass
class Variant:
    platform: str
    hook: str
    caption: str
    tags: list[str]
    alt_prompt: str
    why: list[str]
    shape: str

    @property
    def block(self) -> str:
        return f"{self.hook}\n\n{self.caption}\n\n{' '.join(self.tags)}"


def _top(counts, limit):
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def _sentences(text: str) -> list[tuple[str, str]]:
    """Sentences kept with their terminator, because dropping it is how a question stops
    being detectable. A trailing fragment counts only if it carries two words - a lone
    hashtag at the end of a message is not a sentence."""
    out: list[tuple[str, str]] = []
    for line in re.split(r"\n+", text):
        tokens = re.split(r"([.!?])", line)
        for i in range(0, len(tokens) - 1, 2):
            if tokens[i].strip():
                out.append((tokens[i].strip(), tokens[i + 1]))
        tail = tokens[-1].strip()
        if tail and len(WORD.findall(tail)) >= 2:
            out.append((tail, ""))
    return out


def learn(samples: list[str]) -> VoiceProfile:
    clean = [s.strip() for s in samples if s and s.strip()]
    if not clean:
        return VoiceProfile(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [], [], [], [], [])
    chunks: list[tuple[str, str]] = []
    words: list[str] = []
    emoji: list[str] = []
    tags: dict[str, int] = {}
    for text in clean:
        chunks += _sentences(text)
        words += WORD.findall(text)
        emoji += EMOJI.findall(text)
        for tag in HASHTAG.findall(text):
            if tag.lower() not in BANNED_HASHTAGS:
                tags[tag] = tags.get(tag, 0) + 1
    openers: dict[str, int] = {}
    questions = upper_starts = 0
    for body, term in chunks:
        if body[0].isupper():
            upper_starts += 1
        if term == "?":
            questions += 1
        head = WORD.findall(body.lower())
        if head and head[0] not in STOP:
            openers[head[0]] = openers.get(head[0], 0) + 1
    counts = {}
    for w in words:
        k = w.lower()
        if len(k) >= 4 and k not in STOP:
            counts[k] = counts.get(k, 0) + 1
    repeat = [w for w, c in counts.items() if c >= 2]
    return VoiceProfile(
        samples=len(clean),
        words_per_sentence=round(len(words) / max(len(chunks), 1), 1),
        questions=round(questions / max(len(chunks), 1), 2),
        first_person=round(sum(1 for w in words if w.lower() in FIRST_PERSON) / max(len(words), 1), 2),
        second_person=round(sum(1 for w in words if w.lower() in SECOND_PERSON) / max(len(words), 1), 2),
        lowercase_starts=round(1 - upper_starts / max(len(chunks), 1), 2),
        emoji_per_sample=round(len(emoji) / len(clean), 1),
        emoji_kinds=_top({e: emoji.count(e) for e in set(emoji)}, 3),
        tags=_top(tags, 5),
        openers=_top(openers, 3),
        habits=_top({w: counts[w] for w in repeat}, 4),
    )


def recase(text: str, profile: VoiceProfile) -> str:
    """Public because the engagement drafts case themselves the same way she does. Every
    frame is written lowercase, so a writer who capitals gets the first letter back."""
    if not profile.learned:
        return text
    if profile.case_style == "lowercase":
        return text.lower()
    if profile.case_style == "capitalised":
        return text[:1].upper() + text[1:]
    return text


def _fit(text: str, budget: int) -> str:
    """Whole words only, ending on a sentence boundary the reader can hear."""
    parts = text.split()
    if len(parts) <= budget:
        return text
    cut = " ".join(parts[:budget]).rstrip(" ,;:")
    return cut + ("." if not cut.endswith((".", "!", "?")) else "")


def package(subject: str, hypothesis: str, day: date, profile: VoiceProfile,
            platforms=PLATFORMS) -> list[Variant]:
    base_hook, base_caption = local_copy(hypothesis, subject, day)
    format_tags = [t for t in FORMATS.get(hypothesis, (None, None, None, []))[3]
                   if t.lower() not in BANNED_HASHTAGS]
    out = []
    for platform in platforms:
        rules = PLATFORM_RULES[platform]
        hook = recase(_fit(base_hook, max(8, int(rules["words"] * 0.6))), profile)
        caption = recase(_fit(base_caption, rules["words"]), profile)
        if profile.learned and profile.questions >= 0.34 and "?" not in caption:
            caption = caption.rstrip(".") + "?"
            why_q = f"You question {round(100 * profile.questions)}% of the time, so the line ends open."
        else:
            why_q = ""
        if profile.emoji_per_sample >= 0.5 and profile.emoji_kinds:
            caption = f"{caption} {profile.emoji_kinds[0]}"
        tags = list(profile.tags)
        stem = "#" + hypothesis.split("-")[0].replace("_", "")
        for tag in [stem] + format_tags:
            if tag not in tags and tag.lower() not in BANNED_HASHTAGS:
                tags.append(tag)
            if len(tags) >= rules["tags"]:
                break
        tags = tags[:rules["tags"]]
        why = [f"{rules['words']} words, because your own sentences run "
               f"{profile.words_per_sentence if profile.learned else 'unstated'}."]
        why.append({"lowercase": "Left lowercase, the way you write.",
                    "capitalised": "Capitalised, the way you write.",
                    "unknown": "The app's own casing - you have not pasted a sample of yours.",
                    "mixed": "Casing kept mixed, the way you write."}[profile.case_style])
        if profile.tags:
            why.append(f"Tags are ones you already use, not a list off a trend page.")
        else:
            why.append("No tags of yours to reuse yet, so these come from the format itself.")
        why.append(f"Rewritten for {platform} rather than pasted: {rules['shape']}.")
        if why_q:
            why.append(why_q)
        out.append(Variant(platform, hook, caption, tags,
                           "Alt text is yours: only you can say what is in the frame. "
                           "The app will not describe a shot it has not seen you take.", why,
                           rules["shape"]))
    return out
