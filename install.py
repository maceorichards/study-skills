#!/usr/bin/env python3
"""Install the study skills into course folders (never into your home directory).

  python install.py COURSE_DIR [COURSE_DIR ...] [--tools claude,cursor] [--link] [--force]
  python install.py --update            re-install into every course installed before
  python install.py --list              show installed courses
  python install.py --uninstall COURSE_DIR [COURSE_DIR ...]

Skills are copied (or with --link, symlinked; junctions on Windows) into the fewest
project skill folders that cover the tools you use, e.g. <course>/.claude/skills.
Courses are recorded in installed.json next to this script. Your study/ data is never touched.
Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
SKILLS = REPO / "skills"
REGISTRY = REPO / "installed.json"
MARKER = ".study-skills-install.json"
DEFAULT_TOOLS = ["claude", "cursor"]

# Project-level skill folders each tool reads (from each tool's docs, Oct 2026).
TOOL_DIRS = {
    "claude": [".claude/skills"],
    "codex": [".agents/skills"],
    "gemini": [".agents/skills", ".gemini/skills"],
    "antigravity": [".agents/skills"],
    "copilot": [".claude/skills", ".agents/skills", ".github/skills"],
    "cursor": [".claude/skills", ".agents/skills", ".cursor/skills"],
    "opencode": [".claude/skills", ".agents/skills", ".opencode/skills"],
    "goose": [".claude/skills", ".agents/skills", ".goose/skills"],
    "amp": [".claude/skills", ".agents/skills"],
    "windsurf": [".agents/skills", ".windsurf/skills", ".devin/skills"],
    "cline": [".claude/skills", ".agents/skills", ".cline/skills"],
    "roo": [".agents/skills", ".roo/skills"],
}
PREFERRED = [".claude/skills", ".agents/skills"]


class InstallError(Exception):
    pass


def skill_names() -> list[str]:
    return sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def version() -> str:
    try:
        rev = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "skills"],
                               capture_output=True, text=True).stdout.strip()
        return rev + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def parse_tools(spec: str) -> list[str]:
    tools = [t.strip().lower() for t in spec.split(",") if t.strip()]
    unknown = [t for t in tools if t not in TOOL_DIRS]
    if unknown or not tools:
        raise InstallError(f"unknown tool(s): {', '.join(unknown) or '(none given)'}; "
                           f"known: {', '.join(sorted(TOOL_DIRS))}")
    return tools


def dirs_for(tools: list[str]) -> list[str]:
    """Fewest skill folders such that every tool reads at least one of them."""
    candidates = sorted({d for t in tools for d in TOOL_DIRS[t]},
                        key=lambda d: (PREFERRED.index(d) if d in PREFERRED else len(PREFERRED), d))
    for size in range(1, len(candidates) + 1):
        for combo in itertools.combinations(candidates, size):
            if all(any(d in combo for d in TOOL_DIRS[t]) for t in tools):
                return list(combo)
    raise InstallError("no folder set covers these tools")  # unreachable


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {"courses": {}}


def save_registry(reg: dict) -> None:
    REGISTRY.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")


def _is_junction(p: Path) -> bool:
    fn = getattr(os.path, "isjunction", None)
    if fn is not None:
        return fn(p)
    try:
        return bool(os.lstat(p).st_file_attributes & 0x400) and not p.is_symlink()  # reparse point
    except (AttributeError, OSError):
        return False


def _link_target(p: Path) -> Path | None:
    if p.is_symlink() or _is_junction(p):
        try:
            return Path(os.path.realpath(p))
        except OSError:
            return None
    return None


def owned(dest: Path) -> bool:
    """True if dest is a skill folder this installer created."""
    target = _link_target(dest)
    if target is not None:
        return target.parent == SKILLS.resolve()
    return (dest / MARKER).is_file()


def _rmtree_onerror(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove(dest: Path) -> None:
    if dest.is_symlink():
        dest.unlink()
    elif _is_junction(dest):
        os.rmdir(dest)
    elif dest.exists():
        shutil.rmtree(dest, onerror=_rmtree_onerror)


def make_link(src: Path, dest: Path) -> None:
    try:
        os.symlink(src, dest, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(dest), str(src)], capture_output=True, text=True)
        if r.returncode != 0:
            raise InstallError(f"could not link {dest}: {r.stderr.strip() or r.stdout.strip()}; try without --link")


def install_course(course: Path, tools: list[str], link: bool, force: bool, reg: dict) -> list[str]:
    if not course.is_dir():
        raise InstallError(f"not a folder: {course}")
    if course.resolve() == Path.home().resolve():
        raise InstallError("refusing to install into your home folder; give a course folder")
    if course.resolve() == REPO or REPO in course.resolve().parents:
        raise InstallError("give a course folder, not the study-skills repo itself")
    names = skill_names()
    dirs = dirs_for(tools)
    prev = reg["courses"].get(str(course.resolve()), {})
    conflicts = [course / d / n for d in dirs for n in names
                 if (course / d / n).exists() or (course / d / n).is_symlink()]
    conflicts = [c for c in conflicts if not owned(c)]
    if conflicts and not force:
        raise InstallError("these skill folders already exist and weren't installed by this script:\n  "
                           + "\n  ".join(str(c) for c in conflicts)
                           + "\nre-run with --force to replace them")
    lines = []
    ver = version()
    for d in dirs:
        base = course / d
        base.mkdir(parents=True, exist_ok=True)
        for n in names:
            dest = base / n
            if dest.exists() or dest.is_symlink():
                remove(dest)
            if link:
                make_link(SKILLS / n, dest)
            else:
                shutil.copytree(SKILLS / n, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
                (dest / MARKER).write_text(json.dumps({"source": str(REPO), "version": ver,
                                                       "installed": dt.datetime.now().isoformat(timespec="minutes")},
                                                      indent=2) + "\n", encoding="utf-8")
        lines.append(f"  {base}: {', '.join(names)} ({'linked' if link else 'copied'})")
    for d in prev.get("dirs", []):
        if d not in dirs:
            removed = _remove_owned(course / d, names)
            if removed:
                lines.append(f"  {course / d}: removed (no longer needed for {', '.join(tools)})")
    reg["courses"][str(course.resolve())] = {"tools": tools, "dirs": dirs, "mode": "link" if link else "copy",
                                             "version": ver,
                                             "installed": dt.datetime.now().isoformat(timespec="minutes")}
    return lines


def _remove_owned(base: Path, names: list[str]) -> list[str]:
    removed = []
    for n in names:
        dest = base / n
        if (dest.exists() or dest.is_symlink()) and owned(dest):
            remove(dest)
            removed.append(n)
    for p in (base, base.parent):  # tidy up folders we left empty
        try:
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except OSError:
            pass
    return removed


def uninstall_course(course: Path, reg: dict) -> list[str]:
    key = str(course.resolve())
    names = skill_names()
    dirs = reg["courses"].get(key, {}).get("dirs") or sorted({d for ds in TOOL_DIRS.values() for d in ds})
    lines = []
    for d in dirs:
        removed = _remove_owned(course / d, names)
        if removed:
            lines.append(f"  {course / d}: removed {', '.join(removed)}")
    reg["courses"].pop(key, None)
    return lines or ["  nothing installed there"]


def ask_tools(course: Path) -> list[str]:
    known = ", ".join(sorted(TOOL_DIRS))
    if not sys.stdin.isatty():
        print(f"{course}: no --tools given; using {','.join(DEFAULT_TOOLS)}")
        return list(DEFAULT_TOOLS)
    while True:
        ans = input(f"Which tools will you use in {course.name}? ({known})\n[{','.join(DEFAULT_TOOLS)}]: ").strip()
        try:
            return parse_tools(ans) if ans else list(DEFAULT_TOOLS)
        except InstallError as e:
            print(e)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="install.py", description="Install the study skills into course folders.",
                                 epilog=f"tools: {', '.join(sorted(TOOL_DIRS))}")
    ap.add_argument("courses", nargs="*", metavar="COURSE_DIR", help="course folder(s) to install into")
    ap.add_argument("--tools", help=f"comma-separated tools you use (default asks, or {','.join(DEFAULT_TOOLS)})")
    ap.add_argument("--link", action="store_true", help="symlink to this repo instead of copying")
    ap.add_argument("--force", action="store_true", help="replace same-named skill folders this script didn't install")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true", help="re-install into every recorded course")
    mode.add_argument("--list", action="store_true", help="list recorded courses")
    mode.add_argument("--uninstall", action="store_true", help="remove the skills from the given course(s)")
    args = ap.parse_args(argv)

    try:
        reg = load_registry()
        if args.list:
            if not reg["courses"]:
                print("no courses installed yet; run: python install.py <course-dir>")
            cur = version()
            for path, info in sorted(reg["courses"].items()):
                stale = "" if info.get("mode") == "link" or info.get("version") == cur else f" (out of date: {info.get('version')}; run --update)"
                gone = "" if Path(path).is_dir() else " (folder missing)"
                print(f"{path}\n  tools: {', '.join(info['tools'])} · folders: {', '.join(info['dirs'])} · "
                      f"{info['mode']} · version {info.get('version')}{stale}{gone}")
            return 0
        if args.update:
            if args.courses:
                raise InstallError("--update takes no course folders; it updates every recorded course")
            if not reg["courses"]:
                raise InstallError("no courses recorded yet; run: python install.py <course-dir>")
            for path, info in sorted(reg["courses"].items()):
                course = Path(path)
                if not course.is_dir():
                    print(f"skipped {path}: folder missing (remove it with --uninstall)")
                    continue
                print(f"{path}")
                print("\n".join(install_course(course, info["tools"], info["mode"] == "link", False, reg)))
            save_registry(reg)
            return 0
        if not args.courses:
            ap.print_usage(sys.stderr)
            print("install.py: error: specify at least one course directory, "
                  "e.g. python install.py ~/Courses/BIO101 (or use --list / --update)", file=sys.stderr)
            return 2
        courses = [Path(c).expanduser() for c in args.courses]
        if args.uninstall:
            for course in courses:
                print(course)
                print("\n".join(uninstall_course(course, reg)))
            save_registry(reg)
            return 0
        for course in courses:
            known = reg["courses"].get(str(course.resolve()), {})
            tools = parse_tools(args.tools) if args.tools else known.get("tools") or ask_tools(course)
            print(course)
            print("\n".join(install_course(course, tools, args.link, args.force, reg)))
            save_registry(reg)
        print("Done. Open your agent in the course folder and run setup-study-skills (e.g. /setup-study-skills).")
        return 0
    except InstallError as e:
        print(f"install.py: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
