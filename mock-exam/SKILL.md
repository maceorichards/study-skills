---
name: mock-exam
description: Exam-style practice test across a scope. Writes N questions (default 10) mostly at medium and hard tiers, weighted toward weak topics and styled after past exams; no feedback until the user submits, then grades every answer and updates study/progress.json.
argument-hint: "[N] [folder | file | topic-id | \"topic name\" ...]"
---

# /mock-exam

Give the user a practice exam. Arguments: `$ARGUMENTS`

The course root is the current working directory. Study data lives in `study/`.

## 1. Load state

1. If `study/config.md` doesn't exist, say the course isn't set up, suggest `/setup-study-skills`, and stop.
2. Read `study/config.md`, `study/topics.md`, and `study/progress.json`. `topics.md` decides which topics exist; ignore progress records with no topic, and treat a topic with no record as fresh: `{"tier": 1, "points": 0, "consecutive_misses": 0, "last_tier_change": null, "last_quizzed": null, "taught": null, "weak_concepts": [], "recent_stems": [], "attempts": []}`.
3. Record the start time with `date '+%Y-%m-%d %H:%M'`.

## 2. Parse the arguments

Parse the arguments as whitespace-separated tokens; honor quotes, since filenames contain spaces.
- If the first token is a positive integer, it is N, the number of questions. Otherwise N = 10.
- Every other token is scope, resolved in order:
  1. A path that exists relative to the course root, or inside one of the configured content folders: selects every topic whose sources lie inside it.
  2. An exact topic ID: that topic.
  3. A loose name, matched case-insensitively against topic titles and concepts. If none match, say so and stop.
- No scope tokens: every topic in the course.

## 3. Choose topics and tiers

1. Rank the in-scope topics by these buckets, first match wins. Unlike `/quiz-me`, recently reviewed mastered topics stay eligible, ranked last.
   1. Struggling: an `incorrect` among its last 2 attempts, or `last_tier_change` is a demotion within the last 7 days.
   2. Flagged in teaching: a weak concept with `"source": "teach"` added after `last_quizzed` (or never quizzed).
   3. In progress: quizzed before and not mastered. Lowest tier first; ties go to the oldest `last_quizzed`.
   4. New: never quizzed, in course order.
   5. Mastered.
2. Spread N questions across topics: walk the ranked list giving each topic one question, wrapping around for a second pass only if N exceeds the number of topics. Give the top half of the list priority on the second pass. At most 2 questions per topic unless the scope has fewer than N/2 topics.
3. Each question's tier is the topic's tier plus one, kept between T2 and T3; mastered topics get T3. So a T1 topic gets a T2 question, and T2, T3, and mastered topics get T3 questions.
4. Where a T3 question can naturally join two in-scope topics, do so, and count it toward the first.

## 4. Read the sources

Read every source file named in the `Sources:` lines of the chosen topics, plus up to 4 style-reference files from the folders listed in `study/config.md`: every past exam in `style-reference` folders first (up to the limit), then problem-set handouts from `both` folders. Read fully, by type, issuing independent reads in parallel:
- `.md`, `.txt`, `.tex`, `.py`, `.m`, `.R`, `.jl`, `.ipynb`: Read tool.
- `.pdf`: Read tool; for PDFs over 10 pages pass `pages` in chunks of at most 20. If that fails, extract text with `osascript -l JavaScript -e 'function run(argv){ObjC.import("PDFKit");var d=$.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));return d.string.js}' "<file>"`.
- `.docx`: `textutil -convert txt -stdout "<file>"`.
- `.pptx`: for each `s` in `unzip -Z1 "<file>" | grep -E '^ppt/slides/slide[0-9]+\.xml$' | sort -V`, run `unzip -p "<file>" "$s" | sed -e 's/<\/a:p>/\n/g' -e 's/<[^>]*>//g'`.

## 5. Write the exam

- Questions come from the files. Model their phrasing, length, and structure on the style references (multi-part questions are fine if the past exams use them).
- T2 is mechanism and application ("why does…", "what happens if…", single-step prediction or calculation). T3 is integration and analysis (multi-step reasoning, combining topics, experimental design or data interpretation, derivations, exam-style problems).
- Use only the question formats allowed in `study/config.md`. Follow its math style. Avoid anything close to a topic's `recent_stems`.
- Save the exam to `study/exams/<YYYY-MM-DD-HHMM>.md` before showing it, with an answer key the user doesn't see. For each question record its number, topic ID, tier, target concept, the question, and a model answer with its citation.
- Show all questions at once as a numbered list, without topic or tier labels. Tell the user to answer by number, in one or several messages, and to say "submit" when done. End your turn and wait.

## 6. While the user answers

Acknowledge each message in one line (e.g. `Got 1–4; 6 left.`) with no hints and no grading. If the user asks about a question, clarify only what is being asked, never the answer.

## 7. On "submit"

1. Record the end time. Unanswered questions count as `incorrect`.
2. Grade each answer as `correct`, `partial`, or `incorrect`. For each, show the topic and tier, the grade, a short model answer with its citation, and what was missing or wrong.
3. Update `study/progress.json`, one topic line at a time (one topic record per line; add a fresh record line if the topic has none). Let `Q` be the question's tier and `C` the topic's current tier (T3 for mastered). For each answer:
   - Append `{"date": "<YYYY-MM-DD>", "tier": Q, "result": "<result>", "concept": "<concept>", "source": "mock-exam"}` to `attempts`, keeping only the last 20. Set `last_quizzed` to today. Add a short stem (at most 15 words) to `recent_stems`, keeping only the last 8.
   - `partial` or `incorrect`: add the concept to `weak_concepts` as `{"concept": "<concept>", "added": "<YYYY-MM-DD>", "source": "mock-exam"}` if not already listed. `correct`: remove that concept from `weak_concepts` if listed.
   - `Q` equals `C`: `correct` adds 1 point and resets `consecutive_misses`; `partial` adds 0.5; `incorrect` adds 1 to `consecutive_misses`. Promote at 3 points (T1 → T2 → T3 → `"mastered"`); demote one tier at 2 consecutive misses (never below T1); a mastered topic answered `incorrect` drops to T3.
   - `Q` above `C`: `correct` adds 1 point at `C` and resets `consecutive_misses`; `partial` adds 0.5 at `C`; `incorrect` changes neither points nor misses. Promotion works as above.
   - On any tier change, set `points` and `consecutive_misses` to 0 and `last_tier_change` to `{"date": "<YYYY-MM-DD>", "from": <old>, "to": <new>}`.
   - Validate with `python3 -c 'import json,sys; json.load(open(sys.argv[1]))' study/progress.json` and fix any error.
4. Append the user's answers and grades to the saved exam file.
5. Print the score (partial counts as half), results by topic, the tier changes, and the weakest concepts, then suggest `/quiz-me` or `/teach-me` on the topics missed.
6. Append to `study/log.md`:
   ```
   ## 2026-10-19 14:05 — mock-exam — scope: all — 10 questions
   Start: 14:05 · End: 14:52 · Exam: study/exams/2026-10-19-1405.md
   Score: 6.5/10 (3 partial)
   Tier changes: hw1-tuning-curves T1→T2
   Missed: hw3-fisher-bound: when the Cramér-Rao bound is tight
   ```
