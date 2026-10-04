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
                     # optional observed (not documented, not guaranteed): subagent_id, child_conversation_id
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
    recs.sort(key=lambda r: _when(r) or 0)
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


# --- Q1 identity classification -------------------------------------------------------
# Four separate buckets (docs/empirical-test-plan.md row 8). The verdict derived from them is
# a HINT: only a human classifying per hook name, against ground truth, decides Q1.
#   direct_current_identity          a field that uniquely identifies the CURRENT subagent
#                                    instance on tool hooks (a subagent_id that equals a
#                                    captured subagentStart.subagent_id, on every occurrence;
#                                    or conversation_id equal to such a subagent_id)
#   role_only_identity               names the kind of agent only (subagent_type ...)
#   parent_only_identity             names the spawning parent only
#                                    (parent_conversation_id, other parent_* identity
#                                    keys except parent_tool_call_id, or conversation_id
#                                    equal to the parent's). NEVER counts toward
#                                    current-instance identity.
#   unclassified_identity_candidates id-like keys with undocumented meaning, a
#                                    subagent_id that is not (fully) linkable, or a
#                                    deterministic-link candidate such as
#                                    parent_tool_call_id (not EXACT, not parent-only,
#                                    until row 8 repetitions verify it). NEVER
#                                    auto-promoted.
BUCKETS = (
    "direct_current_identity",
    "role_only_identity",
    "parent_only_identity",
    "unclassified_identity_candidates",
)
DIRECT_ID_KEYS = frozenset({"subagent_id"})
ROLE_ONLY_KEYS = frozenset({"subagent_type", "agent_type", "agent_role", "subagent_role"})
PARENT_ONLY_KEYS = frozenset({"parent_conversation_id"})
# Deterministic-link candidate: observed on inner tool hooks; not EXACT and not
# parent-only until row 8 concurrent repetitions verify the relationship.
LINK_CANDIDATE_KEYS = frozenset({"parent_tool_call_id"})
# session_id correlates a session, not an agent instance. Never a Q1 identity bucket.
SESSION_LEVEL_KEYS = frozenset({"session_id"})
HINT_NOTE = "hint only; requires manual classification per docs/empirical-test-plan.md row 8"
PAIR_SUBAGENT_ID = "subagent_id"
PAIR_TYPE_ORDER = "type_order"
ASSOC_PARENT_TOOL = "parent_tool_call_id"
ASSOC_CHILD_CONV = "child_conversation_id"
ASSOC_TEMPORAL = "temporal"
# subagentStop.subagent_id and subagentStop.child_conversation_id are optional,
# empirically observed fields (one Cursor 3.22.7 sequential run). Not guaranteed.


def _dict(x):
    return x if isinstance(x, dict) else {}


def _sid(v):
    """A usable id string, else None (missing, null, '<invalid>', or any odd type)."""
    return v if isinstance(v, str) and v and v != "<invalid>" else None


def empty_link():
    """Evidence for one id relationship. Missing values are unavailable, not 0 matches."""
    return {
        "observed": 0,
        "comparable": 0,
        "matches": 0,
        "mismatches": 0,
        "unavailable": 0,
        "collisions": 0,
    }


def pairwise_link(pairs):
    """Same-record left ↔ right. A missing side is unavailable, never a 0-match refutation."""
    ev = empty_link()
    items = list(pairs)
    ev["observed"] = len(items)
    match_values = Counter()
    for left, right in items:
        if left is None or right is None:
            ev["unavailable"] += 1
            continue
        ev["comparable"] += 1
        if left == right:
            ev["matches"] += 1
            match_values[left] += 1
        else:
            ev["mismatches"] += 1
    colliding = {v for v, n in match_values.items() if n > 1}
    if colliding:
        ev["collisions"] = sum(match_values[v] for v in colliding)
        ev["matches"] -= ev["collisions"]
    return ev


def membership_link(left_values, right_values):
    """Each left id against the multiset of right ids.

    Missing left, or no usable right ids at all, is unavailable. A left that
    equals exactly one right is a match; equals none is a mismatch; equals
    two or more is a collision. Never treat unavailable as 0 matches.
    """
    ev = empty_link()
    lefts = list(left_values)
    rights = [v for v in right_values if v is not None]
    ev["observed"] = len(lefts)
    counts = Counter(rights)
    no_rights = not counts
    for left in lefts:
        if left is None or no_rights:
            ev["unavailable"] += 1
            continue
        ev["comparable"] += 1
        n = counts[left]
        if n == 1:
            ev["matches"] += 1
        elif n == 0:
            ev["mismatches"] += 1
        else:
            ev["collisions"] += 1
    return ev


def session_correlation(recs):
    """session_id is session-level correlation, not Q1 agent identity."""
    sessions = [r for r in recs if r.get("hook_event_name") == "sessionStart"]
    tools = [r for r in recs if r.get("hook_event_name") in TOOL_EVENTS]
    start_sids = [_sid(_dict(r.get("ids")).get("session_id")) for r in sessions]
    return {
        "note": (
            "session_id is session-level correlation, not agent identity "
            "(not direct, role-only, parent-only, or unclassified)."
        ),
        "sessionStart_session_id_vs_conversation_id": pairwise_link(
            (
                _sid(_dict(r.get("ids")).get("session_id")),
                _sid(_dict(r.get("ids")).get("conversation_id")),
            )
            for r in sessions
        ),
        "tool_session_id_vs_sessionStart_session_id": membership_link(
            [_sid(_dict(r.get("ids")).get("session_id")) for r in tools],
            start_sids,
        ),
        "tool_session_id_vs_tool_conversation_id": pairwise_link(
            (
                _sid(_dict(r.get("ids")).get("session_id")),
                _sid(_dict(r.get("ids")).get("conversation_id")),
            )
            for r in tools
        ),
    }


def _when(r):
    v = r.get("start_epoch_ms")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _idlike(low):
    return (low in ("id", "uuid") or low.endswith(("_id", "_ids", "_uuid"))
            or any(t in low for t in ("agent", "instance", "worker")))


def classify_key(name, event):
    """Bucket for one payload key seen on a tool hook, or None if it is not identity-like.

    A subagent_id is returned as direct here only provisionally; identity_analysis demotes it
    to unclassified unless every occurrence links to a captured subagentStart.subagent_id.
    """
    if not isinstance(name, str) or name.startswith("<"):
        return None
    low = name.lower()
    if low in SESSION_LEVEL_KEYS:
        return None
    if low in LINK_CANDIDATE_KEYS:
        return "unclassified_identity_candidates"
    if low in PARENT_ONLY_KEYS or (low != "parent_tool_call_id" and "parent" in low):
        return "parent_only_identity"
    if low in DIRECT_ID_KEYS:
        return "direct_current_identity"
    if low in ROLE_ONLY_KEYS:
        return "role_only_identity"
    if name in BASE_KEYS or name in DOC_KEYS.get(event, ()):
        return None  # documented fields (conversation_id, tool_use_id, ...) are not candidates
    return "unclassified_identity_candidates" if _idlike(low) else None


def identity_verdict(buckets, starts, in_win):
    """(code, text) for Q1 from the four buckets. A hint, never a result."""
    if buckets["direct_current_identity"]:
        code, why = "CONFIRMED", "tool hooks carry a field that uniquely identifies the current subagent instance: %s" % sorted(buckets["direct_current_identity"])
    elif buckets["role_only_identity"]:
        code, why = "PARTIAL", "role only (%s): names the kind of agent, not the instance" % sorted(buckets["role_only_identity"])
    elif buckets["unclassified_identity_candidates"]:
        code, why = "OPEN", "undocumented or unlinked id-like keys %s need manual classification" % sorted(buckets["unclassified_identity_candidates"])
    elif buckets["parent_only_identity"]:
        code, why = "REFUTED", "parent identity only (%s); a parent id never identifies the current subagent" % sorted(buckets["parent_only_identity"])
    elif not starts:
        code, why = "OPEN", "no subagentStart captured; nothing to classify"
    elif not in_win:
        code, why = "OPEN", "subagentStart seen but no tool hooks fell inside a matched subagent window"
    else:
        code, why = "REFUTED", "no identity-bearing key on tool hooks inside subagent windows"
    return code, "%s: %s (%s)" % (code, why, HINT_NOTE)


def pair_start_stop(starts, stops):
    """Pair each start with one stop.

    Prefer a matching optional subagent_id on the stop (equal to the start's
    subagent_id or tool_call_id). Fall back to type plus chronological order
    only when that id is unavailable on the stop. A stop that carries a
    non-matching subagent_id is never stolen by type+order.
    """
    unmatched = [x for x in stops if _when(x) is not None]
    windows = []
    id_collisions = 0
    for s in starts:
        sids = _dict(s.get("ids"))
        t0 = _when(s)
        st = sids.get("subagent_type")
        start_sid = _sid(sids.get("subagent_id"))
        start_call = _sid(sids.get("tool_call_id"))
        m = None
        method = None
        if t0 is not None:
            id_hits = []
            for cand in unmatched:
                csid = _sid(_dict(cand.get("ids")).get("subagent_id"))
                if csid is None:
                    continue
                ct = _when(cand)
                if ct is not None and ct >= t0 and (
                    (start_sid is not None and csid == start_sid)
                    or (start_call is not None and csid == start_call)
                ):
                    id_hits.append(cand)
            if len(id_hits) > 1:
                id_collisions += 1
            if id_hits:
                m = id_hits[0]
                method = PAIR_SUBAGENT_ID
            else:
                for cand in unmatched:
                    if _sid(_dict(cand.get("ids")).get("subagent_id")) is not None:
                        continue
                    if _dict(cand.get("ids")).get("subagent_type") == st and _when(cand) >= t0:
                        m = cand
                        method = PAIR_TYPE_ORDER
                        break
        if m:
            unmatched.remove(m)
        mids = _dict(m.get("ids")) if m else {}
        windows.append({
            "subagent_id": sids.get("subagent_id"),
            "subagent_type": st,
            "parent": sids.get("parent_conversation_id"),
            "tool_call_id": start_call,
            "child_conversation_id": _sid(mids.get("child_conversation_id")),
            "stop_subagent_id": _sid(mids.get("subagent_id")),
            "t0": t0,
            "t1": _when(m) if m else None,
            "matched_stop": bool(m),
            "pair_method": method,
        })
    return windows, id_collisions


def associate_tool(r, windows):
    """Associate one tool event with at most one window.

    Order: parent_tool_call_id, then child_conversation_id, then temporal.
    A unique hit at an earlier level wins. Ambiguous (2+) hits at a level are
    skipped and recorded. Temporal matching is never treated as exact.
    Returns (window_or_None, method_or_None, list_of_ambiguous_reasons).
    """
    ids = _dict(r.get("ids"))
    t = _when(r)
    ambiguous = []
    ptc = _sid(ids.get("parent_tool_call_id"))
    if ptc is not None:
        hits = [w for w in windows if _sid(w.get("tool_call_id")) == ptc]
        if len(hits) == 1:
            return hits[0], ASSOC_PARENT_TOOL, ambiguous
        if len(hits) > 1:
            ambiguous.append("ambiguous_parent_tool_call_id")
    cid = _sid(ids.get("conversation_id"))
    if cid is not None:
        hits = [w for w in windows if w.get("child_conversation_id") == cid]
        if len(hits) == 1:
            return hits[0], ASSOC_CHILD_CONV, ambiguous
        if len(hits) > 1:
            ambiguous.append("ambiguous_child_conversation_id")
    if t is not None:
        hits = [w for w in windows
                if w["t0"] is not None and w["t1"] is not None and w["t0"] <= t <= w["t1"]]
        if len(hits) == 1:
            return hits[0], ASSOC_TEMPORAL, ambiguous
        if len(hits) > 1:
            ambiguous.append("ambiguous_temporal")
    return None, None, ambiguous


def _is_task(r):
    return _dict(r.get("ids")).get("tool_name") == "Task"


def _bool_flag(container, key):
    """True/False if a real bool is stored; None if missing or non-bool."""
    if not isinstance(container, dict) or key not in container:
        return None
    v = container[key]
    return v if v is True or v is False else None


def flag_counts(values):
    """Group booleans as true / false / missing. Non-bool is missing."""
    out = {"true": 0, "false": 0, "missing": 0}
    for v in values:
        if v is True:
            out["true"] += 1
        elif v is False:
            out["false"] += 1
        else:
            out["missing"] += 1
    return out


def _task_run_in_background(r):
    return _bool_flag(_dict(r.get("vals")), "run_in_background")


def _start_parallel_flag(r):
    return _bool_flag(_dict(r.get("vals")), "is_parallel_worker")


def _tool_name(r):
    name = _dict(r.get("ids")).get("tool_name")
    return name if isinstance(name, str) and name and name != "<invalid>" else "(missing)"


def tool_outcomes_by_event_and_tool(recs):
    """Counts of tool-hook records grouped by hook event, then tool name."""
    by_ev = defaultdict(Counter)
    for r in recs:
        ev = r.get("hook_event_name")
        if ev not in TOOL_EVENTS:
            continue
        by_ev[ev][_tool_name(r)] += 1
    return {ev: dict(c) for ev, c in sorted(by_ev.items(), key=lambda x: str(x[0]))}


def background_lifecycle(recs):
    """Sanitized Task / parallel flags, tool outcomes, and start/stop completeness.

    Missing means the boolean was not recorded (or was not a bool), not that it
    was false. Does not classify Q1.
    """
    recs = [r for r in recs if isinstance(r, dict)]
    starts = [r for r in recs if r.get("hook_event_name") == "subagentStart"]
    stops = [r for r in recs if r.get("hook_event_name") == "subagentStop"]
    tools = [r for r in recs if r.get("hook_event_name") in TOOL_EVENTS]
    tasks = [r for r in tools if _is_task(r)]
    windows, _ = pair_start_stop(starts, stops)
    matched = sum(1 for w in windows if w["matched_stop"])
    unmatched = sum(1 for w in windows if not w["matched_stop"])
    return {
        "task_run_in_background": flag_counts(_task_run_in_background(r) for r in tasks),
        "subagentStart_is_parallel_worker": flag_counts(_start_parallel_flag(r) for r in starts),
        "tool_outcomes_by_event_and_tool": tool_outcomes_by_event_and_tool(recs),
        "lifecycle_completeness": {
            "starts": len(starts),
            "matched_stops": matched,
            "unmatched_starts": unmatched,
        },
        "note": (
            "Sanitized flags only (true/false/missing). Task run_in_background is "
            "read from vals (the hook stores the nested tool_input boolean when "
            "present). Missing means the boolean was not recorded, not false. "
            "Not a Q1 verdict."
        ),
    }


def identity_analysis(recs):
    recs = [r for r in recs if isinstance(r, dict)]
    starts = [r for r in recs if r.get("hook_event_name") == "subagentStart"]
    stops = [r for r in recs if r.get("hook_event_name") == "subagentStop"]
    tools = [r for r in recs if r.get("hook_event_name") in TOOL_EVENTS]
    parents = {_sid(_dict(r.get("ids")).get("parent_conversation_id")) for r in starts} - {None}
    sub_ids = {_sid(_dict(r.get("ids")).get("subagent_id")) for r in starts} - {None}
    child_cids = {_sid(_dict(r.get("ids")).get("child_conversation_id")) for r in stops} - {None}
    res = {"subagent_starts": len(starts), "subagent_stops": len(stops), "tool_events": len(tools)}

    # (a) classify every identity-like key that appears on tool hooks into the four buckets.
    buckets = {b: Counter() for b in BUCKETS}
    linked, unlinked = Counter(), Counter()
    legacy = Counter()  # raw, unclassified key counts (kept for the row 8 artifact list)
    for r in tools:
        ids = _dict(r.get("ids"))
        for k in _dict(r.get("keys")):
            if isinstance(k, str) and any(x in k for x in ("subagent", "parent_", "agent_id", "agent_type")):
                legacy[k] += 1
            b = classify_key(k, r.get("hook_event_name"))
            if b is None:
                continue
            if k in DIRECT_ID_KEYS:
                if _sid(ids.get(k)) in sub_ids:
                    linked[k] += 1
                else:
                    unlinked[k] += 1
            else:
                buckets[b][k] += 1
    for k in sorted(set(linked) | set(unlinked)):
        # direct only if EVERY occurrence links to a start; a partial or unlinked id is a
        # candidate for manual review (row 8: "unlinked discriminator").
        if linked[k] and not unlinked[k]:
            buckets["direct_current_identity"][k] += linked[k]
        else:
            buckets["unclassified_identity_candidates"][k] += linked[k] + unlinked[k]
    res["tool_hook_keys_with_agent_identity"] = dict(legacy)  # RAW; not an identity verdict

    # (b) tool-hook conversation_id relation to known ids
    rel = Counter()
    for r in tools:
        cid = _sid(_dict(r.get("ids")).get("conversation_id"))
        if cid is not None and cid in sub_ids:
            rel["conversation_id==subagent_id"] += 1
        elif cid is not None and cid in parents:
            rel["conversation_id==parent_conversation_id"] += 1
        elif cid is not None and cid in child_cids:
            rel["conversation_id==subagentStop.child_conversation_id"] += 1
        else:
            rel["conversation_id=other"] += 1
    res["tool_conversation_id_relation"] = dict(rel)
    if rel.get("conversation_id==subagent_id"):
        buckets["direct_current_identity"]["conversation_id==subagent_id"] += rel["conversation_id==subagent_id"]

    # (c) start/stop pairing, then inner-tool association (never call temporal exact).
    windows, pairing_id_collisions = pair_start_stop(starts, stops)
    res["windows"] = len(windows)
    res["windows_without_matching_stop"] = sum(1 for w in windows if not w["matched_stop"])
    res["windows_paired_by_subagent_id"] = sum(1 for w in windows if w["pair_method"] == PAIR_SUBAGENT_ID)
    res["windows_paired_by_type_order"] = sum(1 for w in windows if w["pair_method"] == PAIR_TYPE_ORDER)
    res["pairing_id_collisions"] = pairing_id_collisions
    res["pairing_caveat"] = (
        "subagentStop.subagent_id and child_conversation_id are optional, empirically "
        "observed fields (not guaranteed). Pair by matching subagent_id when present; "
        "otherwise type+order (approximate). Temporal inner-tool association is never exact."
    )

    assoc_counts = Counter()
    ambiguous_links = Counter()
    in_win, same_conv_gen, parent_cid_in_win = 0, 0, 0
    main_pairs = set()
    flags = []
    for r in tools:
        win, method, amb = associate_tool(r, windows)
        for reason in amb:
            ambiguous_links[reason] += 1
        flags.append((r, win, method))
        if method:
            assoc_counts[method] += 1
        elif not _is_task(r):
            assoc_counts["unassociated"] += 1
    for r, win, method in flags:
        if win is None:
            ids = _dict(r.get("ids"))
            main_pairs.add((_sid(ids.get("conversation_id")), _sid(ids.get("generation_id"))))
    for r, win, method in flags:
        if win is None:
            continue
        ids = _dict(r.get("ids"))
        in_win += 1
        cid = _sid(ids.get("conversation_id"))
        if (cid, _sid(ids.get("generation_id"))) in main_pairs:
            same_conv_gen += 1
        # Only the parent's conversation_id is parent-only; child conversation is not.
        if cid is not None and cid == _sid(win.get("parent")):
            parent_cid_in_win += 1
    res["tool_events_inside_subagent_windows"] = in_win
    res["of_which_same_conversation_and_generation_as_main"] = same_conv_gen
    res["inner_tool_association"] = dict(assoc_counts)
    res["ambiguous_links"] = dict(ambiguous_links)
    res["temporal_association_is_not_exact"] = True
    if parent_cid_in_win:
        buckets["parent_only_identity"]["conversation_id==parent_conversation_id"] += parent_cid_in_win

    # (d) linkage evidence. Missing values are unavailable, never a 0-match refutation.
    # None of these relationships is an EXACT verdict.
    task_recs = [r for r in tools if _is_task(r)]
    inner = [r for r in tools if not _is_task(r)]
    res["task_tool_events"] = len(task_recs)
    start_sids = [_sid(_dict(r.get("ids")).get("subagent_id")) for r in starts]
    start_calls = [_sid(_dict(r.get("ids")).get("tool_call_id")) for r in starts]
    stop_sids = [_sid(_dict(r.get("ids")).get("subagent_id")) for r in stops]
    stop_childs = [_sid(_dict(r.get("ids")).get("child_conversation_id")) for r in stops]
    res["linkage"] = {
        "task_tool_use_id_vs_subagentStart_tool_call_id": membership_link(
            [_sid(_dict(r.get("ids")).get("tool_use_id")) for r in task_recs],
            start_calls,
        ),
        "subagentStart_subagent_id_vs_subagentStart_tool_call_id": pairwise_link(
            zip(start_sids, start_calls)
        ),
        "innerTool_parent_tool_call_id_vs_subagentStart_tool_call_id": membership_link(
            [_sid(_dict(r.get("ids")).get("parent_tool_call_id")) for r in inner],
            start_calls,
        ),
        "subagentStop_subagent_id_vs_subagentStart_subagent_id": membership_link(
            stop_sids, start_sids
        ),
        "subagentStop_subagent_id_vs_subagentStart_tool_call_id": membership_link(
            stop_sids, start_calls
        ),
        "innerTool_conversation_id_vs_subagentStop_child_conversation_id": membership_link(
            [_sid(_dict(r.get("ids")).get("conversation_id")) for r in inner],
            stop_childs,
        ),
    }
    res["linkage_note"] = (
        "Missing values are unavailable, never a 0-match refutation. "
        "subagentStop.subagent_id and child_conversation_id are optional, "
        "empirically observed for Cursor 3.22.7, never required. "
        "Old captures that lack parent_tool_call_id or child_conversation_id "
        "make those relationships unavailable."
    )
    res["session_correlation"] = session_correlation(recs)

    for b in BUCKETS:
        res[b] = dict(buckets[b])
    code, text = identity_verdict(buckets, starts, in_win)
    res["verdict_code"] = code
    res["verdict"] = text
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
    # parallel subagent windows (same pairing as Q1: id when present, else type+order)
    starts = [r for r in recs if r.get("hook_event_name") == "subagentStart"]
    stops = [r for r in recs if r.get("hook_event_name") == "subagentStop"]
    win_overlap = 0
    paired, _ = pair_start_stop(starts, stops)
    wins = [(w["t0"], w["t1"]) for w in paired if w["t0"] is not None and w["t1"] is not None]
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
        "background_lifecycle": background_lifecycle(real),
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
    w("--- Q1 identity of the CURRENT subagent inside its tool hooks (HINT ONLY) ---")
    ai = a["agent_identity"]
    w("  The four categories below are reported separately. parent_conversation_id (and")
    w("  other parent_* identity keys except parent_tool_call_id) or the parent's")
    w("  conversation_id can only ever count as parent_only_identity.")
    w("  parent_tool_call_id is an unclassified deterministic-link candidate, not EXACT")
    w("  and not parent-only until row 8 repetitions verify it. Classify by hand per")
    w("  docs/empirical-test-plan.md row 8; the verdict below is not a result.")
    w("  session_id is session-level correlation and is not an agent-identity candidate.")
    skip = BUCKETS + (
        "verdict", "verdict_code", "linkage", "linkage_note", "session_correlation",
    )
    for k, v in ai.items():
        if k not in skip:
            w("  %s: %s" % (k, v))
    w("  linkage (missing = unavailable, never a 0-match refutation):")
    for name, ev in (ai.get("linkage") or {}).items():
        w("    %s: observed=%d comparable=%d matches=%d mismatches=%d unavailable=%d collisions=%d"
          % (name, ev["observed"], ev["comparable"], ev["matches"], ev["mismatches"],
             ev["unavailable"], ev["collisions"]))
    if ai.get("linkage_note"):
        w("    note: %s" % ai["linkage_note"])
    sc = ai.get("session_correlation") or {}
    w("  session_correlation (not Q1 identity):")
    if sc.get("note"):
        w("    note: %s" % sc["note"])
    for name, ev in sc.items():
        if name == "note" or not isinstance(ev, dict):
            continue
        w("    %s: observed=%d comparable=%d matches=%d mismatches=%d unavailable=%d collisions=%d"
          % (name, ev["observed"], ev["comparable"], ev["matches"], ev["mismatches"],
             ev["unavailable"], ev["collisions"]))
    for b in BUCKETS:
        w("  %s: %s" % (b, ai[b] or "(none)"))
    w("  VERDICT: %s" % ai["verdict"])
    w("")
    w("--- background flags and lifecycle completeness ---")
    bl = a["background_lifecycle"]
    bg = bl["task_run_in_background"]
    pw = bl["subagentStart_is_parallel_worker"]
    lc = bl["lifecycle_completeness"]
    w("  task_run_in_background: true=%d false=%d missing=%d"
      % (bg["true"], bg["false"], bg["missing"]))
    w("  subagentStart_is_parallel_worker: true=%d false=%d missing=%d"
      % (pw["true"], pw["false"], pw["missing"]))
    w("  tool_outcomes_by_event_and_tool:")
    outcomes = bl["tool_outcomes_by_event_and_tool"]
    if outcomes:
        for ev, tools in outcomes.items():
            w("    %s: %s" % (ev, " ".join("%s=%d" % (n, c) for n, c in sorted(tools.items()))))
    else:
        w("    (none)")
    w("  lifecycle_completeness: starts=%d matched_stops=%d unmatched_starts=%d"
      % (lc["starts"], lc["matched_stops"], lc["unmatched_starts"]))
    if bl.get("note"):
        w("  note: %s" % bl["note"])
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
