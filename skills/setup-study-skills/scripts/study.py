#!/usr/bin/env python3
"""Helper for the study skills (setup-study-skills, teach-me, quiz-me, study-status, mock-exam).

Standard library only, Python 3.9+, macOS / Linux / Windows. Run it from the course root;
study data lives in ./study/. The canonical copy is src/study.py in the study-skills repo;
skills/*/scripts/study.py are generated copies (python tools/sync.py), so edit src/study.py only.

Commands (run with -h for options):
  now                         current local date and time
  extract FILE...             print text of .md .txt .tex .py .ipynb .docx .pptx .pdf files
  survey                      top-level folders of the course with readable-file counts
  scan FOLDER...              readable files under folders, with modification times
  manifest [--write]          manifest table for the configured content folders
  diff-manifest               files new, modified or deleted since the manifest
  init-progress               add fresh progress records for topics that lack one
  topics [SCOPE...]           topics in scope, in course order
  priority [SCOPE...]         topics ranked by where the user needs the most help
  record ...                  apply one graded answer to progress (tier rules)
  add-weak ...                add a weak concept to a topic
  mark-taught ...             mark a topic as taught
  status [SCOPE...]           progress dashboard
  validate                    check topics.md and progress.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

STUDY_DIR = "study"
READABLE = {".md", ".txt", ".tex", ".py", ".m", ".r", ".jl", ".ipynb", ".pdf", ".docx", ".pptx"}
SKIP_DIRS = {"build", "node_modules", "__pycache__", "venv", "env", "site-packages",
             "figures", "scans", "img", "images"}
TIER_NAMES = {"1": 1, "2": 2, "3": 3, "easy": 1, "medium": 2, "hard": 3}
RESULTS = ("correct", "partial", "incorrect")
MAX_ATTEMPTS = 20
MAX_STEMS = 8
REVIEW_DAYS = 14
DEMOTION_DAYS = 7
BUCKET_NAMES = {1: "struggling", 2: "flagged in teaching", 3: "in progress", 4: "new", 5: "review"}


class StudyError(Exception):
    pass


# ---------------------------------------------------------------- basics

def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def days_since(stamp: str, today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return (today - dt.date.fromisoformat(stamp[:10])).days


def norm_path(p: str) -> str:
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def slug(name: str) -> str:
    return re.sub(r"\s+", "-", name.strip().lower())


def mtime(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def tier_num(t) -> int:
    return 4 if t == "mastered" else int(t)


def tier_label(t) -> str:
    return "M" if t == "mastered" else f"T{t}"


def clean_number(x):
    return int(x) if float(x).is_integer() else x


def study_path(root: Path, name: str) -> Path:
    return root / STUDY_DIR / name


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------- extraction

def _xml_text(xml: str, para_tag: str) -> str:
    xml = xml.replace(f"</{para_tag}>", "\n").replace("<w:tab/>", "\t").replace("<a:br/>", "\n")
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return _xml_text(z.read("word/document.xml").decode("utf-8", "replace"), "w:p")


def extract_pptx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        slides = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        slides.sort(key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        parts = []
        for i, name in enumerate(slides, 1):
            parts.append(f"--- slide {i} ---\n" + _xml_text(z.read(name).decode("utf-8", "replace"), "a:p").strip())
        return "\n\n".join(parts)


def extract_ipynb(path: Path) -> str:
    nb = json.loads(path.read_text(encoding="utf-8"))
    parts = []
    for i, cell in enumerate(nb.get("cells", []), 1):
        src = cell.get("source", "")
        src = "".join(src) if isinstance(src, list) else src
        parts.append(f"--- cell {i} [{cell.get('cell_type', '?')}] ---\n{src.rstrip()}")
        for out in cell.get("outputs", []):
            text = out.get("text") or out.get("data", {}).get("text/plain")
            if text:
                text = "".join(text) if isinstance(text, list) else text
                if len(text) > 2000:
                    text = text[:2000] + "\n[output truncated]"
                parts.append(f"[output]\n{text.rstrip()}")
    return "\n\n".join(parts)


_JXA_PDF = (
    'function run(argv){ObjC.import("PDFKit");'
    'var d=$.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));'
    'if(d.isNil()){return "";}var out=[];'
    'for(var i=0;i<d.pageCount;i++){var s=d.pageAtIndex(i).string;out.push(s.isNil()?"":s.js);}'
    'return out.join("\\f");}'
)


def pdf_pages(path: Path) -> list[str]:
    """Text of each page, trying pypdf, pdfminer, pdftotext, then macOS PDFKit."""
    tried = []
    try:
        import pypdf  # type: ignore
        return [p.extract_text() or "" for p in pypdf.PdfReader(str(path)).pages]
    except ImportError:
        tried.append("pypdf (not installed)")
    except Exception as e:  # noqa: BLE001
        tried.append(f"pypdf ({e})")
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        return extract_text(str(path)).split("\f")
    except ImportError:
        tried.append("pdfminer (not installed)")
    except Exception as e:  # noqa: BLE001
        tried.append(f"pdfminer ({e})")
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", "replace").split("\f")
        tried.append("pdftotext (failed)")
    else:
        tried.append("pdftotext (not installed)")
    if sys.platform == "darwin" and shutil.which("osascript"):
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", _JXA_PDF, str(path)], capture_output=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.decode("utf-8", "replace").rstrip("\n").split("\f")
        tried.append("macOS PDFKit (failed)")
    raise StudyError(
        f"could not extract text from {path}; tried: {', '.join(tried)}. "
        "Install pypdf with `python -m pip install pypdf` (or read the PDF with your own file tool)."
    )


def parse_range(spec: str, n: int) -> range:
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", spec.strip())
    if not m:
        raise StudyError(f"bad page range {spec!r}; use e.g. 1-20")
    a = int(m.group(1))
    b = int(m.group(2) or a)
    return range(max(a, 1), min(b, n) + 1)


def extract(path: Path, pages: str | None = None) -> str:
    ext = path.suffix.lower()
    if not path.is_file():
        raise StudyError(f"no such file: {path}")
    if ext == ".pdf":
        texts = pdf_pages(path)
        rng = parse_range(pages, len(texts)) if pages else range(1, len(texts) + 1)
        head = f"[pdf: {len(texts)} pages; showing {rng.start}-{rng.stop - 1}]" if len(texts) else "[pdf: 0 pages]"
        body = "\n\n".join(f"--- page {i} ---\n{texts[i - 1].strip()}" for i in rng)
        return head + "\n" + body
    if ext == ".docx":
        return extract_docx(path)
    if ext == ".pptx":
        return extract_pptx(path)
    if ext == ".ipynb":
        return extract_ipynb(path)
    if ext in READABLE:
        return path.read_text(encoding="utf-8", errors="replace")
    raise StudyError(f"unsupported file type: {path.name} (readable: {' '.join(sorted(READABLE))})")


# ---------------------------------------------------------------- scanning

def _skipped_dir(name: str) -> bool:
    return name.startswith(".") or name.lower() in SKIP_DIRS


def scan(root: Path, folder: str) -> list[tuple[str, str]]:
    """Readable files under folder (relative to root) as (posix path, mtime), sorted."""
    base = root / folder
    if base.is_file():
        files = [base] if base.suffix.lower() in READABLE else []
    elif base.is_dir():
        files = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not _skipped_dir(d))
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                if not fn.startswith(".") and p.suffix.lower() in READABLE:
                    files.append(p)
    else:
        raise StudyError(f"no such file or folder: {folder}")
    tex_stems = {p.stem for p in files if p.suffix.lower() == ".tex"}
    files = [p for p in files if not (p.suffix.lower() == ".pdf" and p.stem in tex_stems)]
    return [(p.relative_to(root).as_posix(), mtime(p)) for p in files]


def survey(root: Path) -> list[dict]:
    rows = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith(".") or child.name == STUDY_DIR:
            continue
        if child.is_dir():
            counts: dict[str, int] = {}
            other = 0
            for dirpath, dirnames, filenames in os.walk(child):
                dirnames[:] = [d for d in dirnames if not _skipped_dir(d)]
                for fn in filenames:
                    if fn.startswith("."):
                        continue
                    ext = Path(fn).suffix.lower()
                    if ext in READABLE:
                        counts[ext] = counts.get(ext, 0) + 1
                    else:
                        other += 1
            rows.append({"name": child.name, "kind": "folder", "readable": counts, "other": other})
        elif child.suffix.lower() in READABLE:
            rows.append({"name": child.name, "kind": "file", "readable": {child.suffix.lower(): 1}, "other": 0})
    return rows


# ---------------------------------------------------------------- parsing study files

class Topic:
    def __init__(self, tid: str, title: str, unit: str, order: int):
        self.id = tid
        self.title = title
        self.unit = unit
        self.order = order
        self.sources: list[tuple[str, str]] = []
        self.concepts: list[str] = []

    def text(self) -> str:
        return " ".join([self.id, self.title, *self.concepts]).lower()


_SRC_EXT = r"(?:md|txt|tex|py|m|r|jl|ipynb|pdf|docx|pptx)"


def parse_sources(s: str) -> list[tuple[str, str]]:
    out = []
    if "`" in s:
        for m in re.finditer(r"`([^`]+)`\s*([^;`]*)", s):
            out.append((norm_path(m.group(1)), m.group(2).strip()))
        return out
    for piece in s.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        m = re.match(rf"(.+?\.{_SRC_EXT})(?=\s|$)(.*)", piece, re.I)
        if m:
            out.append((norm_path(m.group(1)), m.group(2).strip()))
        else:
            out.append((norm_path(piece), ""))
    return out


def _table_rows(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows[1:] if rows else rows  # drop header


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            current = m.group(1)
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def parse_topics(text: str) -> tuple[list[Topic], dict[str, tuple[str, str]]]:
    topics: list[Topic] = []
    manifest: dict[str, tuple[str, str]] = {}
    unit = ""
    in_manifest = False
    in_concepts = False
    manifest_lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^##\s+Manifest\b", line):
            in_manifest, in_concepts = True, False
            continue
        m = re.match(r"^##\s+Unit:\s*(.+?)(?:\s+\(.*\))?\s*$", line)
        if m:
            unit, in_manifest, in_concepts = m.group(1).strip(), False, False
            continue
        if re.match(r"^##\s", line):
            in_manifest = in_concepts = False
            continue
        if in_manifest:
            manifest_lines.append(line)
            continue
        m = re.match(r"^###\s+(\S+)\s+(?:—|–|-{1,2})\s+(.+?)\s*$", line)
        if m:
            topics.append(Topic(m.group(1), m.group(2), unit, len(topics)))
            in_concepts = False
            continue
        if not topics:
            continue
        m = re.match(r"^Sources:\s*(.*)$", line)
        if m:
            topics[-1].sources = parse_sources(m.group(1))
            in_concepts = False
            continue
        if re.match(r"^Concepts:\s*$", line):
            in_concepts = True
            continue
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if in_concepts and m:
            topics[-1].concepts.append(m.group(1))
    for row in _table_rows(manifest_lines):
        if len(row) >= 3:
            manifest[norm_path(row[0].strip("`"))] = (row[1], row[2])
    return topics, manifest


def parse_config(text: str) -> list[dict]:
    rows = _table_rows(_sections(text).get("Content folders", []))
    folders = []
    for row in rows:
        if len(row) < 2:
            continue
        units = [] if len(row) < 3 or row[2] in ("", "—", "-") else [u.strip() for u in row[2].split(",") if u.strip()]
        folder = re.sub(r"\s+\([^)]*\)\s*$", "", row[0]).strip().strip("`")  # drop notes like "(this file only)"
        folders.append({"folder": norm_path(folder), "role": row[1].strip().lower(), "units": units})
    return folders


class Course:
    def __init__(self, root: Path):
        self.root = root
        cfg = study_path(root, "config.md")
        if not cfg.exists():
            raise StudyError("this course isn't set up (no study/config.md); run the setup-study-skills skill first")
        self.folders = parse_config(cfg.read_text(encoding="utf-8"))
        tp = study_path(root, "topics.md")
        self.topics, self.manifest = parse_topics(tp.read_text(encoding="utf-8")) if tp.exists() else ([], {})
        self.by_id = {t.id: t for t in self.topics}
        self.progress = load_progress(root)

    def record(self, tid: str) -> dict:
        recs = self.progress["topics"]
        if tid not in recs:
            recs[tid] = fresh_record()
        return recs[tid]

    def save(self) -> None:
        save_progress(self.root, self.progress)


# ---------------------------------------------------------------- progress file

def fresh_record() -> dict:
    return {"tier": 1, "points": 0, "consecutive_misses": 0, "last_tier_change": None,
            "last_quizzed": None, "taught": None, "weak_concepts": [], "recent_stems": [], "attempts": []}


def load_progress(root: Path) -> dict:
    p = study_path(root, "progress.json")
    if not p.exists():
        return {"version": 1, "topics": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise StudyError(f"study/progress.json is not valid JSON: {e}") from e
    data.setdefault("version", 1)
    data.setdefault("topics", {})
    for rec in data["topics"].values():
        for k, v in fresh_record().items():
            rec.setdefault(k, v)
    return data


def dump_progress(data: dict) -> str:
    items = list(data["topics"].items())
    lines = ["{", f'"version": {data.get("version", 1)},', '"topics": {']
    for i, (tid, rec) in enumerate(items):
        lines.append(json.dumps(tid) + ": " + json.dumps(rec, ensure_ascii=False) + ("," if i < len(items) - 1 else ""))
    lines += ["}", "}"]
    return "\n".join(lines) + "\n"


def save_progress(root: Path, data: dict) -> None:
    atomic_write(study_path(root, "progress.json"), dump_progress(data))


def _same(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def add_weak(rec: dict, concept: str, source: str, when: str) -> bool:
    if any(_same(w["concept"], concept) for w in rec["weak_concepts"]):
        return False
    rec["weak_concepts"].append({"concept": concept, "added": when, "source": source})
    return True


def apply_result(rec: dict, q: int, result: str, concept: str, *, stem: str = "", source: str = "quiz",
                 forced: bool = False, when: str | None = None) -> str:
    """Apply one graded answer at question tier q. Returns a one-line summary."""
    if result not in RESULTS:
        raise StudyError(f"result must be one of {', '.join(RESULTS)}")
    if q not in (1, 2, 3):
        raise StudyError("question tier must be 1, 2 or 3")
    when = when or now()
    old = rec["tier"]
    mastered = old == "mastered"
    c = 3 if mastered else int(old)

    attempt = {"date": when, "tier": q, "result": result, "concept": concept, "source": source}
    if forced:
        attempt["forced"] = True
    rec["attempts"] = (rec["attempts"] + [attempt])[-MAX_ATTEMPTS:]
    rec["last_quizzed"] = when
    if stem:
        rec["recent_stems"] = (rec["recent_stems"] + [stem])[-MAX_STEMS:]
    notes = []
    if result == "correct":
        before = len(rec["weak_concepts"])
        rec["weak_concepts"] = [w for w in rec["weak_concepts"] if not _same(w["concept"], concept)]
        if len(rec["weak_concepts"]) < before:
            notes.append("weak concept cleared")
    elif add_weak(rec, concept, source, when):
        notes.append("weak concept added")

    pts_before = rec["points"]
    new = old
    if q < c:
        notes.append(f"below current tier {tier_label(old)}: logged only")
    elif mastered:
        if result == "incorrect":
            new = 3
    else:
        if result == "correct":
            rec["points"] += 1
            rec["consecutive_misses"] = 0
        elif result == "partial":
            rec["points"] += 0.5
        elif q == c:
            rec["consecutive_misses"] += 1
        else:
            notes.append("miss above current tier: not counted toward demotion")
        if rec["points"] >= 3:
            new = c + 1 if c < 3 else "mastered"
        elif q == c and rec["consecutive_misses"] >= 2 and c > 1:
            new = c - 1
    rec["points"] = clean_number(rec["points"])

    head = f"{result} at T{q} (topic {tier_label(old)})"
    if new != old:
        rec["tier"] = new
        rec["points"] = 0
        rec["consecutive_misses"] = 0
        rec["last_tier_change"] = {"date": when, "from": old, "to": new}
        verb = "promoted" if tier_num(new) > tier_num(old) else "demoted"
        notes.insert(0, f"{verb} {tier_label(old)} → {tier_label(new)}")
    elif rec["points"] != pts_before:
        notes.insert(0, f"points {clean_number(pts_before)} → {rec['points']} of 3")
    if rec["consecutive_misses"] and new == old:
        notes.append(f"{rec['consecutive_misses']} miss(es) in a row")
    return head + ("; " + "; ".join(notes) if notes else "")


# ---------------------------------------------------------------- scope and priority

def find_path(course: Course, token: str) -> str | None:
    tok = norm_path(token)
    candidates = [tok] + [f"{f['folder']}/{tok}" for f in course.folders]
    for c in candidates:
        if c and (course.root / c).exists():
            try:
                return norm_path((course.root / c).resolve().relative_to(course.root.resolve()).as_posix())
            except ValueError:
                raise StudyError(f"{token} is outside the course folder") from None
    return None


def resolve_scope(course: Course, tokens: list[str]) -> tuple[list[Topic], list[str]]:
    """Topics in scope (course order) and notes. Raises StudyError if a token matches nothing."""
    if not tokens:
        return list(course.topics), []
    chosen: set[str] = set()
    notes: list[str] = []
    for tok in tokens:
        p = find_path(course, tok)
        if p is not None:
            hits = [t for t in course.topics
                    if p in ("", ".") or any(s == p or s.startswith(p + "/") for s, _ in t.sources)]
            if not hits:
                notes.append(f"no indexed topics come from {p}")
            try:
                unindexed = [f for f, _ in scan(course.root, p) if f not in course.manifest]
            except StudyError:
                unindexed = []
            if unindexed:
                notes.append(f"{len(unindexed)} file(s) under {p} aren't indexed: {', '.join(unindexed[:5])}"
                             f"{' …' if len(unindexed) > 5 else ''}; re-run setup-study-skills to add them")
            chosen.update(t.id for t in hits)
            continue
        if tok in course.by_id:
            chosen.add(tok)
            continue
        words = tok.lower().split()
        hits = [t for t in course.topics if all(w in t.text() for w in words)]
        if not hits:
            raise StudyError(f"nothing matches {tok!r}: not a path, a topic ID, or a word in any topic title or concept")
        if len(hits) > 1:
            notes.append(f"{tok!r} matched {len(hits)} topics: {', '.join(t.id for t in hits)}")
        chosen.update(t.id for t in hits)
    return [t for t in course.topics if t.id in chosen], notes


def bucket(rec: dict, all_mastered: bool = False, today: dt.date | None = None) -> tuple[int | None, str]:
    atts = rec["attempts"]
    misses = [a for a in atts[-2:] if a["result"] == "incorrect"]
    if misses:
        return 1, f"{tier_label(rec['tier'])}, missed {len(misses)} of last {len(atts[-2:])}"
    ltc = rec.get("last_tier_change")
    if ltc and tier_num(ltc["to"]) < tier_num(ltc["from"]) and days_since(ltc["date"], today) <= DEMOTION_DAYS:
        return 1, f"demoted {tier_label(ltc['from'])} → {tier_label(ltc['to'])} on {ltc['date'][:10]}"
    lq = rec["last_quizzed"]
    weak = [w["concept"] for w in rec["weak_concepts"]
            if w.get("source") == "teach" and (lq is None or w["added"] > lq)]
    if weak:
        return 2, f"{tier_label(rec['tier'])}, weak from teaching: {'; '.join(weak)}"
    if rec["tier"] == "mastered":
        if lq is None or days_since(lq, today) > REVIEW_DAYS:
            return 5, f"mastered, last quizzed {lq[:10] if lq else 'never'}"
        if all_mastered:
            return 5, f"mastered, reviewed {days_since(lq, today)} day(s) ago"
        return None, f"mastered, reviewed {days_since(lq, today)} day(s) ago"
    if lq is not None:
        return 3, f"{tier_label(rec['tier'])}, {rec['points']} of 3 points, last quizzed {lq[:10]}"
    return 4, "new" + ("" if rec["taught"] else ", not taught yet")


def rank(course: Course, topics: list[Topic], all_mastered: bool = False,
         today: dt.date | None = None) -> list[tuple[Topic, int, str]]:
    ranked = []
    for t in topics:
        rec = course.progress["topics"].get(t.id) or fresh_record()
        b, why = bucket(rec, all_mastered, today)
        if b is None:
            continue
        lq = rec["last_quizzed"] or ""
        if b in (1, 2, 3):
            key = (b, tier_num(rec["tier"]), lq, t.order)
        elif b == 4:
            key = (b, 0, "", t.order)
        else:
            key = (b, 0, lq, t.order)
        ranked.append((key, t, b, why))
    ranked.sort(key=lambda r: r[0])
    return [(t, b, why) for _, t, b, why in ranked]


# ---------------------------------------------------------------- manifest

def unit_for(rel: str, folder: dict) -> str:
    if folder["role"] == "style-reference" or not folder["units"]:
        return "(style)" if folder["role"] == "style-reference" else "?"
    if len(folder["units"]) == 1:
        return folder["units"][0]
    rest = rel[len(folder["folder"]) + 1:] if rel.startswith(folder["folder"] + "/") else rel
    first = rest.split("/")[0]
    for cand in (slug(first), slug(Path(first).stem)):
        if cand in folder["units"]:
            return cand
    return "?"


def current_files(course: Course) -> dict[str, tuple[str, str]]:
    files = {}
    for f in course.folders:
        for rel, mt in scan(course.root, f["folder"]):
            files[rel] = (mt, unit_for(rel, f))
    return files


def manifest_table(files: dict[str, tuple[str, str]]) -> str:
    lines = ["## Manifest", "| File | Modified | Unit |", "|---|---|---|"]
    lines += [f"| {p} | {mt} | {u} |" for p, (mt, u) in sorted(files.items())]
    return "\n".join(lines) + "\n"


def write_manifest(course: Course) -> int:
    tp = study_path(course.root, "topics.md")
    text = tp.read_text(encoding="utf-8") if tp.exists() else ""
    files = current_files(course)
    table = manifest_table(files)
    m = re.search(r"^## Manifest\b.*?(?=^## |\Z)", text, re.M | re.S)
    if m:
        text = text[:m.start()] + table + ("\n" if text[m.end():].strip() else "") + text[m.end():]
    else:
        text = text.rstrip("\n") + "\n\n" + table
    atomic_write(tp, text)
    return len(files)


def diff_manifest(course: Course) -> dict[str, list[str]]:
    files = current_files(course)
    return {
        "new": sorted(p for p in files if p not in course.manifest),
        "modified": sorted(p for p in files if p in course.manifest and course.manifest[p][0] != files[p][0]),
        "deleted": sorted(p for p in course.manifest if p not in files),
    }


# ---------------------------------------------------------------- status

def status_text(course: Course, topics: list[Topic], today: dt.date | None = None) -> str:
    recs = course.progress["topics"]
    out = []
    lqs = [r["last_quizzed"] for r in recs.values() if r.get("last_quizzed")]
    out.append(f"{course.root.resolve().name}: {len(topics)} topic(s) in scope · last quiz {max(lqs)[:10] if lqs else 'never'}")
    idw = max([len(t.id) for t in topics] + [2])
    units: dict[str, list[Topic]] = {}
    for t in topics:
        units.setdefault(t.unit, []).append(t)
    for unit, ts in units.items():
        out.append("")
        out.append(f"{unit} ({len(ts)} topic{'s' if len(ts) != 1 else ''})")
        out.append(f"  {'ID':<{idw}}  Tier  Pts  Taught      Quizzed     Recent  Weak concepts")
        for t in ts:
            r = recs.get(t.id) or fresh_record()
            quizzed = bool(r["last_quizzed"])
            tier = tier_label(r["tier"]) if quizzed or r["tier"] != 1 else "new"
            pts = str(r["points"]) if quizzed else "—"
            sym = {"correct": "✓", "partial": "~", "incorrect": "✗"}
            recent = "".join(sym[a["result"]] + ("*" if a.get("forced") else "") for a in r["attempts"][-4:]) or "—"
            weak = ", ".join(w["concept"] for w in r["weak_concepts"]) or "—"
            if len(weak) > 50:
                weak = weak[:49] + "…"
            out.append(f"  {t.id:<{idw}}  {tier:<4}  {pts:<3}  {(r['taught'] or '—')[:10]:<10}  "
                       f"{(r['last_quizzed'] or '—')[:10]:<10}  {recent:<6}  {weak}")
    counts = {"new": 0, "T1": 0, "T2": 0, "T3": 0, "M": 0}
    taught = weak_total = 0
    for t in topics:
        r = recs.get(t.id) or fresh_record()
        counts["new" if not r["last_quizzed"] and r["tier"] == 1 else tier_label(r["tier"])] += 1
        taught += bool(r["taught"])
        weak_total += len(r["weak_concepts"])
    out.append("")
    out.append(f"Tiers: new {counts['new']} · T1 {counts['T1']} · T2 {counts['T2']} · T3 {counts['T3']} · "
               f"mastered {counts['M']}   Taught {taught}/{len(topics)}   Weak concepts {weak_total}")
    out.append("")
    out.append("Next up for quiz-me:")
    ranked = rank(course, topics, today=today)[:4]
    out += [f"  {t.id} — {why}" for t, _, why in ranked] or ["  nothing due (everything in scope is mastered and fresh)"]
    untaught = [t for t in topics if not (recs.get(t.id) or {}).get("taught")][:3]
    if untaught:
        out.append("Next up for teach-me:")
        out += [f"  {t.id} — {t.title}" for t in untaught]
    try:
        d = diff_manifest(course)
    except StudyError:
        d = {"new": [], "modified": [], "deleted": []}
    if any(d.values()):
        out.append("")
        out.append("Unindexed changes (re-run setup-study-skills to pick them up):")
        for kind in ("new", "modified", "deleted"):
            for p in d[kind]:
                out.append(f"  {kind:<8} {p}")
    return "\n".join(out)


# ---------------------------------------------------------------- validate

def validate(course: Course) -> list[str]:
    problems = []
    seen = set()
    for t in course.topics:
        if t.id in seen:
            problems.append(f"duplicate topic ID {t.id}")
        seen.add(t.id)
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", t.id):
            problems.append(f"topic ID {t.id!r} should be lowercase letters, digits, '.', '_' or '-'")
        if not t.sources:
            problems.append(f"{t.id} has no Sources line")
        if not t.concepts:
            problems.append(f"{t.id} has no concepts")
        for s, _ in t.sources:
            if not (course.root / s).exists():
                problems.append(f"{t.id}: source file not found: {s}")
    if not course.topics:
        problems.append("study/topics.md has no topics")
    missing = [t.id for t in course.topics if t.id not in course.progress["topics"]]
    if missing:
        problems.append(f"{len(missing)} topic(s) have no progress record (run init-progress): {', '.join(missing[:5])}")
    for f in course.folders:
        if f["role"] not in ("material", "style-reference", "both"):
            problems.append(f"config: folder {f['folder']} has unknown role {f['role']!r}")
        if not (course.root / f["folder"]).exists():
            problems.append(f"config: folder {f['folder']} not found")
    return problems


# ---------------------------------------------------------------- CLI

def parse_tier(s: str) -> int:
    t = TIER_NAMES.get(str(s).strip().lower().lstrip("t"))
    if t is None:
        raise StudyError(f"tier must be 1, 2, 3, easy, medium or hard (got {s!r})")
    return t


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="study.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".", help="course root (default: current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("now", help="current local date and time")
    p = sub.add_parser("extract", help="print the text of files")
    p.add_argument("files", nargs="+")
    p.add_argument("--pages", help="PDF page range, e.g. 1-20")
    sub.add_parser("survey", help="top-level folders with readable-file counts")
    p = sub.add_parser("scan", help="readable files under folders, with modification times")
    p.add_argument("folders", nargs="+")
    p = sub.add_parser("manifest", help="manifest table for the configured content folders")
    p.add_argument("--write", action="store_true", help="replace the Manifest section of study/topics.md")
    p = sub.add_parser("diff-manifest", help="files new, modified or deleted since the manifest")
    p.add_argument("--json", action="store_true")
    sub.add_parser("init-progress", help="add fresh progress records for topics without one")
    p = sub.add_parser("topics", help="topics in scope, in course order")
    p.add_argument("scope", nargs="*")
    p.add_argument("--untaught", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("priority", help="topics ranked by need")
    p.add_argument("scope", nargs="*")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--all-mastered", action="store_true", help="include recently reviewed mastered topics last")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("record", help="apply one graded answer")
    p.add_argument("--topic", required=True)
    p.add_argument("--tier", required=True, help="tier the question was asked at: 1|2|3|easy|medium|hard")
    p.add_argument("--result", required=True, choices=RESULTS)
    p.add_argument("--concept", required=True)
    p.add_argument("--stem", default="", help="short stem of the question (15 words max)")
    p.add_argument("--source", default="quiz", choices=("quiz", "mock-exam"))
    p.add_argument("--forced", action="store_true", help="the tier was forced with --tier")
    p = sub.add_parser("add-weak", help="add a weak concept to a topic")
    p.add_argument("--topic", required=True)
    p.add_argument("--concept", required=True)
    p.add_argument("--source", default="teach")
    p = sub.add_parser("mark-taught", help="mark a topic as taught")
    p.add_argument("--topic", required=True)
    p = sub.add_parser("status", help="progress dashboard")
    p.add_argument("scope", nargs="*")
    sub.add_parser("validate", help="check topics.md and progress.json")
    args = ap.parse_args(argv)
    root = Path(args.root)

    try:
        if args.cmd == "now":
            print(now())
        elif args.cmd == "extract":
            for i, f in enumerate(args.files):
                if len(args.files) > 1:
                    print(f"{'' if i == 0 else chr(10)}===== {f} =====")
                print(extract(root / f if not Path(f).is_absolute() else Path(f), args.pages))
        elif args.cmd == "survey":
            for r in survey(root):
                counts = ", ".join(f"{n} {e}" for e, n in sorted(r["readable"].items())) or "no readable files"
                extra = f"; {r['other']} other" if r["other"] else ""
                print(f"{r['name']}{'/' if r['kind'] == 'folder' else ''}\t{counts}{extra}")
        elif args.cmd == "scan":
            for folder in args.folders:
                for rel, mt in scan(root, norm_path(folder)):
                    print(f"{rel}\t{mt}")
        elif args.cmd == "manifest":
            course = Course(root)
            if args.write:
                print(f"wrote manifest of {write_manifest(course)} file(s) to study/topics.md")
            else:
                print(manifest_table(current_files(course)), end="")
        elif args.cmd == "diff-manifest":
            d = diff_manifest(Course(root))
            if args.json:
                print(json.dumps(d, indent=1))
            else:
                for kind in ("new", "modified", "deleted"):
                    for p_ in d[kind]:
                        print(f"{kind}\t{p_}")
                print(f"{len(d['new'])} new, {len(d['modified'])} modified, {len(d['deleted'])} deleted")
        elif args.cmd == "init-progress":
            course = Course(root)
            ids = [t.id for t in course.topics]
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            if dupes:
                raise StudyError(f"duplicate topic IDs in study/topics.md: {', '.join(dupes)}")
            recs = course.progress["topics"]
            added = [i for i in ids if i not in recs]
            ordered = {i: recs.get(i) or fresh_record() for i in ids}
            ordered.update({k: v for k, v in recs.items() if k not in ordered})
            course.progress["topics"] = ordered
            course.save()
            print(f"added {len(added)} record(s); {len(ids)} topic(s) total")
        elif args.cmd == "topics":
            course = Course(root)
            topics, notes = resolve_scope(course, args.scope)
            if args.untaught:
                topics = [t for t in topics if not (course.progress["topics"].get(t.id) or {}).get("taught")]
            if args.json:
                print(json.dumps([{"id": t.id, "title": t.title, "unit": t.unit,
                                   "sources": [s for s, _ in t.sources], "concepts": t.concepts,
                                   **(course.progress["topics"].get(t.id) or fresh_record())} for t in topics],
                                 indent=1, ensure_ascii=False))
            else:
                for n in notes:
                    print(f"note: {n}")
                for t in topics:
                    r = course.progress["topics"].get(t.id) or fresh_record()
                    srcs = "; ".join(f"{s} {loc}".strip() for s, loc in t.sources)
                    print(f"{t.id} — {t.title} [{t.unit}] {tier_label(r['tier'])}"
                          f"{', taught ' + r['taught'][:10] if r['taught'] else ', untaught'} · {srcs}")
        elif args.cmd == "priority":
            course = Course(root)
            topics, notes = resolve_scope(course, args.scope)
            ranked = rank(course, topics, args.all_mastered)
            if args.limit:
                ranked = ranked[:args.limit]
            if args.json:
                print(json.dumps([{"id": t.id, "title": t.title, "bucket": b, "bucket_name": BUCKET_NAMES[b],
                                   "reason": why, "sources": [s for s, _ in t.sources]} for t, b, why in ranked],
                                 indent=1, ensure_ascii=False))
            else:
                for n in notes:
                    print(f"note: {n}")
                for i, (t, b, why) in enumerate(ranked, 1):
                    print(f"{i}. {t.id} [{BUCKET_NAMES[b]}] {why}")
                if not ranked:
                    print("nothing due: every topic in scope is mastered and was reviewed in the last 14 days")
        elif args.cmd in ("record", "add-weak", "mark-taught"):
            course = Course(root)
            if args.topic not in course.by_id:
                raise StudyError(f"unknown topic ID {args.topic!r} (see study/topics.md)")
            rec = course.record(args.topic)
            if args.cmd == "record":
                msg = apply_result(rec, parse_tier(args.tier), args.result, args.concept,
                                   stem=" ".join(args.stem.split()[:15]), source=args.source, forced=args.forced)
            elif args.cmd == "add-weak":
                msg = "weak concept added" if add_weak(rec, args.concept, args.source, now()) else "already listed"
            else:
                rec["taught"] = now()
                msg = f"taught {rec['taught']}"
            course.save()
            print(f"{args.topic}: {msg}")
        elif args.cmd == "status":
            course = Course(root)
            topics, notes = resolve_scope(course, args.scope)
            for n in notes:
                print(f"note: {n}")
            print(status_text(course, topics))
        elif args.cmd == "validate":
            problems = validate(Course(root))
            for pr in problems:
                print(f"problem: {pr}")
            print("ok" if not problems else f"{len(problems)} problem(s)")
            return 1 if problems else 0
    except StudyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
