---
name: mock-exam
description: Exam-style practice test across a scope of course material. Writes N questions (default 10), mostly medium and hard, weighted toward weak topics and styled after past exams. Gives no feedback until the user submits, then grades every answer and updates study progress. Use when the user says "give me a practice exam", "mock midterm", "test me like the real exam", or "exam prep".
license: MIT
compatibility: Needs file read/write and shell access, and Python 3.9+. Written for any Agent Skills tool (Claude Code, Codex, Cursor, Copilot, Gemini CLI, OpenCode and others).
argument-hint: "[N] [folder | file | topic-id | \"topic name\" ...]"
---

# mock-exam

Give the user a practice exam.

Arguments: `$ARGUMENTS`

If the line above is empty or still shows the literal text `$ARGUMENTS`, take the arguments from what the user wrote after the skill name, or from their request (e.g. "15-question practice exam on weeks 1-4" → N = 15, scope the matching folders).

The course root is the current working directory. Study data lives in `study/`.

## The helper script

This skill ships `scripts/study.py` (Python 3.9+, standard library only) in its own folder. Run it from the course root with the path where this skill is installed, for example `python3 .claude/skills/mock-exam/scripts/study.py <command>` (or `.agents/skills/...`; on Windows use `python` or `py -3` instead of `python3`). Below, `study.py <command>` is short for that full command. If it prints `error: ...`, show the message to the user and act on it.

## 1. Load state

1. If `study/config.md` doesn't exist, say the course isn't set up, suggest setup-study-skills, and stop.
2. Read `study/config.md` and `study/topics.md`. Record the start time from `study.py now`.

## 2. Parse the arguments

Split the arguments into tokens on whitespace, keeping quoted strings together. If the first token is a positive integer, it is N, the number of questions; otherwise N = 10. Every other token is scope: a path, a topic ID, or a loose name. No scope means the whole course.

## 3. Choose topics and tiers

1. Run `study.py priority <scope tokens...> --all-mastered`. It ranks every in-scope topic by need, with mastered topics last.
2. Spread N questions across the ranked topics: give each topic one question in rank order, and wrap around for a second pass only if N exceeds the number of topics. At most 2 questions per topic, unless the scope has fewer than N/2 topics.
3. Each question's tier is the topic's tier plus one, kept between T2 and T3. So a T1 topic gets a T2 question, and T2, T3 and mastered topics get T3. (`study.py topics <ID>` shows a topic's tier.)
4. Where a T3 question can naturally join two in-scope topics, do so, and count it toward the first.

## 4. Read the sources

Read every file named in the `Sources:` lines of the chosen topics, plus up to 4 style-reference files: past exams in `style-reference` folders first, then problem-set handouts from `both` folders.
- Read text files (`.md .txt .tex .py .m .R .jl`) with your file-reading tool.
- For `.pdf .docx .pptx .ipynb`, use your file tool if it handles that type; otherwise run `study.py extract "<file>"`. For a PDF longer than 20 pages, add `--pages 1-20`, then `--pages 21-40`, and so on.

## 5. Write the exam

- Questions come from the files. Model their phrasing, length and structure on the style references; multi-part questions are fine if the past exams use them.
- T2 is mechanism and application ("why does...", "what happens if...", single-step prediction). T3 is integration and analysis (multi-step reasoning, combining topics, designing or interpreting an experiment, exam-style problems).
- Follow every bullet under Preferences in `study/config.md`: allowed formats, math style, citations, and course notes on what to test or avoid. Avoid anything close to a topic's `recent_stems` (`study.py topics <ID> --json`).
- Before showing the exam, save it to `study/exams/<YYYY-MM-DD-HHMM>.md` with an answer key. For each question record its number, topic ID, tier, target concept (worded as in `study/topics.md`), the question, and a model answer with its citation. Don't show the key to the user.
- Show all questions at once as a numbered list, without topic or tier labels. Tell the user to answer by number, in one or several messages, and to say "submit" when done. Then stop and wait.

## 6. While the user answers

Acknowledge each message in one line (e.g. `Got 1–4; 6 left.`), with no hints and no grading. If they ask about a question, clarify only what is being asked, never the answer.

## 7. On "submit"

1. Record the end time from `study.py now`. Unanswered questions count as `incorrect`.
2. Grade each answer as `correct`, `partial`, or `incorrect`. For each, show the topic and tier, the grade, a short model answer with its citation, and what was missing or wrong.
3. Record every answer:
   ```
   study.py record --topic <ID> --tier <question tier> --result <result> --concept "<concept>" --stem "<question in at most 15 words>" --source mock-exam
   ```
   The command applies the tier rules. A question above the topic's tier counts toward its current tier, and a miss there doesn't demote. Collect any `promoted` or `demoted` lines it prints.
4. Append the user's answers and the grades to the saved exam file.
5. Print the score (partial counts as half), results by topic, the tier changes, and the weakest concepts. Then suggest quiz-me or teach-me on the topics missed.
6. Append to `study/log.md`:
   ```
   ## 2026-10-19 14:05 — mock-exam — scope: all — 10 questions
   Start: 14:05 · End: 14:52 · Exam: study/exams/2026-10-19-1405.md
   Score: 6.5/10 (3 partial)
   Tier changes: week04-glycolysis T1→T2
   Missed: week03-inhibition: competitive inhibition raises apparent Km but leaves Vmax unchanged
   ```
