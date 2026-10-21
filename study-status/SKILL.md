---
name: study-status
description: Read-only study dashboard for this course. Shows each topic's tier, points, recent results and weak concepts from study/progress.json, plus what /quiz-me would focus on next. Takes optional files, folders, topic IDs, or topic names as scope.
argument-hint: "[folder | file | topic-id | \"topic name\" ...]"
---

# /study-status

Report study progress. Arguments: `$ARGUMENTS`

This skill only reads. It never writes to `study/`.

## 1. Load state

1. The course root is the current working directory. If `study/config.md` doesn't exist, say the course isn't set up, suggest `/setup-study-skills`, and stop.
2. Read `study/config.md`, `study/topics.md`, and `study/progress.json`. `topics.md` decides which topics exist; ignore progress records with no topic, and treat a topic with no record as fresh (T1, 0 points, never taught or quizzed).
3. Get today's date with `date '+%Y-%m-%d'`.
4. Scope: parse the arguments as whitespace-separated tokens (honor quotes). A path selects topics whose sources lie inside it; an exact topic ID selects that topic; anything else is matched case-insensitively against topic titles and concepts. No arguments means the whole course.

## 2. Report

Output is plain text for a terminal; keep it compact.

1. **Per unit**, in course order, a header `<unit> (<n> topics)` and a table:
   ```
   ID                         Tier  Pts  Taught      Quizzed     Recent  Weak concepts
   hw1-poisson-fisher-info    T2    1.5  2026-10-02  2026-10-18  ✓✓~✗    Fisher info of a Poisson neuron
   hw1-population-coding      new   —    —           —           —       —
   ```
   - Tier: `T1`/`T2`/`T3`/`M` (mastered), or `new` if never quizzed.
   - Recent: the last 4 attempt results, oldest first: `✓` correct, `~` partial, `✗` incorrect; mark forced-tier attempts with `*`.
   - Weak concepts: comma-separated, truncated to fit; `—` if none.
2. **Summary**, one or two lines: topic counts by tier (new / T1 / T2 / T3 / mastered), taught vs untaught, total weak concepts, and the date of the last quiz.
3. **Next up for /quiz-me**: the first 4 topics by the priority buckets below, each with its reason (e.g. `hw3-fisher-bound — T1, missed 2 of last 2`). First match wins:
   1. Struggling: an `incorrect` among its last 2 attempts, or `last_tier_change` is a demotion within the last 7 days.
   2. Flagged in teaching: a weak concept with `"source": "teach"` added after `last_quizzed` (or never quizzed).
   3. In progress: quizzed before and not mastered. Lowest tier first; ties go to the oldest `last_quizzed`.
   4. New: never quizzed, in course order.
   5. Review: mastered, with `last_quizzed` more than 14 days ago.
4. **Next up for /teach-me**: the first 3 untaught topics in course order, if any.
5. **Unindexed files:** list the readable files (`.md .txt .tex .py .m .R .jl .ipynb .pdf .docx .pptx`) under the content folders in `config.md` that are missing from the manifest in `topics.md`, or whose modification time (`stat -f '%Sm' -t '%Y-%m-%d %H:%M'`) differs from it. Skip hidden files, build output, LaTeX byproducts, and figure folders. If any are found, suggest re-running `/setup-study-skills`. Omit this section when there are none.
