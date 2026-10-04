#!/usr/bin/env python3
"""CursorFleet M0a spike: measure cold-start wall latency of the capture hook.

THROWAWAY. Stdlib only. Spawns fresh interpreter processes (cold start per
run, like Cursor does for every hook call), feeds a doc-derived payload on
stdin, and reports wall-clock percentiles measured by the parent.

    python3 spike/bench_latency.py [-n 40] [--out spike/results/latency-<platform>.json]

Variants measured:
  floor_pass        python -c pass                       (interpreter floor)
  floor_isolated    python -I -S -c pass                 (-I isolated, -S no site)
  capture           python capture_hook.py preToolUse    (what a user would register)
  capture_isolated  python -I -S capture_hook.py preToolUse

Wall time includes fork/exec, interpreter startup, imports, work and exit.
It does NOT include Cursor's own spawn/IPC overhead. Captures go to a temp dir.
"""
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

HERE = os.path.dirname(os.path.abspath(__file__))


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def run_variant(argv, payload, env, n):
    walls = []
    for _ in range(n):
        t = time.perf_counter()
        r = subprocess.run(argv, input=payload, capture_output=True, env=env, timeout=60)
        walls.append((time.perf_counter() - t) * 1000.0)
        if r.returncode != 0:
            raise SystemExit("variant failed: %r rc=%s" % (argv, r.returncode))
    s = sorted(walls)
    return {
        "n": n,
        "first_ms": round(walls[0], 2),
        "min_ms": round(s[0], 2),
        "p50_ms": round(pct(s, 0.50), 2),
        "p95_ms": round(pct(s, 0.95), 2),
        "max_ms": round(s[-1], 2),
        "mean_ms": round(statistics.fmean(s), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=40, help="runs per variant (default 40)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    payload = open(os.path.join(HERE, "doc_examples", "preToolUse.doc-derived.json"), "rb").read()
    hook = os.path.join(HERE, "capture_hook.py")
    tmp = tempfile.mkdtemp(prefix="cf-spike-bench-")
    env = dict(os.environ, CURSORFLEET_SPIKE_DIR=os.path.join(tmp, "cap"))
    py = sys.executable
    try:
        variants = {
            "floor_pass": [py, "-c", "pass"],
            "floor_isolated": [py, "-I", "-S", "-c", "pass"],
            "capture": [py, hook, "preToolUse"],
            "capture_isolated": [py, "-I", "-S", hook, "preToolUse"],
        }
        # -I ignores PYTHON* env vars, so isolated capture needs the dir via a LABEL-free fallback:
        # we pass the dir through a tiny wrapper-free route: -I keeps os.environ (only PYTHON* ignored).
        results = {}
        for name, argv in variants.items():
            results[name] = run_variant(argv, payload, env, args.n)
            r = results[name]
            print("%-17s n=%d first=%7.2f min=%7.2f p50=%7.2f p95=%7.2f max=%7.2f ms" % (
                name, r["n"], r["first_ms"], r["min_ms"], r["p50_ms"], r["p95_ms"], r["max_ms"]))
        # in-process latency recorded by the hook itself (excludes interpreter startup)
        lines = open(os.path.join(tmp, "cap", "captures.jsonl"), encoding="utf-8").read().splitlines()
        inproc = sorted(json.loads(l)["latency_ms"] for l in lines if '"latency_ms"' in l)
        in_stats = {
            "n": len(inproc),
            "p50_ms": round(pct(inproc, 0.5), 3),
            "p95_ms": round(pct(inproc, 0.95), 3),
            "max_ms": round(inproc[-1], 3),
        }
        print("in-process latency_ms (hook's own records, excludes interpreter startup): %s" % in_stats)
        out = {
            "kind": "measured-on-this-machine; NOT Cursor-measured",
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "measured_at_epoch_s": int(time.time()),
            "runs_per_variant": args.n,
            "variants_wall_ms": results,
            "capture_in_process_ms": in_stats,
        }
        path = args.out or os.path.join(HERE, "results", "latency-%s.json" % sys.platform)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(out, f, indent=2)
            f.write("\n")
        print("wrote %s" % path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
