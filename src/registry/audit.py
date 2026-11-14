"""What this repository can already do, read off the files instead of typed by hand.

Every entry names a thing that exists in the tree at the moment the audit runs: a route in
src/app.py, an action the agent can take, a control on an edit rail, a module with a header.
The acceptance column names the test files that mention it, so a feature nobody proves is
marked unproven on its face rather than quietly counted as finished.

The count is the count. It is not rounded up to a number somebody asked for, because a
registry padded to a target stops being evidence and becomes the thing it was supposed to
prevent - a claim with no implementation behind it.
"""

import ast
import re
from dataclasses import asdict, dataclass, field

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_PY = ROOT / "src" / "app.py"
BASE_HTML = ROOT / "src" / "templates" / "base.html"
SRC = ROOT / "src"
TESTS = ROOT / "tests"

DEPARTMENTS = ("Research", "Strategy", "Creation", "Editing", "Repurposing", "Publishing",
               "Analytics", "Experimentation", "Community", "Monetization", "SEO", "Workflow",
               "Interface", "This machine")

# Which department a thing belongs to is decided by the words in what it is called, not by a
# table of names that goes stale the first time a route is added.
DEPT_BY_WORD = (
    # First, because "money.label" is about a caption that also mentions staging and accounts,
    # and those words sit further down this list.
    ("money", "Monetization"), ("monetiz", "Monetization"), ("sponsor", "Monetization"),
    ("disclos", "Monetization"), ("paid post", "Monetization"),
    # Ahead of the rest for the same reason: the SEO module talks about captions, sources,
    # numbers and plans, and every one of those words is lower down this list.
    ("seo", "SEO"), ("discoverab", "SEO"),
    ("repurpos", "Repurposing"),
    ("bench", "Analytics"), ("number", "Analytics"), ("metric", "Analytics"),
    ("spend", "Analytics"), ("weekly", "Analytics"), ("adapt", "Analytics"),
    ("hypothesis", "Experimentation"), ("experiment", "Experimentation"),
    ("trend", "Research"), ("source", "Research"), ("research", "Research"),
    ("niche", "Strategy"), ("plan", "Strategy"), ("interview", "Strategy"),
    ("coach", "Strategy"), ("strateg", "Strategy"),
    ("edit", "Editing"), ("photo", "Editing"), ("clip", "Editing"), ("retouch", "Editing"),
    ("colour", "Editing"), ("design", "Editing"), ("brush", "Editing"), ("pixel", "Editing"),
    ("story", "Publishing"), ("account", "Publishing"), ("stage", "Publishing"),
    ("engage", "Community"), ("graph", "Community"), ("reply", "Community"),
    ("write", "Creation"), ("caption", "Creation"), ("voice", "Creation"),
    ("hook", "Creation"),
    ("agent", "Workflow"), ("command", "Workflow"), ("run", "Workflow"), ("tool", "Workflow"),
    ("phone", "This machine"), ("engine", "This machine"), ("gate", "This machine"),
    ("registry", "This machine"), ("machine", "This machine"),
)

KINDS = ("route", "action", "control", "module")


@dataclass
class Entry:
    """One registered thing. `key` is stable, so the registry can be re-run and diffed."""
    key: str
    name: str
    kind: str
    dept: str
    describe: str
    purpose: str
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    depends: list = field(default_factory=list)
    acceptance: list = field(default_factory=list)
    status: str = "unproven"
    where: str = ""
    reach: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def department(*hints) -> str:
    """The first department whose word appears in any hint, else Interface."""
    hay = " ".join(str(h).lower() for h in hints)
    for word, dept in DEPT_BY_WORD:
        if word in hay:
            return dept
    return "Interface"


def departments(entries: list) -> list:
    """Only the departments this tree actually has work in, in the canonical order.

    The filter on the registry page is built from this, so it can never offer a department
    that would show an empty list - a control that returns nothing is the thing this app is
    told not to build."""
    named = [d for d in DEPARTMENTS if any(e["dept"] == d for e in entries)]
    return named + sorted({e["dept"] for e in entries} - set(DEPARTMENTS))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "root"


def first_line(doc: str) -> str:
    """The summary line of a docstring, which is the sentence the author already wrote for
    exactly this purpose - so the registry quotes it instead of inventing a description."""
    if not doc:
        return ""
    lines = [ln.strip() for ln in doc.strip().splitlines() if ln.strip()]
    out = lines[0]
    for extra in lines[1:]:
        if out.endswith((".", ":", "?")) or len(out) > 150:
            break
        if extra.startswith(("Args:", "Returns:", "Raises:", "Example", ">>>")):
            break
        out += " " + extra
    return out[:400]


def paragraph(doc: str) -> str:
    """The whole first paragraph of a header. The summary line says what a thing is; the
    paragraph after it is where an author puts why it exists, which is the part a registry
    is for - so the two fields are not allowed to be the same sentence twice."""
    if not doc:
        return ""
    return re.sub(r"\s+", " ", doc.strip().split("\n\n")[0]).strip()[:900]


def _alias_map(tree: ast.Module) -> dict:
    """`from src.metrics import bench as benchmod` -> benchmod: src.metrics.bench, so a call
    in a route body can be traced to the module that really answers it."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                out[a.asname or a.name] = (node.module or "") + "." + a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split(".")[0]] = a.name
    return out


def _form_inputs(fn: ast.FunctionDef) -> list:
    """What the route reads: every argument with a Form default is a field it submits with,
    every other defaulted argument is a query string it answers to."""
    got = []
    for arg, default in zip(reversed(fn.args.args), reversed(fn.args.defaults or [])):
        if arg.arg in ("self", "request", "response"):
            continue
        if isinstance(default, ast.Call):
            who = getattr(default.func, "id", None) or getattr(default.func, "attr", "")
            got.append(f"{arg.arg} ({who.lower() or 'value'})")
        else:
            got.append(f"{arg.arg} (query)")
    for arg in getattr(fn.args, "kwonlyargs", []):
        got.append(f"{arg.arg} (query)")
    return got


def _body_facts(fn, aliases: dict, by_name=None, seen=None) -> tuple:
    """The template it renders, what it hands back otherwise, and which modules it calls.

    Plenty of handlers are one line that calls a view helper written beside them, so this
    follows those in-repository calls. An audit that read only the handler body would tell
    her about twenty endpoints render no page when a page is exactly what they return, and
    the registry would be wrong in the direction that flatters the code.
    """
    by_name = by_name or {}
    seen = seen if seen is not None else set()
    templates, redirects, calls, served = [], [], set(), []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                if f.id == "page" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    templates.append(str(node.args[1].value))
                elif f.id == "RedirectResponse":
                    redirects.append("redirect")
                elif f.id in ("Response", "StreamingResponse", "FileResponse"):
                    served.append(served_as(node))
                elif not f.id.startswith("_"):
                    calls.add(f.id)
                if f.id in by_name and f.id not in seen:
                    seen.add(f.id)
                    deeper = _body_facts(by_name[f.id], aliases, by_name, seen)
                    templates += deeper[0]
                    redirects += deeper[1]
                    calls |= set(deeper[2])
                    served += deeper[3]
            elif isinstance(f, ast.Attribute):
                base = getattr(f.value, "id", None)
                if base in aliases:
                    calls.add(aliases[base])
                elif base:
                    calls.add(base)
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str) and node.value.value.startswith("/"):
                redirects.append(node.value.value)
    return templates, redirects, sorted(c for c in calls if not c.startswith("_")), served


def served_as(node: ast.Call) -> str:
    """What a raw Response hands back, read off the media_type it is built with."""
    for kw in node.keywords:
        if kw.arg == "media_type" and isinstance(kw.value, ast.Constant):
            return f"serves {kw.value.value}"
    return "serves bytes"


def _named_functions(tree) -> dict:
    """Every function in app.py by name, nested view helpers included - the thing a route
    actually returns usually lives in one of those."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, node)
    return out


def routes() -> list:
    """Every endpoint in src/app.py, with the form fields and template it is wired to.

    Both plain and async handlers count: the ones that read a file or render a frame are
    async, and an audit that only saw the sync half would report a third of the app missing.
    """
    tree = ast.parse(APP_PY.read_text(encoding="utf-8"))
    aliases = _alias_map(tree)
    by_name = _named_functions(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in ("get", "post", "put", "delete")
                    and dec.args and isinstance(dec.args[0], ast.Constant)):
                continue
            path = str(dec.args[0].value)
            method = dec.func.attr.upper()
            docs = ast.get_docstring(node) or ""
            templates, redirects, calls, served = _body_facts(node, aliases, by_name)
            got = (["renders " + t for t in dict.fromkeys(templates)]
                   + [s for s in dict.fromkeys(served)]
                   + ["redirects" for r in dict.fromkeys(redirects) if r == "redirect"])
            out.append(Entry(
                key=f"route:{method} {path}", name=first_line(docs) or f"{node.name}()",
                kind="route", dept=department(path, node.name, docs),
                describe=first_line(docs) or "No header yet.",
                purpose=paragraph(docs) or "Undocumented: the route does something the file "
                                           "does not say.",
                inputs=_form_inputs(node),
                outputs=got or ["no page"],
                depends=[c for c in calls if "." in c][:10],
                where=f"src/app.py:{node.lineno}"))
    return out


def nav_paths() -> set:
    """The paths the rail actually links to - the difference between a feature and a
    feature nobody can reach."""
    text = BASE_HTML.read_text(encoding="utf-8")
    return set(re.findall(r'\(\s*"[^"]+"\s*,\s*"(\?[^"]*|/[^"]*)"', text))


def linked_paths() -> set:
    """Every path some page points at, however the page points at it.

    A POST is not meant to live in the navigation, so counting only the rail would put forty
    working endpoints on the gap list and turn the backlog into noise. Neither does counting
    only href and action: the editor and the clip screen fetch their preview images from
    script, and a feature that redraws itself on every slider move is about as reachable as
    a feature gets. So this reads attributes and quoted url strings alike, and leaves prose
    out of it - a path someone merely mentioned in a paragraph is not a link.
    """
    out = set()
    for page in (SRC / "templates").glob("*.html"):
        text = page.read_text(encoding="utf-8")
        out |= set(re.findall(r'''[`"'](/(?:[A-Za-z0-9_+-]+)(?:/[A-Za-z0-9_+-]*)*)''', text))
    return out


def actions() -> list:
    """The things the agent can be asked to do, straight from its own registry."""
    from src.agent.tools import catalogue

    out = []
    for t in catalogue():
        out.append(Entry(
            key=f"action:{t['id']}", name=t["name"], kind="action",
            dept=department(t["dept"], t["id"], t["describe"]),
            describe=t["describe"] or "No description registered.",
            purpose=(f"Offered to the agent only once {', '.join(t['needs'])} is in hand."
                     if t["needs"] else
                     "Offered to the agent on any run; nothing has to be in hand first."),
            inputs=[f"{a} (argument)" for a in t["args"]],
            outputs=["an Outcome: did, advised or skipped, with what it touched"],
            depends=[f"needs {n}" for n in t["needs"]],
            where="src/agent/tools.py"))
    return out


def controls() -> list:
    """Every slider, switch and choice the edit rails expose, with the slots it writes."""
    from src.media.edit import RAILS, RAIL_TOOLS, TITLES

    out = []
    for rail in RAILS:
        for tool in RAIL_TOOLS.get(rail, []):
            fields = [f"{f.label} ({f.kind}{' ' + f.unit if f.unit else ''})"
                      for f in tool.fields]
            out.append(Entry(
                key=f"control:{tool.op}", name=tool.label, kind="control",
                dept=department("Editing", rail, tool.op),
                describe=tool.note or f"{TITLES.get(rail, rail)} rail: {tool.label}.",
                purpose=(f"The {rail} rail's {tool.op} step, set by {len(fields)} "
                         f"field{'s' if len(fields) != 1 else ''}."
                         + (" A painted position decides where it lands."
                            if tool.stroke else "")),
                inputs=fields + (["a painted position"] if tool.stroke else []),
                outputs=["a rewritten pixel buffer, recorded in the edit chain"],
                depends=[f"src.media.{rail}"],
                where=f"src/media/registry.py:{rail}"))
    return out


def modules() -> list:
    """Every python file in src with the header it was given."""
    out = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        rel = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            out.append(Entry(key=f"module:{rel}", name=path.name, kind="module",
                             dept="This machine", describe="Does not parse.",
                             purpose="Does not parse.", outputs=["nothing"], where=rel))
            continue
        doc = ast.get_docstring(tree) or ""
        dotted = rel[:-3].replace("/", ".")
        names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        out.append(Entry(
            key=f"module:{rel}", name=dotted, kind="module",
            dept=department(dotted, doc), describe=first_line(doc) or "No header.",
            purpose=first_line(doc) or "No header: nothing says what this file is for.",
            inputs=["imported by the app"], outputs=[f"{len(names)} top-level definitions"],
            depends=[f"defines {n}" for n in names[:8]], where=rel))
    return out


def test_bodies() -> dict:
    """Each test file's text, so a claim can be matched against the tests that name it."""
    out = {}
    for path in sorted(TESTS.rglob("*.py")):
        try:
            out[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return out


def prove(entry: Entry, bodies: dict) -> list:
    """Which test files name this thing. A route is proved by the path in quotes, a control
    by its op in quotes, a module by an import of it, an action by its id."""
    if entry.kind == "route":
        needle = '"' + entry.key.split(" ", 1)[1] + '"'
    elif entry.kind == "control":
        needle = '"' + entry.key.split(":", 1)[1] + '"'
    elif entry.kind == "action":
        needle = '"' + entry.key.split(":", 1)[1] + '"'
    else:
        needle = entry.key.split(":", 1)[1].rsplit("/", 1)[-1][:-3]
    return sorted(name for name, text in bodies.items() if needle in text)


def audit() -> list:
    """The whole registry, with proof and reach filled in."""
    bodies = test_bodies()
    rail, linked = nav_paths(), linked_paths()
    entries = routes() + actions() + controls() + modules()
    for e in entries:
        e.acceptance = prove(e, bodies)
        e.status = "proven" if e.acceptance else "unproven"
        if e.kind == "route":
            path = e.key.split(" ", 1)[1]
            e.reach = ("in the rail" if path in rail or path == "/" else
                       "linked from a page" if path in linked else
                       "nothing links to it")
            if e.reach != "nothing links to it" and e.status == "proven":
                e.status = "live"
        elif e.kind == "module":
            e.reach = "library"
        else:
            e.reach = "behind a route"
    return entries


def upgrades(entries: list) -> list:
    """The backlog is derived, not written. Every upgrade here is a gap the audit can see
    right now, and it closes the moment the audit stops seeing it."""
    out = []
    for e in entries:
        if e.status == "unproven" and e.kind in ("route", "control", "action"):
            what = {"route": "an endpoint", "control": "an edit control",
                    "action": "an agent action"}[e.kind]
            out.append(Entry(
                key=f"upgrade:prove-{slug(e.key)}", name=f"Prove {e.name}", kind="upgrade",
                dept=e.dept,
                describe=f"{what} {e.key.split(':', 1)[1]} runs but no test file names it, so "
                         "nothing says what it returns or that it fails honestly.",
                purpose=f"Give {what} a test so a later change cannot break it silently.",
                inputs=[e.key], outputs=["a passing test that names it"],
                acceptance=[f"a test whose text contains {e.key}"],
                status="open", where=e.where))
        if e.kind == "route" and e.reach == "nothing links to it":
            out.append(Entry(
                key=f"upgrade:reach-{slug(e.key)}", name=f"Put {e.key} in the rail",
                kind="upgrade", dept=e.dept,
                describe="The endpoint works and is tested but no page links to it and no "
                         "form posts to it, so she cannot find it without typing a url.",
                purpose="Make the feature reachable from the navigation.",
                inputs=[e.key], outputs=["a nav entry"],
                acceptance=["base.html links the path"], status="open", where=e.where))
        if e.kind == "module" and e.describe == "No header.":
            out.append(Entry(
                key=f"upgrade:document-{slug(e.key)}", name=f"Write the header for {e.name}",
                kind="upgrade", dept=e.dept,
                describe="The file has no module docstring, so neither the registry nor a new "
                         "reader can say what it is for.",
                purpose="One paragraph naming what the file owns and why it exists.",
                inputs=[e.key], outputs=["a module docstring"],
                acceptance=["ast.get_docstring returns text"], status="open", where=e.where))
    return out


def summary(entries: list, ups: list) -> dict:
    """Counts the audit is willing to say out loud."""
    by = lambda seq, f: {k: sum(1 for x in seq if f(x) == k) for k in
                         sorted({f(x) for x in seq})}
    return {
        "kinds": by(entries, lambda e: e.kind),
        "statuses": by(entries, lambda e: e.status),
        "depts": by(entries + ups, lambda e: e.dept),
        "features": len(entries),
        "upgrades": len(ups),
        "proven": sum(1 for e in entries if e.status in ("live", "proven")),
        # Floored, never rounded: 211 of 212 read as "100% of what this app can do has a test",
        # which is the one sentence on this page that must not be generous.
        "percent": sum(1 for e in entries if e.status in ("live", "proven")) * 100
        // max(1, len(entries)),
        "unproven": sum(1 for e in entries if e.status == "unproven"),
        "unreachable": sum(1 for e in entries if e.reach == "nothing links to it"),
    }
