"""Verify the built sdist and wheel before they are installed or published.

Usage: ``python scripts/check_dist.py dist`` (run from the repository root).

Checks that the wheel carries every kit template, ``py.typed``, the license and both console
scripts, that the sdist carries the sources a rebuild needs, and that the unofficial notice
is part of the long description shown on PyPI. Standard library only; works on every OS.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PREFIX = "cursorfleet/_templates/cursor/"
REQUIRED_SCRIPTS = ("cursorfleet", "cursorfleet-hook")
SDIST_REQUIRED = ("pyproject.toml", "README.md", "LICENSE", "src/cursorfleet/py.typed")
NOTICE = "not affiliated with or endorsed by"


def fail(problems: list[str]) -> int:
    for problem in problems:
        print(f"FAIL: {problem}", file=sys.stderr)
    return 1


def check_wheel(path: Path) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(path) as wheel:
        names = set(wheel.namelist())
        expected = {
            TEMPLATE_PREFIX + file.relative_to(ROOT / "templates" / "cursor").as_posix()
            for file in (ROOT / "templates" / "cursor").rglob("*")
            if file.is_file()
        }
        missing = sorted(expected - names)
        if not expected:
            problems.append("templates/cursor is empty or missing in the checkout")
        if missing:
            problems.append(f"wheel is missing templates: {missing}")
        for required in ("cursorfleet/py.typed", "cursorfleet/cli/main.py"):
            if required not in names:
                problems.append(f"wheel is missing {required}")
        if not any(n.endswith(".dist-info/licenses/LICENSE") for n in names):
            problems.append("wheel does not carry the LICENSE file")
        entry = next((n for n in names if n.endswith(".dist-info/entry_points.txt")), None)
        text = wheel.read(entry).decode("utf-8") if entry else ""
        problems.extend(
            f"wheel has no {script} console script"
            for script in REQUIRED_SCRIPTS
            if f"{script} = " not in text
        )
        meta_name = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        if meta_name is None:
            problems.append("wheel has no METADATA")
        else:
            message = Parser().parsestr(wheel.read(meta_name).decode("utf-8"))
            body = message.get_payload()
            if NOTICE not in str(body):
                problems.append("long description lacks the unofficial / not-affiliated notice")
            if message.get("Name") != "cursorfleet":
                problems.append(f"unexpected project name {message.get('Name')!r}")
    return problems


def check_sdist(path: Path) -> list[str]:
    problems: list[str] = []
    with tarfile.open(path) as sdist:
        names = {name.split("/", 1)[1] for name in sdist.getnames() if "/" in name}
    problems.extend(f"sdist is missing {item}" for item in SDIST_REQUIRED if item not in names)
    if not any(n.startswith("templates/cursor/") for n in names):
        problems.append("sdist is missing templates/cursor/")
    return problems


def main(argv: list[str]) -> int:
    dist = Path(argv[1]) if len(argv) > 1 else ROOT / "dist"
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        return fail(
            [f"expected exactly one wheel and one sdist in {dist}, found {wheels} {sdists}"]
        )
    problems = check_wheel(wheels[0]) + check_sdist(sdists[0])
    if problems:
        return fail(problems)
    print(f"ok: {wheels[0].name} and {sdists[0].name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
