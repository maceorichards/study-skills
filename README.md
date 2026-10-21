# study-skills

Agent Skills for studying course material with an AI coding agent. Point them at a course folder of lectures, notes, readings and problem sets. They build a topic map, teach you topic by topic, quiz you in tiers from easy to hard, and keep a progress log, so each quiz targets where you need the most help.

They use the open [Agent Skills](https://agentskills.io) format (a folder with a `SKILL.md`), so they work in Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI, OpenCode and other tools that support it, with whichever model you use there.

| Skill | What it does |
|---|---|
| `setup-study-skills` | Indexes the course's material into topics and creates `study/`. Re-run it when new material arrives. |
| `teach-me` | Socratic tutoring, one concept at a time with a check question. With no arguments, it offers the next untaught topic. |
| `quiz-me` | One question at a time, focused on your weakest topics, at each topic's tier. Updates progress after every answer. |
| `study-status` | Dashboard of tiers, recent results, weak concepts, and what to study next. |
| `mock-exam` | N exam-style questions with no feedback until you submit, then grading and progress updates. |

## How progress works

Every topic starts at **T1 (easy: recall and recognition)** and moves up to **T2 (medium: mechanism and application)**, then **T3 (hard: integration and analysis)**, then **mastered**.

- **Points:** a correct answer is worth 1 point and a partial answer 0.5. Three points at a tier promote the topic.
- **Demotion:** two misses in a row drop the topic one tier. A miss on a mastered topic drops it to T3.
- **Forced tier:** `quiz-me --tier 3` asks harder questions without letting a topic skip tiers.

`quiz-me` picks topics in this order:
1. Topics with recent misses or a recent demotion.
2. Topics with trouble spots from `teach-me`.
3. Topics in progress, lowest tier first.
4. New topics.
5. Mastered topics not reviewed in 14 days.

## Requirements

- An agent that supports Agent Skills and can read files and run shell commands.
- Python 3.9 or newer, run as `python3`, or as `python` or `py -3` on Windows. Standard library only.
- PDFs: on macOS nothing extra is needed. On Linux and Windows, install `pypdf` (`python -m pip install pypdf`) or `pdftotext` (poppler), unless your agent reads PDFs itself.

## Install

The skills go into each course folder, never into your home directory. Clone the repo once, anywhere:

```bash
git clone https://github.com/maceorichards/study-skills.git
```

Then install into a course:

```bash
python study-skills/install.py ~/Courses/BIO101 --tools claude,cursor
```

`--tools` lists the agents you use in that course. The installer writes the fewest skill folders that cover them:
- `.claude/skills` is read by Claude Code, Cursor, Copilot, OpenCode, Goose, Amp and Cline.
- `.agents/skills` is read by Codex, Gemini CLI, Antigravity, Roo, Windsurf and most others.

Leave out `--tools` and it asks. Known tools: `amp antigravity claude cline codex copilot cursor gemini goose opencode roo windsurf`.

Other commands:

```bash
python study-skills/install.py --list                  # courses installed into
python study-skills/install.py --update                # after git pull: refresh every course
python study-skills/install.py --uninstall ~/Courses/BIO101
```

More options:
- **Links instead of copies:** skills are copied by default. Add `--link` to symlink them to the clone instead (junctions on Windows), so a `git pull` updates every course at once.
- **Existing folders:** the installer won't overwrite a skill folder it didn't create unless you pass `--force`.
- **Your data:** it never touches your `study/` data.

GitHub CLI users can also run `gh skill install maceorichards/study-skills --scope project` from inside a course folder.

## Use

Open your agent **in the course folder** and run setup first:

| Tool | Invoke a skill |
|---|---|
| Claude Code, Cursor, Copilot (CLI and VS Code), Cline, Antigravity | `/setup-study-skills`, `/quiz-me --tier 2 week03`, `/teach-me "enzyme kinetics"` |
| Codex | `$quiz-me week03`, or pick it from `/skills` |
| Gemini CLI, OpenCode, Goose, Roo, Windsurf, others | Ask in plain words, e.g. "quiz me on week 3" or "set up study skills for this course" |

Scope arguments can be paths (`lectures/week03`), topic IDs (`week03-enzyme-kinetics`), or loose names (`"enzyme kinetics"`). Run `/study-status` any time to see where you stand.

## What's in `study/`

| File | Contents |
|---|---|
| `config.md` | Content folders and their roles, plus your preferences: question formats, math and citation style, and anything to test or avoid. Edit it freely; every skill applies every bullet. |
| `topics.md` | The topic map: IDs, titles, sources and concepts, plus a manifest of indexed files. Safe to edit by hand, but don't rename IDs that already have progress. |
| `progress.json` | Per-topic tier, points, attempts and weak concepts, one topic per line. Written by `scripts/study.py`. |
| `log.md` | Every setup, teaching, quiz and exam session. |
| `exams/` | Saved mock exams with answer keys and your graded answers. |

## Tested with

Hands-on testing so far: **Claude Code** and **Cursor CLI** on macOS. CI runs the helper and installer tests on macOS, Linux and Windows. The other tools listed are expected to work from their documented Agent Skills support, but haven't been tried. Reports are welcome.

## Development

- `src/study.py` is the helper script. Edit it there, then run `python tools/sync.py` to copy it into every `skills/*/scripts/`.
- `python tools/check.py` validates the skills against the Agent Skills spec and confirms the copies match.
- `python -m unittest discover -s tests` runs the tests.

## License

MIT
