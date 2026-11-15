"""Captions in the other languages she posts in, and the checks a translation has to pass.

`localise` holds both halves. The first is what a version may not touch - the hashtag, the handle,
the number, the brand in caps, the words she said to leave alone - read out of her own line so the
list is never something this app made up. The second is the check on what a model hands back: the
word budget for that placement in that language, her casing, her punctuation, an emoji she did not
use, a number that moved, and a version that quietly came back still in English.

There is deliberately no translation in here. A laptop with no server has no dictionary, so with no
model connected this module returns the reason plus a brief - the locked list, the budget, the
register notes and the language's watch line - which is the sheet she would hand a person who
speaks the language. A page that printed a guess in a confident font is the failure mode this whole
department is written to avoid.
"""

from src.language import localise


def targets(db, codes=None) -> list:
    """The languages to produce, from what she picked now or what she saved.

    One call for the page and the agent, because a tool that forgot her saved defaults would ask
    for Spanish only after she said she posts in Spanish and Kreyòl."""
    asked = [code for code in (codes or []) if localise.get(code)]
    if asked:
        return asked
    saved = db.get_language()
    return [code for code in saved["targets"] if localise.get(code)]


def keep(db, extra: str = "") -> str:
    """Her keep-words: the saved list plus whatever she named in this request, deduplicated.

    Order is kept because she typed them, and a duplicate would print the same word twice on a
    page whose whole claim is that it shows her what it actually has."""
    words = []
    for word in (db.get_language()["keep"] + " " + (extra or "")).replace(",", " ").split():
        if word.lower() not in [w.lower() for w in words]:
            words.append(word)
    return " ".join(words)
