---
name: setup-study-skills
description: Set up study tracking for a course. Indexes the course's lectures, notes, readings and problem sets into a topic map and creates the study/ folder (config, topics, progress, log) that teach-me, quiz-me, study-status and mock-exam use. Use when the user says "set up studying for this course", "index my course material", or when new lectures or homeworks have been added. Run once per course, then again whenever material changes.
license: MIT
compatibility: Needs file read/write and shell access, and Python 3.9+. Written for any Agent Skills tool (Claude Code, Codex, Cursor, Copilot, Gemini CLI, OpenCode and others).
argument-hint: "[folder ...]"
---

# setup-study-skills

Set up (or refresh) study tracking for this course.

Arguments: `$ARGUMENTS`

If the line above is empty or still shows the literal text `$ARGUMENTS`, take the arguments from what the user wrote after the skill name, or from their request. Arguments, if any, are content folders or files.

The course root is the current working directory. All paths are relative to it. Study data lives in `study/`.

## The helper script

This skill ships `scripts/study.py` (Python 3.9+, standard library only) in its own folder. Run it from the course root with the path where this skill is installed, for example `python3 .claude/skills/setup-study-skills/scripts/study.py <command>` (or `.agents/skills/...`; on Windows use `python` or `py -3` instead of `python3`). Below, `study.py <command>` is short for that full command. If it prints `error: ...`, show the message to the user and act on it.

## Reading files

- Read text files (`.md .txt .tex .py .m .R .jl`) with your file-reading tool.
- For `.pdf .docx .pptx .ipynb`, use your file tool if it handles that type; otherwise run `study.py extract "<file>"`. For a PDF longer than 20 pages, add `--pages 1-20`, then `--pages 21-40`, and so on (the first output line gives the page count).
- If a file can't be read either way, note it and carry on.

## 1. Pick the mode

- `study/config.md` exists: **re-run mode**. Go to §7.
- Otherwise: **first run**. Continue with §2.

## 2. Propose content folders and preferences (one message, then wait)

1. Folders: if arguments were given, use those. Otherwise run `study.py survey`. It lists the top-level folders and files with how many readable files each holds. Propose the ones that hold course material. Leave out `.claude/`, `.agents/`, `study/`, virtualenvs, build output, and folders with no readable files.
2. Give each folder a role:
   - `material`: topics are extracted from it (lectures, notes, readings, papers).
   - `style-reference`: no topics. Its question style models hard (T3) questions and mock exams (past or practice exams).
   - `both`: topics are extracted, and it is also a style reference (homeworks, problem sets).
3. Units: a unit is the group of files that one set of topics comes from. A content folder is one unit, unless it holds self-contained units (e.g. `lectures/` with one subfolder or file per lecture). In that case each child is a unit. A content entry may also be a single file. Unit names are the folder or file name, lowercased, spaces as `-`, extension dropped.
4. Preferences: propose defaults that fit the material:
   - Question formats allowed, from: short answer, multiple choice, predict-the-result, calculation, derivation, code. (A quantitative course may want calculation and derivation; a conceptual one may not.)
   - Math style: default plain-text math (`v = Vmax * S / (Km + S)`), no LaTeX.
   - Citation style: default `[<file stem>, p.N]` or `[<file stem>, §section]`.
   - Any other notes on what to test or avoid.
5. Show it all in one compact message: a table of folder → role → units, the left-out folders with a one-word reason, and the preference defaults. Ask the user to confirm or edit. Stop and wait for their reply.

## 3. Write the config and list the files

Once confirmed, write `study/config.md`:
```
# Study config: <course folder name>

## Content folders
| Folder | Role | Units |
|---|---|---|
| lectures | material | week01, week02, week03 |
| problem-sets | both | problem-sets |
| exams/practice-midterm.pdf | style-reference | — |

## Preferences
- Question formats: short answer, multiple choice, predict-the-result, calculation
- Math: plain text, no LaTeX
- Citations: [<file stem>, p.N]
- Notes: <free text or none>
```
Every skill applies every bullet under Preferences, so the user can add more bullets later.

Then run `study.py scan <folder>` for each content folder. It lists the readable files with their modification times, skipping hidden files, build output, figure folders, LaTeX byproducts, and PDFs compiled from a `.tex` in the same folder.

## 4. Extract topics

For each unit of a `material` or `both` folder, produce draft topics. If you can run subagents or parallel workers, give each unit to one subagent, all in parallel, passing absolute file paths (never pasted content) and the brief below. Otherwise do the units yourself one at a time. Write each unit's draft to `study/.drafts/<unit>.md` as soon as it's done, so earlier units aren't lost if your context fills up.

The brief for each unit:

> Read every file below fully. Use your file tool for text files. For .pdf .docx .pptx .ipynb that your tool can't read, run `<full study.py command> extract "<file>"`, adding `--pages 1-20`, `--pages 21-40`... for long PDFs.
>
> Split the unit's content into topics: coherent sections of the material, usually 3–8 per lecture-sized unit. For a problem set, topics are the ideas its problems exercise (e.g. "Michaelis-Menten kinetics"), not "Problem 1". For each topic give:
> - a short kebab-case slug (2–4 words) and a title;
> - sources: file paths relative to the course root, each in backticks, with pages or sections;
> - 3–8 concepts: specific, testable statements of what someone who knows this topic can explain, predict, or compute.
>
> Return plain text in this shape, topics in the order they appear in the material:
> ```
> ### <slug> — <title>
> Sources: `<path>` p.2-4; `<path>` §1.2
> Concepts:
> - <concept>
> ```
> End with a line `Unreadable: <files>` (or `Unreadable: none`).

Then merge: put units in course order (chronological where names are dates, otherwise the order a student would meet them). Drop topics duplicated across units, keeping the first and adding the other's sources. Form IDs as `<unit>-<slug>`. IDs must be unique, lowercase, and stable; add a suffix if needed.

## 5. Review the topic map (then wait)

Show only the draft titles, grouped by unit, as `<ID> — <title>`, plus the topic count and any unreadable files. Ask the user to merge, split, rename, or drop topics, or to say "looks good". Stop and wait. Apply the edits, and repeat until they approve.

## 6. Write the study files

1. Write `study/topics.md`, units in course order and topics in material order. This order is "course order" for every skill.
   ```
   # Topics: <course folder name>

   ## Unit: week03 (lectures/week03/)

   ### week03-enzyme-kinetics — Michaelis-Menten enzyme kinetics
   Sources: `lectures/week03/slides.pdf` p.4-9; `lectures/week03/notes.md` §2
   Concepts:
   - Km is the substrate concentration at which the rate is half of Vmax
   ```
2. Run `study.py manifest --write`. It appends a `## Manifest` table of every content file and its modification time. Later runs use it to detect changes.
3. Run `study.py init-progress`. It creates `study/progress.json` with a fresh record (tier 1) for every topic.
4. Run `study.py validate` and fix anything it reports in `topics.md`.
5. Write `study/log.md`, using the time from `study.py now`:
   ```
   # Study log

   ## 2026-10-19 14:05 — setup
   Units: 7 · Topics: 31 · Style references: problem-sets, exams
   ```
6. Delete `study/.drafts/`.

Finish with a short summary: topics per unit, where the files are, and the next steps. Those are teach-me to learn untaught topics, quiz-me to start tiered quizzing, and study-status to see progress. Mention that `config.md` and `topics.md` can be edited by hand.

## 7. Re-run mode

1. Read `study/config.md` and `study/topics.md`. Keep the saved preferences; the user can edit `config.md` or ask to change them.
2. If the arguments name folders or files not yet in the config, propose roles and units for them as in §2, and wait for confirmation. Then add them to the config table.
3. Run `study.py diff-manifest`. It lists new, modified and deleted content files. If nothing changed and no folder was added, say so and stop.
4. For each unit with new or modified files in a `material` or `both` folder, extract topics as in §4. Add to the brief the unit's existing topic titles and concepts, and ask only for topics not yet covered, plus concepts or sources to add to existing topics. Changes to style-reference files need no extraction.
5. Show the proposed additions (new IDs and titles, additions to existing topics) and wait for approval, as in §5.
6. Apply them: add the new topics within their unit in `topics.md`, and apply the additions to existing topics. Never rename, renumber, or delete an existing topic ID. For deleted files, keep their topics and list them in the summary so the user can prune `topics.md` by hand.
7. Run `study.py manifest --write`, then `study.py init-progress` (it adds records only for new topics and never resets existing progress), then `study.py validate`.
8. Append a `setup (refresh)` entry to `study/log.md` with the counts of added topics, delete `study/.drafts/`, and summarize.
