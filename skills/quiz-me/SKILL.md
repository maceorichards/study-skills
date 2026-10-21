---
name: quiz-me
description: Tiered, adaptive quiz on course material, one question at a time. Uses the study progress log to focus on the topics that need the most help, asks each topic at its tier (easy, then medium, then hard, then mastered), and updates progress after every answer. Takes an optional tier and files, folders, topic IDs, or topic names as scope. Use when the user says "quiz me", "test me", "what should I study", or "drill me on <topic>".
license: MIT
compatibility: Needs file read/write and shell access, and Python 3.9+. Written for any Agent Skills tool (Claude Code, Codex, Cursor, Copilot, Gemini CLI, OpenCode and others).
argument-hint: "[--tier 1|2|3|easy|medium|hard] [folder | file | topic-id | \"topic name\" ...]"
---

# quiz-me

Quiz the user on course material, focusing where they need the most help.

Arguments: `$ARGUMENTS`

If the line above is empty or still shows the literal text `$ARGUMENTS`, take the arguments from what the user wrote after the skill name, or from their request (e.g. "quiz me on enzyme kinetics, hard questions" → scope `enzyme kinetics`, `--tier 3`).

The course root is the current working directory. Study data lives in `study/`.

## The helper script

This skill ships `scripts/study.py` (Python 3.9+, standard library only) in its own folder. Run it from the course root with the path where this skill is installed, for example `python3 .claude/skills/quiz-me/scripts/study.py <command>` (or `.agents/skills/...`; on Windows use `python` or `py -3` instead of `python3`). Below, `study.py <command>` is short for that full command. If it prints `error: ...`, show the message to the user and act on it.

## 1. Load state

1. If `study/config.md` doesn't exist, say the course isn't set up, suggest setup-study-skills, and stop.
2. Read `study/config.md` and `study/topics.md`.

## 2. Parse the arguments

Split the arguments into tokens on whitespace, keeping quoted strings together.
- `--tier N` (or `--tier=N`), where N is `1|2|3` or `easy|medium|hard`, sets the **forced tier**: every question is written at that tier. Topic choice still follows priority.
- Every other token is scope: a path (topics drawn from files under it), a topic ID, or a loose name matched against topic titles and concepts. No scope means the whole course.

## 3. Pick the working set

Run `study.py priority <scope tokens...>`. It ranks the in-scope topics by need, each with a bucket and a reason:
1. struggling: a miss in the last 2 answers, or recently demoted;
2. flagged in teaching: weak concepts from teach-me not quizzed since;
3. in progress: lowest tier first, then the longest since quizzed;
4. new: never quizzed, in course order;
5. review: mastered topics last quizzed over 14 days ago.

Mastered topics reviewed in the last 14 days are left out. Show any `note:` lines it prints. If it reports nothing due, say so and offer a review anyway (`--tier 3` on mastered topics) or a different scope.

Take the top 4 as the **working set** (fewer if the scope is smaller). Print one plan line, e.g.:

`Focusing on: week03-inhibition (T1, missed 1 of last 2), week02-buffers (T2, weak from teaching), week04-glycolysis (new), week01-ph (T2)`

Add `Forced tier: T2` when the tier is forced.

## 4. Read the sources

Read every file named in the `Sources:` lines of the working-set topics. When a topic joins the working set later, read its sources then. For T3 questions, also read up to 3 style-reference files to model question style: past exams from `style-reference` folders first, then problem-set handouts from `both` folders, choosing those closest to the topic.
- Read text files (`.md .txt .tex .py .m .R .jl`) with your file-reading tool.
- For `.pdf .docx .pptx .ipynb`, use your file tool if it handles that type; otherwise run `study.py extract "<file>"`. For a PDF longer than 20 pages, add `--pages 1-20`, then `--pages 21-40`, and so on.

## 5. Style rules

- Questions and answers come from the files. Explanations may add intuition only when marked "(beyond the course material)".
- Follow every bullet under Preferences in `study/config.md`: allowed question formats, math style, citations, and any course notes on what to test or avoid. These override the defaults below.
- Output is read in a terminal or chat pane. Be concise; minimal bold, few bullets.
- Cite the source of each answer.

## 6. Tiers

Each question is written at the topic's current tier, or at the forced tier. A mastered topic is asked at T3.
- **T1 Easy (recall and recognition):** state or recognize a concept, identify a mechanism or term, straightforward multiple choice.
- **T2 Medium (mechanism and application):** "why does..." and "what happens if..." questions, single-step predictions, short applications.
- **T3 Hard (integration and analysis):** multi-step reasoning, joining this topic with another in scope, designing or interpreting an experiment, exam-style problems modeled on the style references.

Use only the formats the preferences allow. If none of a tier's natural formats is allowed, ask a short-answer question at that tier's depth. Multiple choice has four options labeled A–D with plausible distractors; the user answers in text. Label each question with its topic and tier, e.g. `Q3 [week02-buffers · T2]`.

## 7. Quiz loop

1. Ask exactly one question, then stop and wait for the user's answer. Never reveal the answer before they respond.
2. Interleave: rotate through the working set, never asking the same topic twice in a row while others remain. Struggling topics come up about twice as often as the rest.
3. Aim each question at one concept of the topic: its weak concepts first (from `study.py topics <ID> --json`, field `weak_concepts`), then concepts not tested recently. Don't repeat a question from this session, or anything close to the topic's `recent_stems`.
4. Grade the answer as `correct`, `partial`, or `incorrect`. Give a short explanation of the right answer with its citation, and point out what was missing or wrong in theirs. A "skip" counts as `incorrect`; give the answer and move on.
5. Record it right away:
   ```
   study.py record --topic <ID> --tier <question tier> --result <correct|partial|incorrect> --concept "<concept>" --stem "<question in at most 15 words>" [--forced]
   ```
   Add `--forced` when the tier was forced. Use the concept's wording from `study/topics.md` or the weak list, so weak concepts clear when answered correctly. The command applies the tier rules and prints one line. If it says `promoted` or `demoted`, tell the user in one line, e.g. `week02-buffers: T2 → T3`. For reference, the rules are:
   - correct = 1 point, partial = 0.5;
   - 3 points promote T1 → T2 → T3 → mastered;
   - 2 misses in a row demote one tier, never below T1;
   - a miss on a mastered topic drops it to T3;
   - with a forced tier above the topic's tier, points count toward its current tier and misses don't demote;
   - a forced tier below the topic's tier is only logged.
6. After a miss (`partial` or `incorrect`), ask a differently worded question on the same concept 3–5 questions later.
7. When a topic is promoted, or a mastered topic is answered correctly once (its review is done), it leaves the working set. Refill from the next topic in `study.py priority <scope>` that hasn't been in the set, and read its sources.
8. Keep a running tally (correct / partial / incorrect) and a list of missed concepts.
9. Continue until the user says "stop" (or "done", "quit").

## 8. On stop

1. Print the score (partial counts as half), the tier changes, and the missed concepts. Suggest teach-me on any topic missed more than once this session.
2. Append to `study/log.md`, using the time from `study.py now`:
   ```
   ## 2026-10-19 14:05 — quiz — scope: all (forced tier: none)
   Score: 7/10 (2 partial)
   Tier changes: week04-glycolysis T1→T2; week03-inhibition T2→T1
   Missed: week03-inhibition: competitive inhibition raises apparent Km but leaves Vmax unchanged
   ```
   Write `Tier changes: none` or `Missed: none` when empty.
