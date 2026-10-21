#!/usr/bin/env python3
"""Copy src/study.py into every skill's scripts/ folder. Run after editing src/study.py.

  python tools/sync.py           copy
  python tools/sync.py --check   exit 1 if any copy differs (used by tools/check.py and CI)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "src" / "study.py"


def targets() -> list[Path]:
    return sorted(p.parent / "scripts" / "study.py" for p in (REPO / "skills").glob("*/SKILL.md"))


def stale() -> list[Path]:
    src = SOURCE.read_bytes()
    return [t for t in targets() if not t.is_file() or t.read_bytes() != src]


def main(argv: list[str]) -> int:
    if "--check" in argv:
        bad = stale()
        for t in bad:
            print(f"out of sync: {t.relative_to(REPO)} (run python tools/sync.py)")
        return 1 if bad else 0
    src = SOURCE.read_bytes()
    for t in targets():
        t.parent.mkdir(exist_ok=True)
        if not t.is_file() or t.read_bytes() != src:
            t.write_bytes(src)
            print(f"updated {t.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
