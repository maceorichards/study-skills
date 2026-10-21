---
name: setup-study-skills
description: Index a course's study material into a topic map and create the study/ folder (config, topics, progress, log) that teach-me, quiz-me, study-status and mock-exam use. Run once per course, and again whenever new lectures or homeworks arrive.
argument-hint: "[folder ...]"
---

# /setup-study-skills

Set up (or refresh) study tracking for this course. Arguments: `$ARGUMENTS`

The course root is the current working directory (the folder that contains `.claude/`). All paths below are relative to it. Study data lives in `study/` at the course root.

## 1. Pick the mode

- `study/config.md` exists: **re-run mode**. Follow §7 instead of §2–6.
- Otherwise: **first run**. Continue with §2.

## 2. Choose content folders and preferences (one message, then wait)

1. Folders: if arguments were given, parse them as whitespace-separated paths (honor quotes) and use those. Otherwise list the top-level folders of the course root and propose the ones that hold course material. Never propose `.claude/`, `study/`, hidden folders, virtualenvs, build output, or folders with only binaries (`.pxp`, `.zip`, images, compiled code).
2. Give each folder a role:
   - `material`: topics are extracted from it (lectures, notes, readings, papers).
   - `style-reference`: no topics; its question style models hard (T3) questions and mock exams (past exams, practice exams).
   - `both`: topics are extracted, and it is also a style reference (homeworks, problem sets).
3. Units: a unit is the group of files one set of topics comes from. A content folder is one unit, unless it is a container of self-contained units (e.g. `lectures/` holding one subfolder per lecture date); then each child subfolder or loose file is a unit. Unit names are the folder or file name, lowercased, spaces as `-`, extension dropped.
4. Preferences: propose defaults that fit the material, for the user to confirm or change:
   - Question formats allowed, from: short answer, multiple choice, predict-the-result, calculation, derivation, code. (A quantitative course likely wants calculation/derivation; a mostly conceptual one may not.)
   - Math style: default plain-text math (`tau = R_m * C_m`), no LaTeX.
   - Citation style: default `[<file stem>, p.N]` or `[<file stem>, §section]`.
   - Any other course notes (e.g. "focus on intuition over proofs").
5. Show it all in one compact message: a table of folder → role → units, the skipped folders with a one-word reason, and the preference defaults. Ask the user to confirm or edit. End your turn and wait.

## 3. Collect files

For each content folder, list files recursively (`find <folder> -type f`), then drop:
- hidden files and anything under a hidden folder; `build/`, `node_modules/`, `__pycache__/`, `.ipynb_checkpoints/`, virtualenvs;
- LaTeX byproducts (`.aux .log .out .toc .fls .fdb_latexmk .synctex.gz .bbl .blg`) and backups (`.orig`, `~`);
- images, archives, and other binaries; figure-only folders (`figures/`, `scans/`, `img/`);
- a `.pdf` whose stem matches a `.tex` in the same unit (read the source instead).

Readable types are `.md .txt .tex .py .m .R .jl .ipynb .pdf .docx .pptx`. Record each kept file's modification time with `stat -f '%Sm' -t '%Y-%m-%d %H:%M' "<file>"`.

## 4. Extract topics with subagents

Dispatch one subagent per unit of a `material` or `both` folder, all in parallel. Give each one the unit name and the absolute paths of its files (never pasted content) and this brief:

> Read every file below fully, by type:
> - `.md .txt .tex .py .m .R .jl`, `.ipynb`: Read tool.
> - `.pdf`: Read tool; for PDFs over 10 pages pass `pages` in chunks of at most 20. If that fails, extract text with `osascript -l JavaScript -e 'function run(argv){ObjC.import("PDFKit");var d=$.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));return d.string.js}' "<file>"`.
> - `.docx`: `textutil -convert txt -stdout "<file>"`.
> - `.pptx`: for each `s` in `unzip -Z1 "<file>" | grep -E '^ppt/slides/slide[0-9]+\.xml$' | sort -V`, run `unzip -p "<file>" "$s" | sed -e 's/<\/a:p>/\n/g' -e 's/<[^>]*>//g'`.
>
> Split the unit's content into topics: coherent sections of the material, usually 3–8 per lecture-sized unit. For a problem set, topics are the ideas the problems exercise (e.g. "Fisher information of Poisson neurons"), not "Problem 1". For each topic return:
> - a short kebab-case slug (2–4 words) and a title;
> - sources: file path(s) relative to the course root, with pages or sections;
> - 3–8 concepts: specific, testable statements of what someone who knows this topic can explain, predict, or compute.
>
> Return plain text in this shape, topics in the order they appear in the material:
> ```
> ### <slug> — <title>
> Sources: <path> p.2-4; <path> §1.2
> Concepts:
> - <concept>
> ```
> Then a final line `Unreadable: <files>` (or `Unreadable: none`).

Then merge: put units in course order (chronological where names are dates, otherwise the order a student would meet them), drop duplicate topics across units (keep the first, add the other's sources), and form IDs as `<unit>-<slug>`. IDs must be unique; add a suffix if needed.

## 5. Review the topic map (then wait)

Show the draft titles only, grouped by unit: `<ID> — <title>`, plus the topic count and any unreadable files. Ask the user to merge, split, rename, or drop topics, or say "looks good". Apply the edits; repeat until they approve.

## 6. Write `study/`

Create `study/` with four files. Use today's date and time from `date '+%Y-%m-%d %H:%M'`.

`study/config.md`:
```
# Study config: <course folder name>

## Content folders
| Folder | Role | Units |
|---|---|---|
| lectures | material | 2026-09-03, 2026-09-08 |
| hw1 | both | hw1 |
| midterm | style-reference | — |

## Preferences
- Question formats: short answer, multiple choice, predict-the-result, calculation
- Math: plain text, no LaTeX
- Citations: [<file stem>, p.N]
- Notes: <free text or none>
```

`study/topics.md`, units in course order, topics in material order (this order is "course order" for every skill):
```
# Topics: <course folder name>

## Unit: hw1 (hw1/)

### hw1-poisson-fisher-info — Fisher information of Poisson neurons
Sources: hw1/9_49_Homeworks-6.pdf p.1; hw1/HW1_maceorichards.tex §1
Concepts:
- <concept>

## Manifest
| File | Modified | Unit |
|---|---|---|
| hw1/HW1_maceorichards.tex | 2026-09-25 14:06 | hw1 |
| midterm/midterm_orig.pdf | 2026-10-15 01:06 | (style) |
```
The manifest lists every kept file from §3, including style-reference files (unit `(style)`).

`study/progress.json`: one topic record per line, so a single topic can be edited in place:
```
{
"version": 1,
"topics": {
"hw1-poisson-fisher-info": {"tier": 1, "points": 0, "consecutive_misses": 0, "last_tier_change": null, "last_quizzed": null, "taught": null, "weak_concepts": [], "recent_stems": [], "attempts": []},
"hw1-population-coding": {"tier": 1, "points": 0, "consecutive_misses": 0, "last_tier_change": null, "last_quizzed": null, "taught": null, "weak_concepts": [], "recent_stems": [], "attempts": []}
}
}
```
Validate it with `python3 -c 'import json,sys; json.load(open(sys.argv[1]))' study/progress.json`.

`study/log.md`:
```
# Study log

## 2026-10-19 14:05 — setup
Units: 7 · Topics: 31 · Style references: midterm
```

Finish with a short summary: topics per unit, where the files are, and the next steps: `/teach-me` to learn untaught topics, `/quiz-me` to start tiered quizzing, `/study-status` to see progress. Mention that `config.md` and `topics.md` can be edited by hand.

## 7. Re-run mode

1. Read `study/config.md` and `study/topics.md` (including the manifest). Keep the saved preferences; the user can edit `config.md` directly or ask to change them.
2. If arguments name folders not yet in config, propose roles and units for them as in §2 and wait for confirmation.
3. Re-collect files (§3) for every content folder and compare with the manifest: new files, modified files (different time), and deleted files.
4. If nothing changed, say so and stop.
5. For each unit with new or modified files (in a `material`/`both` folder), dispatch the §4 subagent. Add to its brief the unit's existing topic titles and concepts, and ask it to return only topics not already covered, plus any concepts or sources to add to existing topics. Style-reference changes only update the manifest.
6. Show the proposed additions (new topic IDs and titles, additions to existing topics) and wait for approval, as in §5.
7. Apply: append new topics within their unit in `topics.md`, apply additions to existing topics, update the manifest, and add a fresh record for each new topic to `progress.json`. Never rename, renumber, or delete an existing topic ID, and never reset existing progress. For deleted files, keep their topics and list them in the summary so the user can prune `topics.md` by hand.
8. Validate `progress.json`, append a `setup (refresh)` entry to `study/log.md` with counts of added topics, and summarize.
