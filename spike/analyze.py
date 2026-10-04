#!/usr/bin/env python3
"""CursorFleet M0a spike: summarize captures written by capture_hook.py.

THROWAWAY. Stdlib only. Reads only the sanitized captures.jsonl.

    python3 spike/analyze.py [PATH_TO_captures.jsonl_or_dir] [--json]

PATH defaults to $CURSORFLEET_SPIKE_DIR, else <git-common-dir>/cursorfleet-spike/.
Output is EVIDENCE, not proof: every verdict line says what the data shows and
what it cannot show. Doc-derived examples replayed through the hook are
detectable (cursor_version "0.0.0-doc-example") and are flagged.
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_hook as ch  # noqa: E402

TOOL_EVENTS = (
    "preToolUse", "postToolUse", "postToolUseFailure",
    "beforeShellExecution", "afterShellExecution", "afterFileEdit",
)
BUILTIN_SUBAGENT_TYPES = {"generalPurpose", "explore", "shell", "bash", "browser"}
BASE_KEYS = {
    "conversation_id", "generation_id", "model", "model_id", "model_params",
    "hook_event_name", "cursor_version", "workspace_roots", "user_email", "transcript_path",
}
DOC_KEYS = {  # per docs https://cursor.com/docs/hooks (verified when this spike was written)
    "sessionStart": {"session_id", "is_background_agent", "composer_mode"},
    "sessionEnd": {"session_id", "reason", "duration_ms", "is_background_agent", "final_status", "error_message"},
    "preToolUse": {"tool_name", "tool_input", "tool_use_id", "cwd", "agent_message"},
    "postToolUse": {"tool_name", "tool_input", "tool_output", "tool_use_id", "cwd", "duration"},
    "postToolUseFailure": {"tool_name", "tool_input", "tool_use_id", "cwd", "error_message", "failure_type",
                           "duration", "is_interrupt"},
    "subagentStart": {"subagent_id", "subagent_type", "task", "parent_conversation_id", "tool_call_id",
                      "subagent_model", "is_parallel_worker", "git_branch"},
    "subagentStop": {"subagent_type", "status", "task", "description", "summary", "duration_ms",
                     "message_count", "tool_call_count", "loop_count", "modified_files", "agent_transcript_path"},
    "beforeShellExecution": {"command", "cwd", "sandbox"},
    "afterShellExecution": {"command", "output", "duration", "sandbox"},
    "afterFileEdit": {"file_path", "edits"},
    "preCompact": {"trigger", "context_usage_percent", "context_tokens", "context_window_size",
                   "message_count", "messages_to_compact", "is_first_compaction"},
    "stop": {"status", "loop_count"},
}


def pct(vals, q):
    s = sorted(vals)
    if not s:
        return None
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def load(path):
    if os.path.isdir(path):
        path = os.path.join(path, ch.CAPTURE_FILE)
    recs, bad = [], 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if isinstance(r, dict):
                    recs.append(r)
                else:
                    bad += 1
            except Exception:
                bad += 1  # torn/corrupt line: tolerated
    recs.sort(key=lambda r: r.get("start_epoch_ms", 0))
    return path, recs, bad


def shape_types(d):
    return d if isinstance(d, str) else d.get("t", "?") if isinstance(d, dict) else "?"


def key_shapes(recs):
    by_ev = defaultdict(list)
    for r in recs:
        if "keys" in r:
            by_ev[r.get("hook_event_name")].append(r)
    out = {}
    for ev, rs in by_ev.items():
        n = len(rs)
        keys = defaultdict(lambda: {"count": 0, "types": Counter(), "nested": defaultdict(Counter)})
        for r in rs:
            for k, d in r["keys"].items():
                e = keys[k]
                e["count"] += 1
                e["types"][shape_types(d)] += 1
                if isinstance(d, dict):
                    for nk, nt in (d.get("keys") or {}).items():
                        e["nested"][nk][nt] += 1
                    for nk, nt in (d.get("item_keys") or {}).items():
                        e["nested"]["[]." + nk][nt] += 1
        seen = set(keys)
        doc = DOC_KEYS.get(ev)
        out[ev] = {
            "n": n,
            "keys": {
                k: {
                    "presence": "%d/%d" % (v["count"], n),
                    "types": dict(v["types"]),
                    "nested": {nk: dict(nt) for nk, nt in sorted(v["nested"].items())},
                }
                for k, v in sorted(keys.items())
            },
            "undocumented_keys": sorted(seen - BASE_KEYS - doc) if doc is not None else None,
            "documented_but_absent": sorted((doc | BASE_KEYS) - seen) if doc is not None else None,
        }
    return out


def identity_analysis(recs):
    starts = [r for r in recs if r.get("hook_event_name") == "subagentStart"]
    stops = [r for r in recs if r.get("hook_event_name") == "subagentStop"]
    tools = [r for r in recs if r.get("hook_event_name") in TOOL_EVENTS]
    parents = {r["ids"].get("parent_conversation_id") for r in starts if "ids" in r} - {None}
    sub_ids = {r["ids"].get("subagent_id") for r in starts if "ids" in r} - {None}
    res = {"subagent_starts": len(starts), "subagent_stops": len(stops), "tool_events": len(tools)}

    # (a) any identity-ish key on tool hooks?
    idkeys = Counter()
    for r in tools:
        for k in r.get("keys", {}):
            if any(s in k for s in ("subagent", "parent_", "agent_id", "agent_type")):
                idkeys[k] += 1
    res["tool_hook_keys_with_agent_identity"] = dict(idkeys)

    # (b) tool-hook conversation_id relation to known ids
    rel = Counter()
    for r in tools:
        cid = (r.get("ids") or {}).get("conversation_id")
        if cid in sub_ids:
            rel["conversation_id==subagent_id"] += 1
        elif cid in parents:
            rel["conversation_id==parent_conversation_id"] += 1
        else:
            rel["conversation_id=other"] += 1
    res["tool_conversation_id_relation"] = dict(rel)

    # (c) temporal attribution: pair each start with the next unmatched stop of same type.
    unmatched = list(stops)
    windows = []
    for s in starts:
        st = (s.get("ids") or {}).get("subagent_type")
        m = None
        for cand in unmatched:
            if (cand.get("ids") or {}).get("subagent_type") == st and cand["start_epoch_ms"] >= s["start_epoch_ms"]:
                m = cand
                break
        if m:
            unmatched.remove(m)
        windows.append({
            "subagent_id": (s.get("ids") or {}).get("subagent_id"),
            "subagent_type": st,
            "parent": (s.get("ids") or {}).get("parent_conversation_id"),
            "t0": s["start_epoch_ms"],
            "t1": m["start_epoch_ms"] if m else None,
            "matched_stop": bool(m),
        })
    res["windows"] = len(windows)
    res["windows_without_matching_stop"] = sum(1 for w in windows if not w["matched_stop"])
    note_matching = "subagentStop has no subagent_id per docs; start/stop pairing is by type+order and is approximate"
    res["pairing_caveat"] = note_matching
    in_win, same_conv_gen = 0, 0
    main_pairs = set()
    for r in tools:
        t = r["start_epoch_ms"]
        ids = r.get("ids") or {}
        inside = any(w["t1"] and w["t0"] <= t <= w["t1"] and w["parent"] == ids.get("conversation_id") for w in windows)
        if not inside:
            main_pairs.add((ids.get("conversation_id"), ids.get("generation_id")))
    for r in tools:
        t = r["start_epoch_ms"]
        ids = r.get("ids") or {}
        if any(w["t1"] and w["t0"] <= t <= w["t1"] and w["parent"] == ids.get("conversation_id") for w in windows):
            in_win += 1
            if (ids.get("conversation_id"), ids.get("generation_id")) in main_pairs:
                same_conv_gen += 1
    res["tool_events_inside_subagent_windows"] = in_win
    res["of_which_same_conversation_and_generation_as_main"] = same_conv_gen

    # (d) Task tool linkage
    task_ids = {(r.get("ids") or {}).get("tool_use_id") for r in tools
                if (r.get("ids") or {}).get("tool_name") == "Task"} - {None}
    call_ids = {(r.get("ids") or {}).get("tool_call_id") for r in starts} - {None}
    res["task_tool_use_ids_matching_subagentStart_tool_call_id"] = len(task_ids & call_ids)
    res["task_tool_events"] = sum(1 for r in tools if (r.get("ids") or {}).get("tool_name") == "Task")

    if not starts:
        verdict = "INCONCLUSIVE: no subagentStart captured"
    elif idkeys:
        verdict = "LIKELY YES: tool hooks carry agent-identity-like keys %s (confirm values differ per subagent)" % sorted(idkeys)
    elif rel.get("conversation_id==subagent_id"):
        verdict = "LIKELY YES: tool hooks inside subagents use conversation_id == subagent_id"
    elif in_win:
        verdict = ("LIKELY NO: %d tool events inside subagent windows; no identity keys; %d/%d share the main "
                   "conversation_id+generation_id. Only temporal attribution possible (unsafe under parallelism)."
                   % (in_win, same_conv_gen, in_win))
    else:
        verdict = "INCONCLUSIVE: subagentStart seen but no tool hooks fell inside a matched subagent window"
    res["verdict"] = verdict
    return res


def subagent_types(recs):
    c = Counter()
    for r in recs:
        if r.get("hook_event_name") in ("subagentStart", "subagentStop"):
            c[((r.get("ids") or {}).get("subagent_type"), r["hook_event_name"])] += 1
    names = sorted({k[0] for k in c if k[0]})
    custom = [n for n in names if n not in BUILTIN_SUBAGENT_TYPES]
    return {
        "types_seen": {"%s/%s" % (k[0], k[1]): v for k, v in sorted(c.items(), key=lambda x: str(x))},
        "non_builtin_types": custom,
        "note": "Compare non_builtin_types with the `name:` in your .cursor/agents/*.md. "
                "If a custom agent only ever appears as generalPurpose, subagent_type does NOT carry the custom name.",
    }


def latency(recs):
    by = defaultdict(lambda: {"latency_ms": [], "stdin_read_ms": []})
    for r in recs:
        ev = r.get("hook_event_name")
        for k in ("latency_ms", "stdin_read_ms"):
            if isinstance(r.get(k), (int, float)):
                by[ev][k].append(r[k])
    out = {}
    for ev, d in sorted(by.items(), key=lambda x: str(x[0])):
        out[ev] = {}
        for k, v in d.items():
            if v:
                out[ev][k] = {"n": len(v), "p50": round(pct(v, .5), 3), "p95": round(pct(v, .95), 3), "max": round(max(v), 3)}
    return out


def worktrees(recs):
    c = defaultdict(Counter)
    bases = defaultdict(set)
    for r in recs:
        label = r.get("label") or "(no label)"
        for i, w in enumerate(r.get("workspace_roots") or []):
            c[(label, "workspace_roots")][w.get("git_kind")] += 1
            if w.get("git_kind") == "linked-worktree":
                bases[label].add(w.get("base"))
        if r.get("cwd"):
            c[(label, "payload.cwd")][r["cwd"].get("git_kind")] += 1
        if r.get("proc_cwd"):
            c[(label, "process_cwd")][r["proc_cwd"].get("git_kind")] += 1
        if r.get("cursor_project_dir"):
            c[(label, "CURSOR_PROJECT_DIR")][r["cursor_project_dir"].get("git_kind")] += 1
    dir_src = Counter((r.get("label") or "(no label)", r.get("capture_dir_source")) for r in recs if "capture_dir_source" in r)
    return {
        "git_kind_by_label_and_source": {"%s | %s" % k: dict(v) for k, v in sorted(c.items())},
        "linked_worktree_basenames_by_label": {k: sorted(v) for k, v in bases.items()},
        "capture_dir_source": {"%s | %s" % k: v for k, v in dir_src.items()},
        "note": "git_kind=linked-worktree means <root>/.git is a gitfile pointing into <common>/worktrees/<name>. "
                "Hooks run from different worktrees should still land in ONE capture file when capture_dir_source=git-common-dir.",
    }


def interleaving(recs):
    iv = [(r["start_epoch_ms"], r.get("end_epoch_ms", r["start_epoch_ms"]), r.get("pid"), r.get("hook_event_name"))
          for r in recs if "start_epoch_ms" in r and "end_epoch_ms" in r]
    events = []
    for a, b, *_ in iv:
        events.append((a, 1))
        events.append((b, -1))
    events.sort()
    cur = mx = 0
    for _, d in events:
        cur += d
        mx = max(mx, cur)
    overlap_pairs = 0
    iv_sorted = sorted(iv)
    for i, x in enumerate(iv_sorted):
        for y in iv_sorted[i + 1:]:
            if y[0] > x[1]:
                break
            if x[2] != y[2]:
                overlap_pairs += 1
    # parallel subagent windows
    starts = [r for r in recs if r.get("hook_event_name") == "subagentStart"]
    stops = [r for r in recs if r.get("hook_event_name") == "subagentStop"]
    win_overlap = 0
    wins = []
    unmatched = list(stops)
    for s in starts:
        st = (s.get("ids") or {}).get("subagent_type")
        m = next((c for c in unmatched if (c.get("ids") or {}).get("subagent_type") == st
                  and c["start_epoch_ms"] >= s["start_epoch_ms"]), None)
        if m:
            unmatched.remove(m)
            wins.append((s["start_epoch_ms"], m["start_epoch_ms"]))
    for i, a in enumerate(wins):
        for b in wins[i + 1:]:
            if a[0] < b[1] and b[0] < a[1]:
                win_overlap += 1
    # A-B-A pattern on conversation/generation among tool events
    seq = [((r.get("ids") or {}).get("conversation_id"), (r.get("ids") or {}).get("tool_use_id"))
           for r in recs if r.get("hook_event_name") in TOOL_EVENTS]
    aba = 0
    open_tool = []
    for cid, tid in seq:
        if tid is None:
            continue
        if tid in open_tool:
            open_tool.remove(tid)
        else:
            if open_tool:
                aba += 1  # a new tool call started before an earlier one finished
            open_tool.append(tid)
    pw = sum(1 for r in starts if (r.get("vals") or {}).get("is_parallel_worker") is True)
    return {
        "hook_processes": len(iv),
        "max_concurrent_hook_processes": mx,
        "overlapping_process_pairs": overlap_pairs,
        "overlapping_subagent_windows": win_overlap,
        "tool_calls_started_while_another_open": aba,
        "subagentStart_is_parallel_worker_true": pw,
        "pids_distinct": len({x[2] for x in iv}),
        "note": "Overlap = two hook processes alive at the same wall-clock time. Concurrent subagents are only "
                "'interleaved' if overlapping_subagent_windows > 0 AND tool hooks from both windows alternate.",
    }


def analyze(path):
    path, recs, bad = load(path)
    real = [r for r in recs if r.get("hook_event_name") != "<internal-error>"]
    versions = Counter((r.get("ids") or {}).get("cursor_version") for r in real)
    out = {
        "file": path,
        "records": len(recs),
        "corrupt_lines_skipped": bad,
        "internal_error_records": len(recs) - len(real),
        "doc_example_records": sum(1 for r in real if (r.get("ids") or {}).get("cursor_version") == "0.0.0-doc-example"),
        "labels": dict(Counter(r.get("label") or "(no label)" for r in real)),
        "cursor_versions": {str(k): v for k, v in versions.items()},
        "event_counts": dict(Counter(r.get("hook_event_name") for r in real)),
        "env_names_seen": sorted({n for r in real for n in r.get("env_names", [])}),
        "key_shapes": key_shapes(real),
        "agent_identity": identity_analysis(real),
        "subagent_types": subagent_types(real),
        "latency_ms": latency(real),
        "worktrees": worktrees(real),
        "interleaving": interleaving(real),
    }
    return out


def render(a):
    L = []
    w = L.append
    w("=== CursorFleet M0a spike analysis ===")
    w("file: %s" % a["file"])
    w("records: %d  corrupt lines skipped: %d  internal-error records: %d" %
      (a["records"], a["corrupt_lines_skipped"], a["internal_error_records"]))
    if a["doc_example_records"]:
        w("!! %d records are replayed DOC-DERIVED examples (cursor_version 0.0.0-doc-example), NOT live Cursor captures." %
          a["doc_example_records"])
    w("labels: %s" % a["labels"])
    w("cursor_versions: %s" % a["cursor_versions"])
    w("env var NAMES seen in hook processes (names only): %s" % (", ".join(a["env_names_seen"]) or "(none)"))
    w("")
    w("--- event counts ---")
    for k, v in sorted(a["event_counts"].items(), key=lambda x: str(x[0])):
        w("  %-22s %d" % (k, v))
    w("")
    w("--- key shapes per event (presence = records containing key / records of event) ---")
    for ev, d in sorted(a["key_shapes"].items(), key=lambda x: str(x[0])):
        w("[%s] n=%d" % (ev, d["n"]))
        for k, v in d["keys"].items():
            nested = ""
            if v["nested"]:
                nested = "  nested: " + ", ".join("%s:%s" % (nk, "/".join(nt)) for nk, nt in v["nested"].items())
            w("    %-24s %-7s %s%s" % (k, v["presence"], "/".join(v["types"]), nested))
        if d["undocumented_keys"]:
            w("    >> keys NOT in docs: %s" % d["undocumented_keys"])
        if d["documented_but_absent"]:
            w("    >> documented keys never seen: %s" % d["documented_but_absent"])
    w("")
    w("--- Q1 agent identity inside subagent tool hooks ---")
    ai = a["agent_identity"]
    for k, v in ai.items():
        if k != "verdict":
            w("  %s: %s" % (k, v))
    w("  VERDICT: %s" % ai["verdict"])
    w("")
    w("--- Q2 subagent_type values ---")
    st = a["subagent_types"]
    w("  seen: %s" % st["types_seen"])
    w("  non-builtin: %s" % st["non_builtin_types"])
    w("  note: %s" % st["note"])
    w("")
    w("--- Q3/Q4 worktree evidence ---")
    wt = a["worktrees"]
    for k, v in wt["git_kind_by_label_and_source"].items():
        w("  %-40s %s" % (k, v))
    w("  linked-worktree basenames by label: %s" % wt["linked_worktree_basenames_by_label"])
    w("  capture dir source: %s" % wt["capture_dir_source"])
    w("  note: %s" % wt["note"])
    w("")
    w("--- Q5 interleaving ---")
    for k, v in a["interleaving"].items():
        w("  %s: %s" % (k, v))
    w("")
    w("--- Q6 hook latency (in-process ms; excludes interpreter startup; see results/ for wall) ---")
    w("  %-22s %-14s %5s %9s %9s %9s" % ("hook", "metric", "n", "p50", "p95", "max"))
    for ev, d in a["latency_ms"].items():
        for k, v in d.items():
            w("  %-22s %-14s %5d %9.3f %9.3f %9.3f" % (ev, k, v["n"], v["p50"], v["p95"], v["max"]))
    return "\n".join(L)


def main(argv):
    args = [x for x in argv[1:] if not x.startswith("--")]
    as_json = "--json" in argv
    path = args[0] if args else ch.resolve_capture_dir(None)[0]
    try:
        a = analyze(path)
    except FileNotFoundError:
        print("no capture file at %s (did hooks run? see spike/README.md)" % path, file=sys.stderr)
        return 1
    print(json.dumps(a, indent=2, default=str) if as_json else render(a))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
