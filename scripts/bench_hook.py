"""Cold-start latency benchmark for the ``cursorfleet-hook`` hot path.

    uv run python scripts/bench_hook.py [-n 100] [--out docs/hook-latency.json]

Every sample is a FRESH interpreter process (Cursor spawns one per hook call), with a
real payload on stdin, running inside a throwaway git repo, so the numbers include
process spawn, imports, repo discovery, normalization, the spool append and exit. They do
NOT include Cursor's own spawn/IPC overhead. Nothing here is asserted against a budget
(timings are machine dependent): results are recorded in ``docs/hook-latency.md``.

Variants:
  floor            ``python -c pass`` in the venv (interpreter + site + .pth floor)
  console_script   the installed ``cursorfleet-hook`` entry point (what hooks.json runs)
  module           ``python -c "from ...hook_main import main; main()"``
  isolated         ``python -I -S`` with src on sys.path (no site-packages/.pth processing)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DOC_DIR = ROOT / "spike" / "doc_examples"
SRC = ROOT / "src"
HOOKS = ("sessionStart", "preToolUse", "postToolUse")
RUN_MAIN = "from cursorfleet.adapters.cursor.hook_main import main; main()"
ISOLATED_MAIN = f"import sys; sys.path.insert(0, {str(SRC)!r}); {RUN_MAIN}"


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize(samples: list[float]) -> dict[str, float]:
    return {
        "n": len(samples),
        "first_ms": round(samples[0], 2),
        "min_ms": round(min(samples), 2),
        "p50_ms": round(percentile(samples, 0.50), 2),
        "p95_ms": round(percentile(samples, 0.95), 2),
        "max_ms": round(max(samples), 2),
        "mean_ms": round(statistics.fmean(samples), 2),
    }


def make_repo(parent: Path) -> Path:
    repo = parent / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    for args in (
        ["init", "-q"],
        [
            "-c",
            "user.name=b",
            "-c",
            "user.email=b@x.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "init",
        ],
    ):
        git_argv = ["git", *args]
        subprocess.run(  # noqa: S603
            git_argv, cwd=repo, env=env, check=True, timeout=60, capture_output=True
        )
    return repo.resolve()


def payload_for(hook: str, repo: Path) -> bytes:
    data: dict[str, Any] = json.loads((DOC_DIR / f"{hook}.doc-derived.json").read_text("utf-8"))
    data.pop("_doc_derived_not_captured", None)
    data["workspace_roots"] = [str(repo)]
    return json.dumps(data).encode()


def sample(argv: list[str], payload: bytes, cwd: Path, env: dict[str, str], n: int) -> list[float]:
    walls: list[float] = []
    for _ in range(n):
        start = time.perf_counter()
        done = subprocess.run(  # noqa: S603 - argv list built above, no shell
            argv, input=payload, cwd=cwd, env=env, capture_output=True, timeout=60, check=False
        )
        walls.append((time.perf_counter() - start) * 1000.0)
        if done.returncode != 0:
            msg = f"variant failed: {argv!r} rc={done.returncode}"
            raise SystemExit(msg)
    return walls


def run(n: int) -> dict[str, Any]:
    python = sys.executable
    script = shutil.which("cursorfleet-hook", path=str(Path(python).parent))
    tmp = Path(tempfile.mkdtemp(prefix="cf-bench-"))
    try:
        repo = make_repo(tmp)
        env = {k: v for k, v in os.environ.items() if k != "CURSOR_PROJECT_DIR"}
        variants: dict[str, tuple[list[str], dict[str, str]]] = {
            "floor": ([python, "-c", "pass"], env),
            "module": ([python, "-c", RUN_MAIN], env),
            "isolated": ([python, "-I", "-S", "-c", ISOLATED_MAIN], env),
        }
        if script:
            variants["console_script"] = ([script], env)
        results: dict[str, Any] = {}
        for hook in HOOKS:
            payload = payload_for(hook, repo)
            for name, (argv, variant_env) in variants.items():
                key = name if name == "floor" else f"{name}:{hook}"
                if name == "floor" and hook != HOOKS[0]:
                    continue
                sample(argv, payload, repo, variant_env, 2)  # warm the page cache, discarded
                results[key] = summarize(sample(argv, payload, repo, variant_env, n))
        return {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "samples_per_variant": n,
            "results": results,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-n", type=int, default=100, help="samples per variant (default 100)")
    parser.add_argument("--out", default=None, help="write the JSON report here")
    args = parser.parse_args()
    report = run(args.n)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
