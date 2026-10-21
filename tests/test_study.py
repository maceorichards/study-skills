"""Tests for src/study.py. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("study", REPO / "src" / "study.py")
study = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(study)

CONFIG = """# Study config: BIO101

## Content folders
| Folder | Role | Units |
|---|---|---|
| lectures | material | week01, week02 |
| psets | both | psets |
| exams/practice.md (this file only) | style-reference | — |

## Preferences
- Question formats: short answer
"""

TOPICS = """# Topics: BIO101

## Unit: week01 (lectures/week01/)

### week01-ph — pH and buffers
Sources: `lectures/week01/notes.md` §1; `lectures/week01/slides deck.pptx` slide 2
Concepts:
- pH is the negative log of hydrogen ion concentration
- A buffer resists pH change near its pKa

### week01-water — Properties of water
Sources: lectures/week01/notes.md §2
Concepts:
- Hydrogen bonding gives water a high heat capacity

## Unit: week02 (lectures/week02/)

### week02-enzyme-kinetics — Michaelis-Menten kinetics
Sources: lectures/week02/notes.md p.1 (intro); psets/pset1.tex Problem 2
Concepts:
- Km is the substrate concentration at half Vmax
- Competitive inhibition raises apparent Km
"""


def make_course(tmp: Path) -> Path:
    root = tmp / "BIO101"
    for rel, text in {
        "lectures/week01/notes.md": "# pH\n",
        "lectures/week02/notes.md": "# Enzymes\n",
        "psets/pset1.tex": "\\section{Problem 2}\n",
        "psets/pset1.pdf": "%PDF compiled from tex",
        "psets/build/pset1.aux": "aux",
        "psets/figures/plot.pdf": "%PDF figure",
        "psets/.hidden.md": "hidden",
        "exams/practice.md": "Q1. Why ...\n",
        "exams/other.md": "not configured",
        "lectures/week01/image.png": "png",
    }.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    with zipfile.ZipFile(root / "lectures/week01/slides deck.pptx", "w") as z:
        z.writestr("ppt/slides/slide10.xml", "<p:sld><a:p><a:t>Ten</a:t></a:p></p:sld>")
        z.writestr("ppt/slides/slide2.xml", "<p:sld><a:p><a:t>Two &amp; more</a:t></a:p></p:sld>")
    (root / "study").mkdir()
    (root / "study/config.md").write_text(CONFIG, encoding="utf-8")
    (root / "study/topics.md").write_text(TOPICS, encoding="utf-8")
    return root


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = study.main(["--root", str(root), *args])
    return code, out.getvalue(), err.getvalue()


class TierRules(unittest.TestCase):
    def rec(self, **kw):
        r = study.fresh_record()
        r.update(kw)
        return r

    def test_promote_at_three_points_with_partials(self):
        r = self.rec()
        for res in ("correct", "partial", "correct"):
            study.apply_result(r, 1, res, "c")
        self.assertEqual(r["tier"], 1)
        self.assertEqual(r["points"], 2.5)
        msg = study.apply_result(r, 1, "partial", "c")
        self.assertEqual((r["tier"], r["points"], r["consecutive_misses"]), (2, 0, 0))
        self.assertIn("promoted T1 → T2", msg)
        self.assertEqual(r["last_tier_change"]["from"], 1)

    def test_t3_promotes_to_mastered(self):
        r = self.rec(tier=3, points=2)
        study.apply_result(r, 3, "correct", "c")
        self.assertEqual(r["tier"], "mastered")

    def test_demote_after_two_consecutive_misses(self):
        r = self.rec(tier=2, points=1.5)
        study.apply_result(r, 2, "incorrect", "c")
        self.assertEqual(r["tier"], 2)
        study.apply_result(r, 2, "incorrect", "c")
        self.assertEqual((r["tier"], r["points"], r["consecutive_misses"]), (1, 0, 0))

    def test_partial_does_not_reset_misses_but_correct_does(self):
        r = self.rec(tier=2)
        study.apply_result(r, 2, "incorrect", "c")
        study.apply_result(r, 2, "partial", "c")
        self.assertEqual(r["consecutive_misses"], 1)
        study.apply_result(r, 2, "incorrect", "c")
        self.assertEqual(r["tier"], 1)
        r = self.rec(tier=2)
        study.apply_result(r, 2, "incorrect", "c")
        study.apply_result(r, 2, "correct", "c")
        study.apply_result(r, 2, "incorrect", "c")
        self.assertEqual(r["tier"], 2)

    def test_never_below_t1(self):
        r = self.rec()
        for _ in range(3):
            study.apply_result(r, 1, "incorrect", "c")
        self.assertEqual(r["tier"], 1)

    def test_mastered_miss_drops_to_t3_and_correct_changes_nothing(self):
        r = self.rec(tier="mastered")
        study.apply_result(r, 3, "correct", "c")
        self.assertEqual((r["tier"], r["points"]), ("mastered", 0))
        study.apply_result(r, 3, "incorrect", "c")
        self.assertEqual(r["tier"], 3)

    def test_forced_above_counts_at_current_tier_and_never_skips(self):
        r = self.rec(tier=1, points=2)
        study.apply_result(r, 3, "correct", "c", forced=True)
        self.assertEqual(r["tier"], 2)  # not 3: one tier at a time
        r = self.rec(tier=1, points=1)
        study.apply_result(r, 3, "incorrect", "c", forced=True)
        study.apply_result(r, 3, "incorrect", "c", forced=True)
        self.assertEqual((r["tier"], r["points"], r["consecutive_misses"]), (1, 1, 0))
        self.assertTrue(r["attempts"][-1]["forced"])

    def test_forced_below_is_logged_only(self):
        r = self.rec(tier=3, points=1, consecutive_misses=1)
        study.apply_result(r, 1, "incorrect", "c", forced=True)
        self.assertEqual((r["tier"], r["points"], r["consecutive_misses"]), (3, 1, 1))
        self.assertEqual(len(r["attempts"]), 1)

    def test_weak_concepts_added_on_miss_and_cleared_on_correct(self):
        r = self.rec()
        study.apply_result(r, 1, "partial", "Km meaning", source="mock-exam")
        self.assertEqual(r["weak_concepts"][0]["source"], "mock-exam")
        study.apply_result(r, 1, "incorrect", "km MEANING")
        self.assertEqual(len(r["weak_concepts"]), 1)
        study.apply_result(r, 1, "correct", "Km meaning ")
        self.assertEqual(r["weak_concepts"], [])

    def test_attempts_and_stems_are_capped(self):
        r = self.rec()
        for i in range(25):
            study.apply_result(r, 1, "incorrect", "c", stem=f"q{i}")
        self.assertEqual(len(r["attempts"]), study.MAX_ATTEMPTS)
        self.assertEqual(r["recent_stems"], [f"q{i}" for i in range(17, 25)])

    def test_bad_input_rejected(self):
        with self.assertRaises(study.StudyError):
            study.apply_result(self.rec(), 1, "maybe", "c")
        with self.assertRaises(study.StudyError):
            study.parse_tier("4")
        self.assertEqual(study.parse_tier("hard"), 3)
        self.assertEqual(study.parse_tier("T2"), 2)


class Buckets(unittest.TestCase):
    today = dt.date(2026, 10, 21)

    def b(self, **kw):
        r = study.fresh_record()
        r.update(kw)
        return study.bucket(r, today=self.today)[0]

    def test_buckets(self):
        miss = [{"date": "2026-10-20 10:00", "tier": 1, "result": "incorrect", "concept": "c", "source": "quiz"}]
        ok = [{"date": "2026-10-20 10:00", "tier": 1, "result": "correct", "concept": "c", "source": "quiz"}]
        self.assertEqual(self.b(attempts=miss, last_quizzed="2026-10-20 10:00"), 1)
        self.assertEqual(self.b(attempts=ok, last_quizzed="2026-10-20 10:00",
                                last_tier_change={"date": "2026-10-18 09:00", "from": 2, "to": 1}), 1)
        self.assertEqual(self.b(attempts=ok, last_quizzed="2026-10-20 10:00",
                                last_tier_change={"date": "2026-10-01 09:00", "from": 2, "to": 1}), 3)
        self.assertEqual(self.b(weak_concepts=[{"concept": "c", "added": "2026-10-20", "source": "teach"}]), 2)
        self.assertEqual(self.b(last_quizzed="2026-10-20 10:00", attempts=ok,
                                weak_concepts=[{"concept": "c", "added": "2026-10-20 11:00", "source": "teach"}]), 2)
        self.assertEqual(self.b(last_quizzed="2026-10-20 10:00", attempts=ok,
                                weak_concepts=[{"concept": "c", "added": "2026-10-19 11:00", "source": "teach"}]), 3)
        self.assertEqual(self.b(), 4)
        self.assertEqual(self.b(tier="mastered", last_quizzed="2026-10-01 10:00", attempts=ok), 5)
        self.assertIsNone(self.b(tier="mastered", last_quizzed="2026-10-15 10:00", attempts=ok))
        r = study.fresh_record()
        r.update(tier="mastered", last_quizzed="2026-10-15 10:00", attempts=ok)
        self.assertEqual(study.bucket(r, all_mastered=True, today=self.today)[0], 5)


class CourseFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = make_course(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_parse_topics_and_sources(self):
        topics, _ = study.parse_topics(TOPICS)
        self.assertEqual([t.id for t in topics], ["week01-ph", "week01-water", "week02-enzyme-kinetics"])
        self.assertEqual(topics[0].sources[1], ("lectures/week01/slides deck.pptx", "slide 2"))
        self.assertEqual([s for s, _ in topics[2].sources], ["lectures/week02/notes.md", "psets/pset1.tex"])
        self.assertEqual(len(topics[2].concepts), 2)
        self.assertEqual(topics[2].unit, "week02")

    def test_parse_config_strips_notes(self):
        folders = study.parse_config(CONFIG)
        self.assertEqual(folders[2], {"folder": "exams/practice.md", "role": "style-reference", "units": []})
        self.assertEqual(folders[0]["units"], ["week01", "week02"])

    def test_scan_exclusions(self):
        files = [p for p, _ in study.scan(self.root, "psets")]
        self.assertEqual(files, ["psets/pset1.tex"])  # compiled pdf, build/, figures/, hidden skipped
        files = [p for p, _ in study.scan(self.root, "lectures")]
        self.assertEqual(files, ["lectures/week01/notes.md", "lectures/week01/slides deck.pptx",
                                 "lectures/week02/notes.md"])

    def test_extract_pptx_orders_slides_numerically(self):
        text = study.extract(self.root / "lectures/week01/slides deck.pptx")
        self.assertLess(text.index("Two & more"), text.index("Ten"))
        self.assertIn("--- slide 1 ---", text)

    def test_extract_docx_and_ipynb(self):
        docx = self.root / "a.docx"
        with zipfile.ZipFile(docx, "w") as z:
            z.writestr("word/document.xml", "<w:document><w:p><w:r><w:t>Hello</w:t></w:r></w:p>"
                                            "<w:p><w:r><w:t>World</w:t></w:r></w:p></w:document>")
        self.assertEqual(study.extract(docx).split(), ["Hello", "World"])
        nb = self.root / "n.ipynb"
        nb.write_text(json.dumps({"cells": [
            {"cell_type": "markdown", "source": ["# Title"]},
            {"cell_type": "code", "source": "x = 1", "outputs": [{"text": ["1\n"]}]}]}), encoding="utf-8")
        text = study.extract(nb)
        self.assertIn("# Title", text)
        self.assertIn("[output]\n1", text)
        with self.assertRaises(study.StudyError):
            study.extract(self.root / "lectures/week01/image.png")

    def test_manifest_write_then_diff(self):
        code, out, _ = run(self.root, "manifest", "--write")
        self.assertEqual(code, 0, out)
        course = study.Course(self.root)
        self.assertEqual(course.manifest["exams/practice.md"][1], "(style)")
        self.assertEqual(course.manifest["lectures/week02/notes.md"][1], "week02")
        self.assertNotIn("exams/other.md", course.manifest)
        self.assertEqual(study.diff_manifest(course), {"new": [], "modified": [], "deleted": []})
        (self.root / "lectures/week02/extra.md").write_text("new", encoding="utf-8")
        (self.root / "lectures/week01/notes.md").unlink()
        d = study.diff_manifest(study.Course(self.root))
        self.assertEqual(d["new"], ["lectures/week02/extra.md"])
        self.assertEqual(d["deleted"], ["lectures/week01/notes.md"])
        # rewriting keeps the topics and replaces the old table
        run(self.root, "manifest", "--write")
        text = (self.root / "study/topics.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("## Manifest"), 1)
        self.assertIn("### week02-enzyme-kinetics", text)

    def test_init_progress_is_idempotent_and_keeps_progress(self):
        self.assertEqual(run(self.root, "init-progress")[0], 0)
        run(self.root, "record", "--topic", "week01-ph", "--tier", "1", "--result", "correct", "--concept", "c")
        code, out, _ = run(self.root, "init-progress")
        self.assertIn("added 0", out)
        data = json.loads((self.root / "study/progress.json").read_text(encoding="utf-8"))
        self.assertEqual(data["topics"]["week01-ph"]["points"], 1)
        lines = (self.root / "study/progress.json").read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines[3].startswith('"week01-ph": {'))  # one topic per line

    def test_record_add_weak_mark_taught(self):
        run(self.root, "init-progress")
        code, out, _ = run(self.root, "record", "--topic", "week01-ph", "--tier", "easy",
                           "--result", "partial", "--concept", "buffers", "--stem", " ".join(["w"] * 30))
        self.assertEqual(code, 0)
        self.assertIn("points 0 → 0.5 of 3", out)
        run(self.root, "add-weak", "--topic", "week01-water", "--concept", "heat capacity")
        run(self.root, "mark-taught", "--topic", "week01-water")
        recs = study.load_progress(self.root)["topics"]
        self.assertEqual(len(recs["week01-ph"]["recent_stems"][0].split()), 15)
        self.assertEqual(recs["week01-water"]["weak_concepts"][0]["source"], "teach")
        self.assertIsNotNone(recs["week01-water"]["taught"])
        code, _, err = run(self.root, "record", "--topic", "nope", "--tier", "1", "--result", "correct", "--concept", "c")
        self.assertEqual(code, 1)
        self.assertIn("unknown topic ID", err)

    def test_scope_resolution(self):
        run(self.root, "init-progress")
        course = study.Course(self.root)
        ids = lambda toks: [t.id for t in study.resolve_scope(course, toks)[0]]  # noqa: E731
        self.assertEqual(ids(["lectures/week01"]), ["week01-ph", "week01-water"])
        self.assertEqual(ids(["week01"]), ["week01-ph", "week01-water"])  # inside a content folder
        self.assertEqual(ids(["psets"]), ["week02-enzyme-kinetics"])
        self.assertEqual(ids(["week01-water"]), ["week01-water"])
        self.assertEqual(ids(["competitive inhibition"]), ["week02-enzyme-kinetics"])
        self.assertEqual(len(ids([])), 3)
        with self.assertRaises(study.StudyError):
            ids(["photosynthesis"])
        (self.root / "lectures/week02/new.md").write_text("x", encoding="utf-8")
        run(self.root, "manifest", "--write")
        (self.root / "lectures/week02/newer.md").write_text("x", encoding="utf-8")
        _, notes = study.resolve_scope(study.Course(self.root), ["lectures/week02"])
        self.assertTrue(any("aren't indexed" in n and "newer.md" in n for n in notes))

    def test_priority_order(self):
        run(self.root, "init-progress")
        run(self.root, "record", "--topic", "week02-enzyme-kinetics", "--tier", "1", "--result", "incorrect", "--concept", "Km")
        run(self.root, "add-weak", "--topic", "week01-water", "--concept", "heat capacity")
        code, out, _ = run(self.root, "priority", "--json")
        ranked = json.loads(out)
        self.assertEqual([r["id"] for r in ranked], ["week02-enzyme-kinetics", "week01-water", "week01-ph"])
        self.assertEqual([r["bucket"] for r in ranked], [1, 2, 4])

    def test_status_and_validate(self):
        run(self.root, "manifest", "--write")
        self.assertEqual(run(self.root, "validate")[0], 1)  # no progress yet
        run(self.root, "init-progress")
        code, out, _ = run(self.root, "validate")
        self.assertEqual((code, out.strip()), (0, "ok"))
        code, out, _ = run(self.root, "status")
        self.assertEqual(code, 0)
        self.assertIn("BIO101: 3 topic(s) in scope", out)
        self.assertIn("Next up for quiz-me", out)
        self.assertNotIn("Unindexed", out)

    def test_not_set_up(self):
        shutil.rmtree(self.root / "study")
        code, _, err = run(self.root, "status")
        self.assertEqual(code, 1)
        self.assertIn("isn't set up", err)

    def test_survey(self):
        rows = {r["name"]: r for r in study.survey(self.root)}
        self.assertNotIn("study", rows)
        self.assertEqual(rows["lectures"]["readable"], {".md": 2, ".pptx": 1})
        self.assertEqual(rows["lectures"]["other"], 1)


@unittest.skipUnless(os.environ.get("STUDY_TEST_PDF"), "set STUDY_TEST_PDF to a PDF path to test PDF extraction")
class Pdf(unittest.TestCase):
    def test_pdf_pages(self):
        text = study.extract(Path(os.environ["STUDY_TEST_PDF"]), "1")
        self.assertTrue(text.startswith("[pdf: "))
        self.assertIn("--- page 1 ---", text)


if __name__ == "__main__":
    unittest.main()
