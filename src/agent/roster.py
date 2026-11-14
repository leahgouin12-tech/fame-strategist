"""The desks the orchestrator actually staffs.

The command centre takes a sentence and hands it to somebody. A "specialist" here is a named
slice of the tool catalogue and nothing more: The Scout cannot be hired unless
`research.library` exists, and a tool that no desk owns would be work the org chart hides.
Both rules run when this module is imported, so a card with no work behind it raises with the
offender's name instead of turning up on the page as a button that does nothing.

This is also why the desk list is as long as it is and no longer: it is derived from the tools
that exist on this laptop, so every name on the page can be clicked, runs real code and leaves a
real step in the history. A department with no tool in it gets no card.
"""
from dataclasses import dataclass

from src.agent.tools import REGISTRY


@dataclass(frozen=True)
class Desk:
    """One named group of tools, the words that hand it work, and the line on its card."""
    id: str
    name: str
    line: str
    tools: tuple
    words: tuple

    def owns(self, tool_id: str) -> bool:
        return tool_id in self.tools

    def staffed(self, kit=None) -> list:
        """The tools on this desk. With a kit, only the ones that can actually run right now -
        a desk whose whole bench is waiting on her numbers is only honest if it says so."""
        out = []
        for tool_id in self.tools:
            tool = REGISTRY.get(tool_id)
            if tool is not None and (kit is None or not tool.blocked(kit)):
                out.append(tool)
        return out


DESKS = (
    Desk("research", "The Scout",
         "Reads the sourced library and this week's findings, and says what is actually moving.",
         ("research.library", "research.week", "memory.recall"),
         ("trend", "research", "what is working", "viral", "emerging", "library", "what do you "
          "know", "remember", "history", "findings")),
    Desk("strategy", "The Strategist",
         "Ranks the niches against your hours and writes the eight weeks that test them.",
         ("strategy.niches", "strategy.build"),
         ("niche", "position", "plan", "eight weeks", "roadmap", "strategy", "brand",
          "which audience")),
    Desk("producer", "The Producer",
         "Turns the week into today's shot list and stages the frames so posting is a drag.",
         ("day.list", "queue.stage", "day.mark"),
         ("today", "shoot", "film", "stage", "shot list", "what do i do", "tomorrow",
          "prepare", "line up")),
    Desk("editor", "The Editor",
         "Measures every frame in the inbox - light, sharpness, placement - and exports a look.",
         ("media.judge", "media.face", "media.polish"),
         ("judge", "score", "rate my", "which photo", "better picture", "compare", "edit",
          "polish", "fix my", "enhance", "retouch", "face", "looks best")),
    Desk("voice", "The Voice",
         "Writes the line for each placement in the casing she actually types in, in the "
         "temperature she asks for, picks the tags it can account for, and drafts the replies.",
         ("copy.packs", "copy.tone", "copy.tags", "community.drafts"),
         ("caption", "hook", "write", "copy", "reply", "replies", "comment", "what do i say",
          "wording", "tone", "cunty", "funny", "aesthetic", "selfie", "hashtag")),
    Desk("seo", "The Signpost",
         "Reads a post for the words a search could land on - only the ones her own posts, "
         "captions and plan can account for, and never a volume figure it cannot check.",
         ("seo.audit",),
         ("seo", "search", "searchable", "discover", "keyword", "alt text", "alt", "indexed",
          "index", "findable", "get found", "rank", "who is finding this")),
    Desk("metrics", "The Analyst",
         "Reads the numbers she typed, names a window from her own history and proposes the "
         "adjustment.",
         ("metrics.take", "metrics.window", "metrics.adapt", "research.coach"),
         ("numbers", "views", "analytics", "did i grow", "grew", "followers", "best time",
          "when should i", "adjust", "review", "how did it go", "week go", "coach")),
    Desk("experiment", "The Experimenter",
         "Files each post under the week's hypothesis and says what the two arms prove.",
         ("experiment.arms", "experiment.file"),
         ("test", "arm", "arms", "hypothesis", "lab", "prove", "verdict", "experiment",
          "which worked")),
    Desk("repurpose", "The Remixer",
         "Takes the posts the ledger already ranked and cuts them for the frames they never "
         "ran in.",
         ("repurpose.cuts",),
         ("repurpose", "reuse", "other shape", "other frame", "story", "rebuild the best",
          "cut these", "remake")),
    Desk("money", "The Bookkeeper",
         "Prices a paid post from her own views and her own hours, and reads the caption for "
         "the label that has to be on it.",
         ("money.quote", "money.label"),
         ("charge", "paid", "money", "sponsor", "brand deal", "rate card", "invoice", "quote",
          "gifted", "disclosure", "is this an ad", "label", "how much should i ask")),
)


def check(desks) -> None:
    """No desk with a tool that does not exist, no tool on two desks, no tool with no desk.
    Runs at import below, and in a test with a roster she could never see, so the guard is
    proved rather than assumed."""
    seen: dict = {}
    for desk in desks:
        for tool_id in desk.tools:
            if tool_id not in REGISTRY:
                raise RuntimeError(f"{desk.name} is staffed by {tool_id}, which this app has no "
                                   "tool for.")
            if tool_id in seen:
                raise RuntimeError(f"{tool_id} sits on {seen[tool_id].name} and {desk.name}; a "
                                   "tool answers to one desk.")
            seen[tool_id] = desk
    unowned = sorted(set(REGISTRY) - set(seen))
    if unowned:
        raise RuntimeError(f"no desk owns {', '.join(unowned)} - the roster would hide work that "
                           "exists.")


check(DESKS)


def desks() -> tuple:
    return DESKS


def by_id(desk_id: str):
    return next((d for d in DESKS if d.id == desk_id), None)


def owner(tool_id: str) -> str:
    """The desk name a step in the history belongs to, or the tool id when the roster and the
    catalogue have drifted - which the import check makes impossible, so it only ever shows up
    for a step recorded before a tool was renamed."""
    return next((d.name for d in DESKS if tool_id in d.tools), tool_id)


def route(asked: str):
    """Which desk this sentence belongs to, or None.

    It counts matches rather than taking the first hit, so "research what is working then
    rebuild the plan" goes to the desk with two of its own words in it and not to whichever
    name happens to be early in the tuple."""
    low = (asked or "").lower()
    if not low.strip():
        return None
    best, hits = None, 0
    for desk in DESKS:
        n = sum(1 for w in desk.words if w in low)
        if n > hits:
            best, hits = desk, n
    return best


def chain(desk) -> list:
    """The whole bench, in the order it should run. Blocked tools stay in: the loop records
    them as `Not run: <what she still has to give it>`, which is a truer page than a silent
    short list."""
    return [(t.id, {}) for t in desk.staffed()]
