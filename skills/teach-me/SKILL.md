---
name: teach-me
description: Socratic, chunked tutoring on course material, one concept at a time with a check question after each. Takes files, folders, topic IDs, or topic names; with no arguments it offers the next untaught topic. Records taught topics and trouble spots when the course is set up. Use when the user says "teach me", "explain this lecture", "walk me through <topic>", or "help me learn <topic>".
license: MIT
compatibility: Needs file read/write and shell access, and Python 3.9+. Written for any Agent Skills tool (Claude Code, Codex, Cursor, Copilot, Gemini CLI, OpenCode and others).
argument-hint: "[folder | file | topic-id | \"topic name\" ...]"
---

# teach-me

Teach the material in scope interactively.

Arguments: `$ARGUMENTS`

If the line above is empty or still shows the literal text `$ARGUMENTS`, take the arguments from what the user wrote after the skill name, or from their request (e.g. "teach me enzyme kinetics" → scope `enzyme kinetics`).

The course root is the current working directory. If the course is set up, study data lives in `study/` (created by setup-study-skills).

## The helper script

This skill ships `scripts/study.py` (Python 3.9+, standard library only) in its own folder. Run it from the course root with the path where this skill is installed, for example `python3 .claude/skills/teach-me/scripts/study.py <command>` (or `.agents/skills/...`; on Windows use `python` or `py -3` instead of `python3`). Below, `study.py <command>` is short for that full command. If it prints `error: ...`, show the message to the user and act on it.

## 1. Pick the mode

- `study/config.md` exists: **tracked mode**. Read `study/config.md` and `study/topics.md`.
- Otherwise: **untracked mode**. Teach straight from the paths given, and record nothing. If there are no arguments, ask which file or folder to teach, then stop and wait. Mention once that setup-study-skills turns on progress tracking.

## 2. Resolve the scope

Split the arguments into tokens on whitespace, keeping quoted strings together, since filenames contain spaces.

Tracked mode:
- With arguments, run `study.py topics <tokens...>`. Each token can be a path (it selects the topics drawn from files under it), a topic ID, or a loose name matched against topic titles and concepts. The command prints the matching topics in course order, plus `note:` lines.
  - If a note says a name matched several topics and the user clearly meant one, ask which. Stop and wait.
  - If a note says files under a path aren't indexed, teach those files straight from the file as well, and suggest re-running setup-study-skills.
- With no arguments, run `study.py topics --untaught` and offer the first 5 as `<ID> — <title>`. Ask whether to start with the first or pick another. Stop and wait. If every topic is taught, offer the topics with the most weak concepts instead (see `study.py status`).

Untracked mode: each token must be an existing file or folder (a folder means every file in it, recursively, skipping hidden files). If one doesn't exist, say which and stop.

## 3. Read the sources

In tracked mode, read every file named in the `Sources:` lines of the selected topics in `study/topics.md`. In untracked mode, read every file in scope. Read them fully:
- Read text files (`.md .txt .tex .py .m .R .jl`) with your file-reading tool.
- For `.pdf .docx .pptx .ipynb`, use your file tool if it handles that type; otherwise run `study.py extract "<file>"`. For a PDF longer than 20 pages, add `--pages 1-20`, then `--pages 21-40`, and so on.
- Skip anything unreadable, and list it as skipped.

Print one short line: the topics in scope (or the files loaded), plus any skipped files.

## 4. Style rules

- Teach from the files. Outside intuition or analogies are fine only when marked "(beyond the course material)".
- In tracked mode, follow every bullet under Preferences in `study/config.md`: question formats, math style, citations, and any course notes, including those that limit what check questions may ask. Without a config, use plain-text math (`v = Vmax * S / (Km + S)`), no LaTeX, and cite as `[<file stem>, p.N]`.
- Output is read in a terminal or chat pane. Be concise; minimal bold, few bullets.
- Cite the file each point comes from.

## 5. Teaching loop

1. Open with a short numbered list of the topics in scope, in course order. Teach in that order unless the user picks a topic. In untracked mode, derive the topics from the files.
2. Work through one topic at a time. In tracked mode, the topic's concepts in `study/topics.md` are what it must cover.
3. Each chunk: explain one concept in a few sentences (plus the key equation if there is one), then ask exactly one check question. Then stop and wait for the user's answer. Never answer your own question in the same message.
4. On the answer:
   - Correct: confirm briefly, add any nuance the files give, and move on to the next concept.
   - Partial or wrong: name the specific gap, re-explain from a different angle or ask a leading sub-question, and re-check before moving on. This concept is a trouble spot.
5. Favor questions that test mechanism and prediction ("what happens if...", "why does...") over recalling definitions, unless the course preferences say otherwise.
6. The user may say "skip", "go deeper", "next topic", or "stop" at any time; follow it.

## 6. Record progress (tracked mode only)

Record as you go, so nothing is lost if the session ends early:
- **Trouble spot:** `study.py add-weak --topic <ID> --concept "<concept>"`. Use the concept's wording from `study/topics.md` when it matches one.
- **Topic finished:** once all of a topic's concepts are covered (skipped ones count as covered), run `study.py mark-taught --topic <ID>`. A topic cut off by "stop" partway through stays untaught, but its trouble spots are kept.

Teaching never changes tiers; only quizzes do.

## 7. On stop

When the user says "stop" or every topic in scope is done:
1. Give a 3–5 line recap of what was covered and which concepts gave trouble.
2. In tracked mode, append to `study/log.md`, using the time from `study.py now`:
   ```
   ## 2026-10-19 14:05 — teach — scope: week03
   Taught: week03-enzyme-kinetics, week03-inhibition
   Trouble: week03-inhibition: competitive inhibition raises apparent Km but leaves Vmax unchanged
   ```
   Write `Trouble: none` if nothing gave trouble.
3. Suggest quiz-me on the same scope.
