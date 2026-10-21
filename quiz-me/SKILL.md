---
name: quiz-me
description: Tiered, adaptive one-question-at-a-time quiz on course material. Reads study/progress.json to focus on the topics that need the most help, quizzes each topic at its tier (easy → medium → hard → mastered), and updates progress after every answer. Takes an optional --tier flag and files, folders, topic IDs, or topic names as scope.
argument-hint: "[--tier 1|2|3|easy|medium|hard] [folder | file | topic-id | \"topic name\" ...]"
---

# /quiz-me

Quiz the user on course material, focusing where they need the most help. Arguments: `$ARGUMENTS`

The course root is the current working directory. Study data lives in `study/`.

## 1. Load state

1. If `study/config.md` doesn't exist, say the course isn't set up, suggest `/setup-study-skills`, and stop.
2. Read `study/config.md`, `study/topics.md`, and `study/progress.json`. `topics.md` decides which topics exist; ignore progress records with no topic, and treat a topic with no record as fresh: `{"tier": 1, "points": 0, "consecutive_misses": 0, "last_tier_change": null, "last_quizzed": null, "taught": null, "weak_concepts": [], "recent_stems": [], "attempts": []}`.
3. Get today's date and time with `date '+%Y-%m-%d %H:%M'`.

## 2. Parse the arguments

Parse the arguments as whitespace-separated tokens; honor quotes, since filenames contain spaces.
- `--tier N` (or `--tier=N`), where N is `1|2|3` or `easy|medium|hard`: the **forced tier**. Questions are written at that tier for every topic.
- Every other token is scope, resolved in order:
  1. A path that exists relative to the course root, or inside one of the configured content folders: selects every topic whose sources lie inside it. If files under it are missing from the manifest in `topics.md`, warn that they aren't indexed and suggest re-running `/setup-study-skills`.
  2. An exact topic ID: that topic.
  3. A loose name, matched case-insensitively against topic titles and concepts. If several topics match, include them all and list them in the plan line; if none match, say so and stop.
- No scope tokens: every topic in the course.

## 3. Rank topics and pick a working set

Sort the in-scope topics into priority buckets, first match wins:
1. **Struggling:** an `incorrect` among its last 2 attempts, or `last_tier_change` is a demotion within the last 7 days.
2. **Flagged in teaching:** has a weak concept with `"source": "teach"` added after `last_quizzed` (or never quizzed).
3. **In progress:** quizzed before and not mastered. Lowest tier first; ties go to the oldest `last_quizzed`.
4. **New:** never quizzed, in course order (the order in `topics.md`).
5. **Review:** mastered, with `last_quizzed` more than 14 days ago.

Mastered topics quizzed within the last 14 days are left out. If nothing in scope is left, say so (everything in scope is mastered and fresh) and offer a review anyway, or `--tier 3`.

Take the top 4 topics as the **working set** (fewer if the scope is smaller). Print one plan line, e.g.:

`Focusing on: hw3-fisher-bound (T1, 2 recent misses), hw2-poisson-variance (T2, weak: Fano factor), hw1-tuning-curves (new), hw4-attractors (T2)`

Add `Forced tier: T2` when the flag is set.

## 4. Read the sources

Read every source file named in the `Sources:` lines of the working-set topics. For T3 questions (including a forced T3), also read up to 3 style-reference files from the folders listed in `study/config.md` to model question style: past exams from `style-reference` folders first, then problem-set handouts from `both` folders, preferring those closest to the topic. When a new topic joins the working set later, read its sources then. Read fully, by type, issuing independent reads in parallel:
- `.md`, `.txt`, `.tex`, `.py`, `.m`, `.R`, `.jl`, `.ipynb`: Read tool.
- `.pdf`: Read tool; for PDFs over 10 pages pass `pages` in chunks of at most 20. If that fails, extract text with `osascript -l JavaScript -e 'function run(argv){ObjC.import("PDFKit");var d=$.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));return d.string.js}' "<file>"`.
- `.docx`: `textutil -convert txt -stdout "<file>"`.
- `.pptx`: for each `s` in `unzip -Z1 "<file>" | grep -E '^ppt/slides/slide[0-9]+\.xml$' | sort -V`, run `unzip -p "<file>" "$s" | sed -e 's/<\/a:p>/\n/g' -e 's/<[^>]*>//g'`.

## 5. Style rules

- Questions and answers come from the files. Explanations may add intuition only when marked "(beyond lecture)".
- Output is read in a terminal. Follow the math and citation styles in `study/config.md`. Be concise; minimal bold, few bullets.
- Cite the source of each answer.

## 6. Tiers and formats

Each question is written at a tier: the topic's current tier, or the forced tier. A mastered topic is asked at T3.
- **T1 Easy (recall and recognition):** definitions, identifying a mechanism or term, straightforward multiple choice.
- **T2 Medium (mechanism and application):** "why does…" / "what happens if…" short answers, single-step predict-the-result, short calculations.
- **T3 Hard (integration and analysis):** multi-step reasoning, questions that join this topic with another in scope, experimental design or data interpretation, derivations, exam-style problems modeled on the style references.

Use only the question formats allowed in `study/config.md`. If none of a tier's natural formats is allowed, use a short answer at that tier's level. Multiple choice has four options labeled A–D with plausible distractors; the user answers in text. Label each question with its topic and tier, e.g. `Q3 [hw2-poisson-variance · T2]`.

## 7. Quiz loop

1. Ask exactly one question per turn, then end your turn and wait. Never reveal the answer before the user responds.
2. Interleave: rotate through the working set, never asking the same topic twice in a row while others remain. Topics in bucket 1 come up about twice as often as the rest.
3. Aim each question at one of the topic's concepts, preferring its weak concepts first, then concepts not tested recently. Don't repeat a question from this session or anything close to its `recent_stems`.
4. Grade each answer as `correct`, `partial`, or `incorrect`. Then give a short explanation of the right answer with its citation, and point out what was missing or wrong in theirs. A "skip" counts as `incorrect`: give the answer and move on.
5. After a miss (`partial` or `incorrect`), queue a differently worded question on the same concept 3–5 questions later.
6. Update `study/progress.json` after every graded answer (§8), and announce any tier change in one line, e.g. `hw2-poisson-variance: T2 → T3`.
7. A topic that is promoted, or a mastered topic answered correctly once (its review is done), leaves the working set; refill from the next topic in priority order and read its sources. A topic promoted to mastered also leaves.
8. Keep a running tally (correct / partial / incorrect) and the list of missed concepts.
9. Continue until the user says "stop" (or "done", "quit").

## 8. Update progress after every answer

Edit only that topic's line in `study/progress.json` (one topic record per line; add a fresh record line if the topic has none). Let `Q` be the question's tier and `C` the topic's current tier (T3 for mastered).

Always:
- Append `{"date": "<YYYY-MM-DD>", "tier": Q, "result": "<result>", "concept": "<concept>", "source": "quiz"}` to `attempts`, and add `"forced": true` when the tier was forced. Keep only the last 20 attempts.
- Set `last_quizzed` to today.
- Add a short stem of the question (at most 15 words) to `recent_stems`, keeping only the last 8.
- `partial` or `incorrect`: add the concept to `weak_concepts` as `{"concept": "<concept>", "added": "<YYYY-MM-DD>", "source": "quiz"}` if it isn't already listed.
- `correct`: remove that concept from `weak_concepts` if it is listed (from any source).

Tier rules, when `Q` equals `C` (normal quizzing):
- `correct` adds 1 point, `partial` adds 0.5. `correct` resets `consecutive_misses` to 0; `partial` leaves it unchanged.
- `incorrect` adds 1 to `consecutive_misses`.
- **Promote** when points reach 3: T1 → T2 → T3 → `"mastered"`.
- **Demote** one tier when `consecutive_misses` reaches 2, but never below T1.
- A mastered topic answered `incorrect` drops to T3. A correct or partial answer on a mastered topic changes nothing else.
- On any tier change, set `points` and `consecutive_misses` to 0, and set `last_tier_change` to `{"date": "<YYYY-MM-DD>", "from": <old>, "to": <new>}`.

Forced tier above the current one (`Q` > `C`): `correct` counts as 1 point at `C` (so a topic never skips a tier) and resets `consecutive_misses`; `partial` adds 0.5 at `C`; `incorrect` changes neither points nor misses. Promotion works as above.

Forced tier below the current one (`Q` < `C`): record the attempt only; points, misses, and tier don't change.

After each write, validate with `python3 -c 'import json,sys; json.load(open(sys.argv[1]))' study/progress.json` and fix any error.

## 9. On stop

1. Print the score (partial counts as half), the tier changes, and the missed concepts. Suggest `/teach-me <topic-id>` for any topic missed more than once this session.
2. Append an entry to `study/log.md`:
   ```
   ## 2026-10-19 14:05 — quiz — scope: all (forced tier: none)
   Score: 7/10 (2 partial)
   Tier changes: hw1-tuning-curves T1→T2; hw2-poisson-variance T2→T1
   Missed: hw2-poisson-variance: Fano factor of a Poisson process; hw3-fisher-bound: when the Cramér-Rao bound is tight
   ```
   Write `Tier changes: none` or `Missed: none` when empty.
