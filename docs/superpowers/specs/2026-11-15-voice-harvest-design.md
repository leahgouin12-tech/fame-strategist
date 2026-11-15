# Voice harvest: reading her own captions out of the files she already has

**Date:** 2026-11-15 · **Status:** built
**Module:** `src/captions/harvest.py` · **Route:** `POST /write/harvest` · **Page:** `/write`

## The problem this is the fix for

`src/db.py` holds her voice samples in one table, and on 2026-11-15 that table had **zero rows**
(`SELECT COUNT(*) FROM voice` → 0, `caption` prefs both false). Everything downstream of it is
therefore honest but useless to her: `captions.register.of(profile, [])` returns
`learned=False`, `source="the app's default, because nothing is pasted"`, and every caption card
prints "Voice unlearned". That is the exact state behind her standing complaint — *"the ones i seen
so far id never ever use em"* — and the reason is not a bad generator. The generator has no
measurement to work from.

The only way to change it is to hand the register real sentences she wrote. Asking her to retype ten
old captions into a textarea is a chore she has already implicitly refused by never doing it, and the
data is not scarce: every platform she posts on will hand her every caption she ever wrote, free, in
an official archive.

## What is verified, and what is not

* **Verified in this repository:** the ingest paths that already exist. `metrics/ingest.py` reads a
  CSV of *numbers* (REQUIRED = post_ref, views, avg_watch_pct, follows_gained); `metrics/churn.py`
  reads follower lists out of a JSON blob by walking the structure and accepting a name from any of a
  list of candidate keys (`NAME_KEYS`) rather than assuming one path. Nothing in the codebase has ever
  read a caption out of anything except pasted text.
* **Verified by attempt, 2026-11-15:** Meta and TikTok document *how to request* the archive, and do
  **not** publish the file layout of the result. Two attempts to read a schema from the web failed —
  one search returned nothing relevant, one help page returned a stylesheet instead of prose. There is
  no quotable list of key names to copy.
* **Therefore not assumed, by design:** this parser does not hard-code `captions_1.json` or any other
  filename, and does not assume a nesting shape. It walks whatever the file actually contains, collects
  every string sitting under a caption-shaped key, and **tells her which key path each line came from**.
  If her archive is shaped differently than anybody's blog post claims, the page shows the paths it
  found in *her* file. A parser that guessed the schema would either silently return nothing or invent
  a structure; reporting the path it really read is the honest version of the same feature.
* **Still open, and stated on the page:** whether an archive she requests contains the captions of
  posts she has since deleted, or whether a platform that has since re-edited a caption gives the old
  or the new text. The parser cannot know and does not claim to — she sees the line and keeps or drops
  it, so the confirmation is hers.

## Rules

1. **Sources it accepts** (all read locally, nothing uploaded, no model call):
   a `.zip` (the archive as platforms deliver it), a `.json` export file, a `.csv`, or plain text.
2. **Candidate keys**, matched case-insensitively and by substring where unambiguous:
   `caption`, `description`, `title`, `text`, `content`, `share_text`, `post_text`, `body`.
   Comments, replies and other people's names are not caption keys and are not harvested — the lists
   she is confirming are her own writing.
3. **A line earns its place** only if, after unescaping, it has at least `MIN_WORDS` = 2 words and
   `MIN_CHARS` = 8 characters, and is not made only of hashtags, only of emoji/punctuation, or only of
   a link. Everything rejected is returned in `dropped` with the reason, so "it found 3 of 200" is
   legible rather than mysterious.
4. **Multi-line captions split into lines**, because the register counts per sample — casing,
   terminal punctuation, question rate, emoji per sample — and one five-line caption counted as a
   single sample would flatten all four numbers.
5. **Caps, because her machine has 3.66 GB of RAM:** `MAX_BYTES` per file, `MAX_MEMBERS` per archive,
   and a `MAX_SAMPLES` ceiling on what is kept. A big archive is read until the ceiling, and the page
   says how much of it was read instead of pretending it read everything.
6. **Provenance is stored, not inferred:** the kept lines go to `db.save_voice(...)` exactly as the
   paste box does, and one summary row goes to `db.remember("voice-source", ...)`. `captions` reads
   that note so a card can say where the measurement came from. Deleting the samples deletes the note.
7. **Nothing is invented.** An archive with no usable caption under any candidate key returns
   `error` text naming the keys it looked for, and the app keeps its old voice state rather than
   falling back to invented lines.

## Out of scope

No auto-posting, no follow/DM/poll of any account (the guardrail verbs), no upload, no model call, no
public hosting. The harvest only fills the same table the paste box fills.
