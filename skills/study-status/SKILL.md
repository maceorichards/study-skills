---
name: study-status
description: Read-only study dashboard for the current course. Shows each topic's tier, points, recent results and weak concepts, what quiz-me and teach-me would pick next, and course files not yet indexed. Takes optional files, folders, topic IDs, or topic names as scope. Use when the user asks "how am I doing", "show my progress", "what's my weakest topic", or "what should I study next".
license: MIT
compatibility: Needs shell access and Python 3.9+. Written for any Agent Skills tool (Claude Code, Codex, Cursor, Copilot, Gemini CLI, OpenCode and others).
argument-hint: "[folder | file | topic-id | \"topic name\" ...]"
---

# study-status

Report study progress. This skill only reads; it never changes anything in `study/`.

Arguments: `$ARGUMENTS`

If the line above is empty or still shows the literal text `$ARGUMENTS`, take the scope from what the user wrote after the skill name, or from their request. No scope means the whole course.

## The helper script

This skill ships `scripts/study.py` (Python 3.9+, standard library only) in its own folder. Run it from the course root (the current working directory) with the path where this skill is installed, for example `python3 .claude/skills/study-status/scripts/study.py <command>` (or `.agents/skills/...`; on Windows use `python` or `py -3` instead of `python3`). Below, `study.py <command>` is short for that full command.

## Steps

1. If `study/config.md` doesn't exist, say the course isn't set up, suggest setup-study-skills, and stop.
2. Run `study.py status <scope tokens...>`. Split the scope on whitespace, keeping quoted strings together. Each token can be a path, a topic ID, or a loose name. If it prints `error: ...`, show the message and stop.
3. Show the output as is, in a code block so the columns line up. It contains:
   - a table per unit: topic ID, tier (`new`, `T1`–`T3`, `M` for mastered), points toward the next tier, dates taught and last quizzed, the last 4 results (`✓` correct, `~` partial, `✗` incorrect, `*` asked at a forced tier), and weak concepts;
   - a summary line;
   - "Next up" for quiz-me and teach-me;
   - any course files not yet indexed.
4. Below it, add at most two sentences: the most useful next step (e.g. "Run quiz-me; week03-inhibition has two recent misses"), and whether to re-run setup-study-skills if unindexed files were listed.
