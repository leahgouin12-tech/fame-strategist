"""The planner and the loop.

Two planners, one contract. With a key the model chooses tools from the catalogue;
without one the rulebook does, and the run says which one wrote the plan, because
"the AI decided" is not true on a machine with no key in it.
"""
from datetime import datetime

from src.agent import modes, roster, tools
from src.agent.roster import chain
from src.agent.tools import REGISTRY, Outcome

PLAN_SCHEMA = {
    "type": "object",
    "required": ["steps"],
    "properties": {
        "steps": {"type": "array", "items": {
            "type": "object", "required": ["tool"],
            "properties": {"tool": {"type": "string"}}}},
        "because": {"type": "string"},
    },
}

PROMPT = """You are the operating half of a local creator app. Pick the tools that carry out
the request, in the order they must run, using only these ids:
{catalogue}

Rules: a tool whose needs are unmet has been left out of that list, so do not invent one.
Reply as JSON: {{"steps": [{{"tool": "id", "args": {{}}}}], "because": "one sentence"}}.
Fewer tools, correctly run, beats a long list that will be skipped."""

# The rulebook: intent in, tool chain out. Only the first matching line runs, so the
# specific asks are above the general ones.
INTENTS = (
    (("trend", "research", "what is working", "hot", "emerging", "viral"),
     [("research.library", {}), ("research.week", {})]),
    (("niche", "position", "which audience", "brand"),
     [("strategy.niches", {})]),
    (("plan", "strategy", "eight weeks", "roadmap"),
     [("strategy.niches", {}), ("strategy.build", {}), ("day.list", {})]),
    (("judge", "score", "rate my", "which photo", "better picture", "compare"),
     [("media.judge", {})]),
    (("edit", "polish", "fix my", "enhance", "retouch"),
     [("media.judge", {}), ("media.polish", {})]),
    (("caption", "write", "copy for", "hook"),
     [("day.list", {}), ("copy.packs", {})]),
    (("reply", "comment", "dms", "community"),
     [("community.drafts", {})]),
    (("when should i", "best time", "window", "schedule"),
     [("metrics.window", {})]),
    (("numbers", "metrics", "views", "analytics", "did i grow"),
     [("metrics.window", {}), ("metrics.adapt", {}), ("research.coach", {})]),
    (("review", "coach", "how did it go", "week go"),
     [("research.coach", {})]),
    (("post", "today", "shoot", "film", "stage", "prepare"),
     [("day.list", {}), ("queue.stage", {})]),
    (("remember", "what do you know", "history"),
     [("memory.recall", {})]),
)
GROWTH = [("research.library", {}), ("strategy.niches", {}), ("strategy.build", {}),
          ("day.list", {}), ("queue.stage", {})]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def available(kit, mode) -> list[str]:
    """Only tools this mode is allowed to touch and this machine can actually run right now."""
    return [t.id for t in REGISTRY.values()
            if mode.allows(t.cap) and not t.blocked(kit)]


def rule_plan(kit, asked: str, desk=None) -> tuple[list[tuple[str, dict]], str]:
    if desk is not None:
        return chain(desk), f"{desk.name} (rulebook)"
    low = asked.lower()
    for words, chain_ in INTENTS:
        if any(w in low for w in words):
            return [(t, dict(a)) for t, a in chain_], "rulebook"
    return [(t, {}) for t in GROWTH], "rulebook"


def model_plan(kit, asked: str, mode, desk=None) -> tuple[list[tuple[str, dict]], str]:
    open_ids = available(kit, mode)
    if desk is not None:
        bench = {t.id for t in desk.staffed(kit)}
        open_ids = [i for i in open_ids if i in bench]
        if not open_ids:
            return rule_plan(kit, asked, desk)
    catalogue = "\n".join(f"- {REGISTRY[i].id}: {REGISTRY[i].describe}" for i in open_ids)
    data = kit.engine.complete_json(PROMPT.format(catalogue=catalogue), asked, PLAN_SCHEMA)
    wanted = [s.get("tool", "") for s in data.get("steps", []) if isinstance(s, dict)]
    steps, dropped = [], []
    for name in wanted:
        if name in open_ids:
            steps.append((name, {}))
        else:
            dropped.append(name)
    if not steps:
        return rule_plan(kit, asked, desk)
    who = f"{kit.engine.name}" + (f" ({desk.name})" if desk else "")
    return steps, who + (f" - dropped {', '.join(dropped)}" if dropped else "")


def plan_steps(kit, asked: str, mode, desk=None) -> tuple[list[tuple[str, dict]], str]:
    if kit.engine.name != "offline":
        try:
            return model_plan(kit, asked, mode, desk)
        except Exception as exc:              # noqa: BLE001 - a bad answer must not lose the ask
            steps, _ = rule_plan(kit, asked, desk)
            return steps, f"rulebook (the model answered unusably: {type(exc).__name__})"
    return rule_plan(kit, asked, desk)


def execute(kit, tool_id: str, args: dict) -> Outcome:
    tool = REGISTRY[tool_id]
    why = tool.blocked(kit)
    if why:
        return Outcome("skipped", f"Not run: {why}.")
    wanted = {k: v for k, v in (args or {}).items() if k in tool.args}
    try:
        return tool.run(kit, **wanted)
    except Exception as exc:                  # noqa: BLE001 - a tool that throws is a failed step
        return Outcome("failed", f"The tool stopped: {type(exc).__name__}: {exc}")


def run(kit, asked: str, mode_id: str, desk_id: str = "") -> dict:
    """One ask, one recorded run. `desk_id` is her naming somebody for the job; without it the
    sentence is routed, and a sentence that names no desk runs the growth loop as before."""
    mode = modes.get(mode_id)
    granted = kit.db.get_grants().get("auto", [])
    desk = roster.by_id(desk_id) if desk_id else roster.route(asked)
    steps, planner = plan_steps(kit, asked, mode, desk)
    if desk is not None and desk_id:
        planner = f"{desk.name} (you named the desk)"
    run_id = kit.db.start_run(asked.strip() or "run the growth loop", mode.id, planner, _now())
    for tool_id, args in steps:
        tool = REGISTRY.get(tool_id)
        if tool is None:
            kit.db.add_step(run_id, tool_id, args, "failed",
                            f"{tool_id} is not a tool this app has.", {}, _now())
            continue
        if not mode.allows(tool.cap):
            kit.db.add_step(run_id, tool_id, args, "skipped",
                            f"{mode.label} does not reach for {modes.CAP_LABEL[tool.cap]}.",
                            {}, _now())
            continue
        if not mode.runs_alone(tool.cap, granted):
            kit.db.add_step(run_id, tool_id, args, "advised",
                            "Planned, not run - it stops here until you press it.", args, _now())
            continue
        outcome = execute(kit, tool_id, args)
        kit.db.add_step(run_id, tool_id, args, outcome.kind, outcome.summary,
                        outcome.detail, _now())
    record = kit.db.get_run(run_id)
    kit.db.end_run(run_id, tally(record), _now())
    return kit.db.get_run(run_id)


def carry_out(kit, step_id: int) -> dict | None:
    """She pressed 'do it' on an advised step. It runs under the same tool, and the
    history keeps one entry with the verdict it actually earned.

    A skipped step stays skipped: that verdict is either an unmet need - which would fail
    again - or the mode refusing a capability, which is her policy and not hers to bypass
    by pressing a button. Retry a failed one as many times as you like."""
    row = kit.db.get_step(step_id)
    if row is None or row["kind"] not in ("advised", "failed"):
        return None
    if row["tool"] not in REGISTRY:
        return row
    outcome = execute(kit, row["tool"], row["args"])
    kit.db.redid_step(step_id, outcome.kind, outcome.summary, outcome.detail, _now())
    return kit.db.get_step(step_id)


# What a detail value leads with, in order: the sentence the step actually produced,
# then the shortest thing that identifies it.
_HEAD = ("claim", "text", "body", "name", "file", "written", "goal", "hours", "target",
         "post_ref", "ref", "id")
_TAIL = ("basis", "why", "because", "reason", "tier", "band", "score", "note", "as_of")


def _say(value) -> str:
    """One detail value as one line she can read."""
    if isinstance(value, dict):
        head = next((str(value[k]) for k in _HEAD if isinstance(value.get(k), (str, int, float))), "")
        if not head:
            head = "; ".join(f"{k.replace('_', ' ')} {v}" for k, v in list(value.items())[:2])
        tail = next((f" ({value[k]})" for k in _TAIL if isinstance(value.get(k), (str, int, float))), "")
        return head + tail
    if isinstance(value, (list, tuple)):
        return " · ".join(_say(v) if isinstance(v, (dict, list, tuple)) else str(v)
                          for v in list(value)[:14]) or "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def narrate(detail: dict) -> list[tuple[str, str]]:
    """The receipt under a step. The page shows these lines instead of the detail dict,
    because a wall of JSON is how an app looks automated without being useful."""
    out = []
    for key, value in (detail or {}).items():
        if value in (None, "", [], {}, 0):
            continue
        text = _say(value)
        if text and text != "none":
            out.append((key.replace("_", " "), text))
    return out[:8]


def tally(record: dict) -> str:
    kinds = [s["kind"] for s in record["steps"]]
    bits = []
    for kind, word in (("did", "done"), ("advised", "advised"),
                       ("skipped", "skipped"), ("failed", "failed")):
        n = kinds.count(kind)
        if n:
            bits.append(f"{n} {word}")
    return ", ".join(bits) or "nothing to run"


def next_move(kit) -> dict:
    """One obvious next action, because an ADHD brain should not have to derive it."""
    from src.agent.tools import _complete

    steps = {s["tool"] for s in (kit.db.recent_runs(1) or [{}])[0].get("steps", [])}
    if kit.answers() is None or not _complete(kit):
        return {"where": "/interview", "go": "Answer the eight questions",
                "why": "Everything downstream is sized to the hours you actually have."}
    if kit.plan() is None:
        return {"where": "/agent", "go": "Build the eight weeks",
                "why": "The plan is what makes a day's shot list mean something."}
    if not kit.photos():
        return {"where": "/photos", "go": "Drop the frames you shot into the inbox",
                "why": "The judge can only read files that are actually on this laptop."}
    if "queue.stage" not in steps:
        return {"where": "/today", "go": "Shoot today's list",
                "why": "Ticks are a shooting aid; the record is marking the day posted."}
    return {"where": "/numbers", "go": "Type tonight's three numbers",
            "why": "Below the floor the app refuses to guess, so numbers are what unlock an "
                   "opinion."}
