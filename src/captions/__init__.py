"""The two things a caption is actually chosen for: the temperature of the line, and the
tags that let a stranger find it.

`tone` writes the same post six ways - cunty, lit, funny, niche, aesthetic, soft - out of the
words she used to describe the shot, in the casing the voice profile measured. Nothing here is
a persona and nothing is a model's idea of a girl: each tone is a small grammar of sentence
shapes, and the slots are filled from her own sentence.

`tags` is the discoverability half, and it is deliberately narrower than a trending-hashtag
widget. No platform publishes a hashtag list this app can read, and scraping one would be a
forecast dressed as research, so every tag here carries the evidence that put it on the page -
a caption she wrote, the words she used for the shot, or her own posts under the hypothesis her
numbers favoured. A tag with no evidence is not shown at all.

`register` is the third half and the reason the other two got rewritten. It decides whether a
line is something she would actually type: what the sentence calls the item (the head noun, not
the whole description she typed for the generator), how it is typed (contracted, in her casing,
with only the abbreviations she uses), and which shapes are refused outright because they have
circulated as templates long enough to read as generated.

Neither half sanitises. An adult line is written because she asked for it; what the app adds is
the word a caption filter is likely to look at, as a note beside the line rather than a refusal
of it.
"""

from src.captions import register as caption_register
from src.strategist import voice as voice_module


def voice_register(db):
    """Her voice profile and her typing register, from the three things that decide whether a
    caption reads as hers: the captions she pasted, the two switches she set, and the corrections
    she already made to a line the app wrote.

    One call because every caller needs both halves and a caller that forgot the corrections would
    quietly re-ship a line she already rejected - which is the exact thing that makes a generator
    feel like it is not listening.
    """
    samples = db.get_voice()
    profile = voice_module.learn(samples)
    prefs = db.get_caption()
    reg = caption_register.of(profile, samples, want_abbrevs=bool(prefs["casual"]),
                             want_markers=bool(prefs["markers"]),
                             corrections=caption_register.fixes(db.recall("caption-fix")))
    return profile, reg
