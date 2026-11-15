"""Reading her own captions out of the files she already has, and proving the parser invents none.

The register is starved of exactly one input: sentences she wrote. Every platform will hand her those
sentences in an archive, but nobody publishes the file layout of that archive (see the spec), so what
is proved here is the shape of the promise rather than a schema:

* a caption is found wherever it sits and **named by where it sat** - the page quotes her own key
  path, so a different layout shows up as a different path instead of a silent zero;
* the words of other people are never her voice: a key that looks like a conversation is left alone
  and counted, because a reply somebody else wrote would teach the generator to sound like a stranger;
* a line has to be a line: hashtags only, emoji only, links only and three-word fragments are
  dropped with the reason attached, not quietly skipped;
* a five-line caption is five samples, because casing, terminal punctuation, question rate and emoji
  are all counted per sample;
* the ceilings are reported (`truncated`), never hidden behind a list that looks complete;
* nothing that comes back was not in the file, and an unreadable or empty archive changes nothing.
"""

import csv
import io
import json
import zipfile

from src.captions import harvest

MINE = "wore the tank again and i'm not even sorry"
OTHERS = "omg where is that from??"


def zbytes(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return buf.getvalue()


# ---------------------------------------------------------------- finding, and naming where

def test_a_caption_is_found_wherever_it_sits_and_named_by_that_path():
    blob = json.dumps({"data": {"posts": [{"mediaList": [{"description": MINE}]}]}})
    got = harvest.read(blob, name="anything.json")
    assert got.lines == [MINE]
    assert "description" in got.samples[0]["from"]
    assert "mediaList" in got.samples[0]["from"], "the page must be able to say where it read from"


def test_the_key_name_is_read_case_insensitively():
    got = harvest.read(json.dumps({"Caption": MINE}), name="x.json")
    assert got.lines == [MINE]


def test_a_list_of_strings_under_a_caption_key_is_read_as_lines():
    got = harvest.read(json.dumps({"captions": [MINE, "wait why is the lighting like this"]}),
                       name="x.json")
    assert len(got.lines) == 2


def test_a_csv_column_named_for_the_caption_is_read():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Timestamp", "Caption", "Views"])
    writer.writerow(["2026-11-01", MINE, "1200"])
    writer.writerow(["2026-11-02", "  ", "900"])
    got = harvest.read(buf.getvalue(), name="posts.csv")
    assert got.lines == [MINE]


def test_plain_text_is_read_the_way_the_paste_box_reads_it():
    got = harvest.read(f"{MINE}\n\nwait why is the lighting like this\n\n", name="notes.txt")
    assert got.lines == [MINE, "wait why is the lighting like this"]


# ---------------------------------------------------------------- not her voice

def test_other_peoples_words_are_left_alone_and_counted():
    blob = json.dumps({"comments_1.json": [{"text": OTHERS}], "caption": MINE})
    got = harvest.read(blob, name="x.json")
    assert got.lines == [MINE], "a stranger's reply is not a sample of her voice"
    assert any("comment" in path.lower() for path in got.blocked), got.blocked


def test_a_title_that_is_a_product_page_is_still_hers_if_it_is_under_the_key():
    # "title" is a candidate because some exports file the caption there; the parser does not judge
    # the content's genre, only whether the sentence can measure a register.
    got = harvest.read(json.dumps({"title": MINE}), name="x.json")
    assert got.lines == [MINE]


# ---------------------------------------------------------------- a line has to be a line

def test_hashtags_only_and_emoji_only_and_links_only_are_dropped_with_the_reason():
    blob = json.dumps([{"description": "#fyp #foryou #viral"},
                       {"description": "🔥🔥😭"},
                       {"description": "https://short.example/a1b2"},
                       {"description": "ok"},
                       {"description": MINE}])
    got = harvest.read(blob, name="x.json")
    assert got.lines == [MINE]
    reasons = " | ".join(d["why"] for d in got.dropped)
    assert "hashtag" in reasons and "emoji" in reasons and "link" in reasons
    assert "too short" in reasons


# ---------------------------------------------------------------- one caption, many samples

def test_a_long_caption_is_counted_as_the_lines_it_actually_is():
    text = "the tank again\nnobody asked for this but ok\ni own three of them"
    got = harvest.read(json.dumps({"description": text}), name="x.json")
    assert got.lines == ["the tank again", "nobody asked for this but ok", "i own three of them"]
    assert len({s["from"] for s in got.samples}) == 1, "same file, same key, three samples"


# ---------------------------------------------------------------- the archive

def test_a_zip_is_read_member_by_member_and_says_which_members_it_read():
    blob = zbytes({"instagram/captions_1.json": json.dumps([{"description": MINE}]),
                   "instagram/profile.json": json.dumps({"name": "leah"}),
                   "media/2026/pic.jpg": "not text"})
    got = harvest.read(blob, name="export.zip")
    assert got.lines == [MINE]
    assert any(member.endswith("captions_1.json") for member in got.files)
    assert not any(member.endswith(".jpg") for member in got.files), "it does not parse what it cannot read"


def test_the_sample_ceiling_is_reported_rather_than_hidden():
    many = json.dumps([{"description": f"{MINE} number {i}"} for i in range(harvest.MAX_SAMPLES + 40)])
    got = harvest.read(many, name="big.json")
    assert len(got.lines) == harvest.MAX_SAMPLES
    assert got.truncated is True


def test_a_file_over_the_byte_cap_is_refused_not_half_read():
    big = json.dumps({"description": "x" * (harvest.MAX_BYTES + 10)})
    got = harvest.read(big, name="huge.json")
    assert got.samples == []
    assert "too big" in got.error.lower()


def test_an_archive_with_no_caption_under_any_key_says_what_it_looked_for():
    got = harvest.read(json.dumps({"following_and_followers": [{"user": "x"}]}), name="x.json")
    assert got.samples == []
    assert "caption" in got.error and "description" in got.error


def test_nothing_in_the_report_is_a_string_that_was_not_in_the_file():
    blob = json.dumps({"posts": [{"caption": MINE}, {"caption": "idc, post it anyway"}]})
    got = harvest.read(blob, name="x.json")
    raw = blob
    for line in got.lines:
        assert line in raw, f"{line!r} was never in her file"


def test_an_empty_file_changes_nothing_and_says_so():
    for payload, name in (("", "x.txt"), ("[]", "x.json"), (zbytes({}), "empty.zip")):
        got = harvest.read(payload, name=name)
        assert got.samples == [] and got.error, name


def test_provenance_names_the_file_and_the_line_count():
    got = harvest.read(json.dumps([{"description": MINE}, {"description": "idc, post it anyway"}]),
                       name="captions.json")
    said = got.provenance()
    assert "2" in said and "captions.json" in said
