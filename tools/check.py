#!/usr/bin/env python3
"""Check every skill against the Agent Skills spec (agentskills.io/specification) plus repo rules.

Spec rules: name is 1-64 chars of a-z, 0-9 and single hyphens, and matches its folder; description is
1-1024 chars; compatibility is at most 500 chars; frontmatter keys come from the spec, plus
argument-hint, which Claude Code, VS Code and Copilot CLI use and other tools ignore.
Repo rules: license is set, the body stays under 500 lines, the skill points at scripts/study.py,
and that copy matches src/study.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import sync  # noqa: E402

SPEC_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
EXTRA_KEYS = {"argument-hint"}


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, re.S)
    if not m:
        raise ValueError("missing YAML frontmatter between --- lines")
    fields: dict[str, str] = {}
    key = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if km and not line[0].isspace():
            key = km.group(1)
            val = km.group(2).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1].replace('\\"', '"')
            fields[key] = val
        elif key is not None:
            fields[key] += ("\n" if fields[key] else "") + line.strip()
        else:
            raise ValueError(f"unexpected frontmatter line: {line!r}")
    return fields, m.group(2)


def check_skill(d: Path) -> list[str]:
    problems = []
    skill = d / "SKILL.md"
    try:
        fields, body = frontmatter(skill.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"{d.name}: {e}"]
    for k in fields:
        if k not in SPEC_KEYS | EXTRA_KEYS:
            problems.append(f"{d.name}: frontmatter key {k!r} isn't in the spec (allowed extras: {', '.join(EXTRA_KEYS)})")
    name = fields.get("name", "")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > 64:
        problems.append(f"{d.name}: name {name!r} must be 1-64 chars of a-z, 0-9 and single hyphens")
    if name != d.name:
        problems.append(f"{d.name}: name {name!r} must match its folder name")
    desc = fields.get("description", "")
    if not 1 <= len(desc) <= 1024:
        problems.append(f"{d.name}: description must be 1-1024 chars (is {len(desc)})")
    if len(fields.get("compatibility", "")) > 500:
        problems.append(f"{d.name}: compatibility must be at most 500 chars")
    if not fields.get("license"):
        problems.append(f"{d.name}: license is missing")
    if len(body.splitlines()) >= 500:
        problems.append(f"{d.name}: body is {len(body.splitlines())} lines; keep it under 500")
    if "scripts/study.py" not in body:
        problems.append(f"{d.name}: body never mentions scripts/study.py")
    return problems


def main() -> int:
    skills = sorted(p.parent for p in (REPO / "skills").glob("*/SKILL.md"))
    problems = [p for d in skills for p in check_skill(d)]
    problems += [f"out of sync: {t.relative_to(REPO)} (run python tools/sync.py)" for t in sync.stale()]
    for p in problems:
        print(f"problem: {p}")
    print(f"checked {len(skills)} skill(s): " + ("ok" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
