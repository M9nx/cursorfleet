"""Smoke test for scripts/bench_hook.py. Real numbers: ``uv run python scripts/bench_hook.py``.

Timings are machine dependent, so the only assertions are generous sanity bounds that
catch a hot path that has become pathological (for example an accidental heavy import).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bench_hook.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bench_hook", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_hook"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.benchmark
def test_bench_script_runs_and_the_hot_path_is_sane() -> None:
    bench = load_script()
    samples = int(os.environ.get("CURSORFLEET_BENCH_N", "3"))
    report = bench.run(samples)
    results = report["results"]
    assert "floor" in results and any(key.startswith("module:") for key in results)
    for key, row in results.items():
        assert row["n"] == samples
        assert row["p50_ms"] < 3000, f"{key} is pathologically slow: {row}"
    sys.stdout.write(f"\nhook latency p50/p95 (ms), n={samples}:\n")
    for key, row in sorted(results.items()):
        sys.stdout.write(f"  {key:34s} {row['p50_ms']:7.1f} {row['p95_ms']:7.1f}\n")


def test_percentile_helper_is_correct() -> None:
    bench = load_script()
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert bench.percentile(values, 0.5) == 3.0
    assert bench.percentile(values, 0.0) == 1.0 and bench.percentile(values, 1.0) == 5.0
    assert bench.percentile([7.0], 0.95) == 7.0
