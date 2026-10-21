---
name: teach-me
description: Socratic, chunked tutoring on course material, topic by topic with check questions. Takes files, folders, topic IDs, or topic names; with no arguments it offers the next untaught topic. Records taught topics and trouble spots in study/progress.json when the course is set up.
argument-hint: "[folder | file | topic-id | \"topic name\" ...]"
---

# /teach-me

Teach the material in scope interactively. Arguments: `$ARGUMENTS`

The course root is the current working directory. Study data, if the course is set up, lives in `study/` (created by `/setup-study-skills`).

## 1. Load state

If `study/config.md` exists, this is **tracked mode**: read `study/config.md`, `study/topics.md`, and `study/progress.json`. `topics.md` decides which topics exist; ignore progress records with no topic, and treat a topic with no record as fresh (`tier` 1, nothing taught).

Otherwise this is **untracked mode**: teach straight from the paths given, with nothing recorded. If there are no arguments, ask which file or folder to teach and wait. Mention once that `/setup-study-skills` enables progress tracking.

## 2. Resolve the scope

Parse the arguments as whitespace-separated tokens; honor quotes, since filenames contain spaces. For each token, in order:
1. A path that exists relative to the course root, or inside one of the configured content folders: a path. A folder means every file inside it, recursively, skipping hidden files.
2. In tracked mode, an exact topic ID from `topics.md`: that topic.
3. In tracked mode, otherwise: a loose name, matched case-insensitively against topic titles and concepts. If several topics match, list them and ask which; if none match, say so and stop.
4. In untracked mode, a token that is not an existing path: say which one and stop.

In tracked mode:
- A path selects every topic whose sources lie inside it. Files under the path that are missing from the manifest in `topics.md` are still taught, straight from the file, but warn that they aren't indexed and suggest re-running `/setup-study-skills`.
- No arguments: list the next up-to-5 topics in course order (the order in `topics.md`) with `taught: null`, as `<ID> — <title>`, and ask whether to start with the first or pick another. End your turn and wait. If every topic is taught, say so and offer the topics with the most weak concepts instead.

## 3. Read the sources

Read every source file of the selected topics (in tracked mode, the files named in their `Sources:` lines; in untracked mode, every file in scope). Read fully, by type, issuing independent reads in parallel:
- `.md`, `.txt`, `.tex`, `.py`, `.m`, `.R`, `.jl`, `.ipynb`: Read tool.
- `.pdf`: Read tool; for PDFs over 10 pages pass `pages` in chunks of at most 20. If that fails, extract text with `osascript -l JavaScript -e 'function run(argv){ObjC.import("PDFKit");var d=$.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));return d.string.js}' "<file>"`.
- `.docx`: `textutil -convert txt -stdout "<file>"`.
- `.pptx`: for each `s` in `unzip -Z1 "<file>" | grep -E '^ppt/slides/slide[0-9]+\.xml$' | sort -V`, run `unzip -p "<file>" "$s" | sed -e 's/<\/a:p>/\n/g' -e 's/<[^>]*>//g'`.
- Anything else: skip, and list it as skipped.

Print one short line: the topics in scope (or files loaded, in untracked mode), plus any skipped files.

## 4. Style rules

- Teach from the files. Outside intuition or analogies are fine only when marked "(beyond lecture)".
- Output is read in a terminal. Follow the math and citation styles in `study/config.md`; without a config, use plain-text math (`tau = R_m * C_m`), no LaTeX, and cite as `[<file stem>, p.N]`. Be concise; minimal bold, few bullets.
- Cite the specific file a point comes from.

## 5. Teaching loop

1. Open with a short numbered list of the topics in scope, in course order. Teach in that order unless the user picks a topic. In untracked mode, derive the topic list from the files.
2. Work through one topic at a time. In tracked mode, the topic's concepts in `topics.md` are what it must cover.
3. Each chunk: explain one concept in a few sentences (plus the key equation if there is one), then ask exactly one check question. End your turn and wait. Never answer your own question in the same turn.
4. On the answer:
   - Correct: confirm briefly, add any nuance the files give, move to the next concept.
   - Partial or wrong: name the specific gap, re-explain from a different angle or ask a leading sub-question, and re-check before moving on. Note the concept as a trouble spot.
5. Favor questions that test mechanism and prediction ("what happens if…", "why does…") over recall of definitions.
6. The user may say "skip", "go deeper", "next topic", or "stop" at any time; follow it.

## 6. Record progress (tracked mode only)

Write as you go, so nothing is lost if the session ends early. Edit only the affected topic's line in `study/progress.json` (one topic record per line); add a fresh record line if the topic has none:
- **Trouble spot:** when a concept needed re-explaining, add `{"concept": "<concept>", "added": "<YYYY-MM-DD>", "source": "teach"}` to that topic's `weak_concepts` (skip it if the same concept is already listed).
- **Topic finished:** when all of a topic's concepts have been covered (skipped concepts count as covered), set `"taught": "<YYYY-MM-DD>"`. A topic cut off by "stop" partway through stays untaught, but its trouble spots are kept.
- Never change `tier`, `points`, `consecutive_misses`, or `attempts`. Only quizzes move tiers.

After each write, validate with `python3 -c 'import json,sys; json.load(open(sys.argv[1]))' study/progress.json` and fix any error.

## 7. On stop

When the user says "stop" or all topics in scope are done:
1. Give a 3–5 line recap of what was covered and the concepts that gave trouble.
2. In tracked mode, append to `study/log.md` (time from `date '+%Y-%m-%d %H:%M'`):
   ```
   ## 2026-10-19 14:05 — teach — scope: hw1
   Taught: hw1-poisson-fisher-info, hw1-population-coding
   Trouble: hw1-population-coding: Fisher information adds across independent neurons
   ```
   Write `Trouble: none` if nothing gave trouble.
3. Suggest `/quiz-me` on the same scope.
