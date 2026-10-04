#!/usr/bin/env python3
"""CursorFleet M0a spike: passive, privacy-preserving Cursor hook capture.

THROWAWAY spike code. Stdlib only. Not product code.

Usage as a Cursor hook (stdin = hook JSON):
    python3 capture_hook.py [<hook_event_name_hint>]

Behaviour:
- Reads the hook JSON from stdin, appends exactly ONE sanitized JSON line to
  <capture dir>/captures.jsonl, prints `{}` (or `{"permission":"allow"}` for
  permission hooks) on stdout and ALWAYS exits 0 (fails open on any error).
- Capture dir: $CURSORFLEET_SPIKE_DIR, else `<git-common-dir>/cursorfleet-spike/`
  (shared by all linked worktrees), else a per-user temp dir.

What is recorded (allowlist, nothing else):
- hook_event_name (only if it is a known Cursor hook name)
- wall-clock + monotonic timing, in-process latency, stdin read time, pid/ppid
- key-shape: key names (lowercase snake_case only) and value TYPES; for a few
  structural keys (tool_input, edits, ...) also nested key names and types
- values ONLY for: IDs (conversation_id, generation_id, session_id,
  subagent_id, subagent_type, parent_conversation_id, parent_tool_call_id,
  child_conversation_id, tool_use_id, tool_call_id, tool_name, git_branch,
  cursor_version), small enums (status, reason, ...), booleans, and
  numbers (durations/counters). parent_tool_call_id and child_conversation_id
  are optional opaque scalars, stored only when they are valid bounded
  identifier strings (same treatment as tool_call_id / subagent_id).
- cwd / workspace_roots / CURSOR_PROJECT_DIR reduced to basename + git kind
  (main | linked-worktree | submodule-or-other | none)

What is NEVER recorded: prompts, thinking/response text, file contents,
commands, tool inputs/outputs, edits, summaries, tasks, emails,
transcript paths, full paths.

Other modes:
    --selftest              run the privacy/latency self-test and exit
    --set-label NAME        write LABEL file in the capture dir (e.g. ide, cli,
                            agents-window); the label is stamped on each record
    --print-capture-dir     print the resolved capture directory
"""
import time

_T0_MONO = time.monotonic()
_T0_WALL = time.time()

import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402

SCHEMA = 1
CAPTURE_FILE = "captures.jsonl"
DEFAULT_MAX_STDIN = 8 * 1024 * 1024

PERMISSION_HOOKS = frozenset(
    {
        "beforeShellExecution",
        "beforeMCPExecution",
        "beforeReadFile",
        "beforeTabFileRead",
        "subagentStart",
        "preToolUse",
    }
)

KNOWN_EVENTS = frozenset(
    {
        "sessionStart",
        "sessionEnd",
        "preToolUse",
        "postToolUse",
        "postToolUseFailure",
        "subagentStart",
        "subagentStop",
        "beforeShellExecution",
        "afterShellExecution",
        "beforeMCPExecution",
        "afterMCPExecution",
        "beforeReadFile",
        "afterFileEdit",
        "beforeSubmitPrompt",
        "preCompact",
        "stop",
        "afterAgentResponse",
        "afterAgentThought",
        "beforeTabFileRead",
        "afterTabFileEdit",
        "workspaceOpen",
    }
)

ID_FIELDS = (
    "conversation_id",
    "generation_id",
    "session_id",
    "subagent_id",
    "subagent_type",
    "parent_conversation_id",
    "parent_tool_call_id",
    "child_conversation_id",
    "tool_use_id",
    "tool_call_id",
    "tool_name",
    "git_branch",
    "cursor_version",
)
ID_RE = re.compile(r"^[A-Za-z0-9_.:/+\-]{1,128}$")  # no '@' (emails), no spaces

ENUM_FIELDS = {
    "status": {"completed", "aborted", "error"},
    "failure_type": {"timeout", "error", "permission_denied"},
    "trigger": {"auto", "manual"},
    "composer_mode": {"agent", "ask", "edit"},
    "reason": {"completed", "aborted", "error", "window_close", "user_close"},
}
BOOL_FIELDS = (
    "is_parallel_worker",
    "is_background_agent",
    "is_first_compaction",
    "is_interrupt",
    "sandbox",
    "run_in_background",
)
NUM_FIELDS = (
    "duration",
    "duration_ms",
    "tool_call_count",
    "message_count",
    "loop_count",
    "context_usage_percent",
    "context_tokens",
    "context_window_size",
    "messages_to_compact",
)
# Only these structural keys get nested key-name/type shape recorded.
NESTED_SHAPE_KEYS = frozenset(
    {"tool_input", "edits", "model_params", "attachments", "modified_files"}
)
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
LABEL_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,32}$")
BASENAME_RE = re.compile(r"^[A-Za-z0-9_.+\- ]{1,64}$")  # rejects '@' and path seps
ENV_NAME_RE = re.compile(r"^(CURSOR|CLAUDE)_[A-Z0-9_]{1,48}$")


# ---------------------------------------------------------------- helpers


def _tname(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return "other"


def _safe_key(k):
    return k if isinstance(k, str) and KEY_RE.match(k) else "<odd-key>"


def _describe(v, nested):
    t = _tname(v)
    if t == "dict" and nested:
        keys = {}
        for k, x in list(v.items())[:40]:
            keys[_safe_key(k)] = _tname(x)
        return {"t": "dict", "keys": dict(sorted(keys.items()))}
    if t == "list":
        d = {"t": "list", "n": min(len(v), 1000)}
        if nested and v:
            d["item_types"] = sorted({_tname(x) for x in v[:50]})
            item_keys = {}
            for x in v[:50]:
                if isinstance(x, dict):
                    for k, y in list(x.items())[:40]:
                        item_keys.setdefault(_safe_key(k), _tname(y))
            if item_keys:
                d["item_keys"] = dict(sorted(item_keys.items()))
        return d
    return t


def key_shape(payload):
    shape = {}
    for k, v in list(payload.items())[:64]:
        sk = _safe_key(k)
        shape[sk] = _describe(v, sk in NESTED_SHAPE_KEYS)
    return dict(sorted(shape.items()))


def safe_basename(p):
    if not isinstance(p, str) or not p:
        return None
    p = p.replace("\\", "/").rstrip("/")
    b = p.rsplit("/", 1)[-1]
    if b and BASENAME_RE.match(b):
        return b
    return "<redacted-name>"


def _read_small(path, limit=4096):
    with open(path, "rb") as f:
        return f.read(limit).decode("utf-8", "replace")


def find_git_entry(start):
    """Walk up from `start`; return path of the first `.git` entry or None."""
    try:
        cur = os.path.abspath(start)
    except Exception:
        return None
    for _ in range(40):
        cand = os.path.join(cur, ".git")
        if os.path.lexists(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    return None


def git_info(start):
    """Return (kind, common_dir). kind in none|main|linked-worktree|submodule-or-other."""
    if not isinstance(start, str) or not start:
        return "none", None
    try:
        entry = find_git_entry(start)
        if entry is None:
            return "none", None
        if os.path.isdir(entry):
            return "main", entry
        line = _read_small(entry).strip().splitlines()[0]
        if not line.startswith("gitdir:"):
            return "submodule-or-other", None
        gitdir = line[len("gitdir:") :].strip()
        if not os.path.isabs(gitdir):
            gitdir = os.path.normpath(os.path.join(os.path.dirname(entry), gitdir))
        norm = gitdir.replace("\\", "/")
        commondir_file = os.path.join(gitdir, "commondir")
        if "/worktrees/" in norm and os.path.exists(commondir_file):
            cd = _read_small(commondir_file).strip()
            if not os.path.isabs(cd):
                cd = os.path.normpath(os.path.join(gitdir, cd))
            return "linked-worktree", cd
        return "submodule-or-other", gitdir
    except Exception:
        return "none", None


def resolve_capture_dir(payload=None):
    env = os.environ.get("CURSORFLEET_SPIKE_DIR")
    if env:
        return env, "env"
    cands = [os.getcwd()]
    if isinstance(payload, dict):
        wr = payload.get("workspace_roots")
        if isinstance(wr, list) and wr and isinstance(wr[0], str):
            cands.append(wr[0])
    pd = os.environ.get("CURSOR_PROJECT_DIR")
    if pd:
        cands.append(pd)
    for c in cands:
        _kind, common = git_info(c)
        if common:
            return os.path.join(common, "cursorfleet-spike"), "git-common-dir"
    import tempfile

    uid = os.getuid() if hasattr(os, "getuid") else "u"
    return os.path.join(tempfile.gettempdir(), "cursorfleet-spike-%s" % uid), "fallback-tmp"


def path_info(p):
    kind, _ = git_info(p)
    return {"base": safe_basename(p), "git_kind": kind}


def read_label(cap_dir):
    try:
        v = _read_small(os.path.join(cap_dir, "LABEL"), 128).strip().splitlines()[0]
        return v if LABEL_RE.match(v) else None
    except Exception:
        return None


def response_for(event):
    return '{"permission":"allow"}' if event in PERMISSION_HOOKS else "{}"


def read_stdin(max_bytes):
    """Return (bytes, truncated, read_ms). Drains stdin even if over the cap."""
    t = time.monotonic()
    if sys.stdin is None or sys.stdin.isatty():
        return b"", False, 0.0
    buf = sys.stdin.buffer
    chunks, total, truncated = [], 0, False
    while True:
        c = buf.read(65536)
        if not c:
            break
        total += len(c)
        if total <= max_bytes:
            chunks.append(c)
        else:
            truncated = True
    return b"".join(chunks), truncated, (time.monotonic() - t) * 1000.0


def build_record(payload, hint, raw_len, truncated, parse_ok, stdin_ms, cap_dir, cap_src):
    rec = {
        "schema": SCHEMA,
        "start_epoch_ms": round(_T0_WALL * 1000.0, 3),
        "mono_start_ms": round(_T0_MONO * 1000.0, 3),
        "pid": os.getpid(),
        "ppid": os.getppid() if hasattr(os, "getppid") else None,
        "py": "%d.%d.%d" % sys.version_info[:3],
        "platform": sys.platform,
        "capture_dir_source": cap_src,
        "stdin_bytes": raw_len,
        "stdin_truncated": truncated,
        "stdin_read_ms": round(stdin_ms, 3),
        "parse_ok": parse_ok,
        "label": read_label(cap_dir),
    }
    event = None
    if isinstance(payload, dict):
        he = payload.get("hook_event_name")
        event = he if he in KNOWN_EVENTS else None
        rec["hook_event_name"] = event if event else "<unknown>"
        if isinstance(he, str) and event is None:
            rec["hook_event_name_valid"] = False
    else:
        rec["hook_event_name"] = None
    rec["event_hint"] = hint if hint in KNOWN_EVENTS else None
    if hint and event and hint != event:
        rec["hint_mismatch"] = True

    env_names = sorted(k for k in os.environ if ENV_NAME_RE.match(k))[:40]
    rec["env_names"] = env_names
    rec["cursor_project_dir"] = (
        path_info(os.environ["CURSOR_PROJECT_DIR"]) if os.environ.get("CURSOR_PROJECT_DIR") else None
    )
    rec["proc_cwd"] = path_info(os.getcwd())

    if isinstance(payload, dict):
        rec["keys"] = key_shape(payload)
        ids = {}
        for f in ID_FIELDS:
            if f in payload:
                v = payload[f]
                if isinstance(v, str) and ID_RE.match(v):
                    ids[f] = v
                elif v is None:
                    ids[f] = None
                else:
                    ids[f] = "<invalid>"
        rec["ids"] = ids
        vals = {}
        for f, allowed in ENUM_FIELDS.items():
            if f in payload:
                v = payload[f]
                vals[f] = v if isinstance(v, str) and v in allowed else "<other>"
        for f in BOOL_FIELDS:
            if f in payload and isinstance(payload[f], bool):
                vals[f] = payload[f]
        # Nested Task boolean only; never store any other tool_input value.
        ti = payload.get("tool_input")
        if (
            isinstance(ti, dict)
            and isinstance(ti.get("run_in_background"), bool)
            and "run_in_background" not in vals
        ):
            vals["run_in_background"] = ti["run_in_background"]
        for f in NUM_FIELDS:
            v = payload.get(f)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals[f] = v
        rec["vals"] = vals
        cwd = payload.get("cwd")
        rec["cwd"] = path_info(cwd) if isinstance(cwd, str) else None
        wr = payload.get("workspace_roots")
        if isinstance(wr, list):
            rec["workspace_roots"] = [path_info(x) for x in wr[:8] if isinstance(x, str)]
            rec["workspace_roots_n"] = len(wr)
    return rec, event


def append_line(cap_dir, line):
    os.makedirs(cap_dir, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(cap_dir, CAPTURE_FILE), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line)  # single write => atomic-ish append for lines < PIPE_BUF-ish
    finally:
        os.close(fd)


def hook_main(argv):
    hint = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else None
    out = response_for(hint if hint in KNOWN_EVENTS else None)
    try:
        max_bytes = int(os.environ.get("CURSORFLEET_SPIKE_MAX_STDIN", DEFAULT_MAX_STDIN))
        raw, truncated, stdin_ms = read_stdin(max_bytes)
        payload, parse_ok = None, False
        if raw and not truncated:
            try:
                payload = json.loads(raw.decode("utf-8", "replace"))
                parse_ok = True
            except Exception:
                payload = None
        cap_dir, cap_src = resolve_capture_dir(payload)
        rec, event = build_record(
            payload, hint, len(raw), truncated, parse_ok, stdin_ms, cap_dir, cap_src
        )
        out = response_for(event or (hint if hint in KNOWN_EVENTS else None))
        end_mono = time.monotonic()
        rec["mono_end_ms"] = round(end_mono * 1000.0, 3)
        rec["end_epoch_ms"] = round(time.time() * 1000.0, 3)
        rec["latency_ms"] = round((end_mono - _T0_MONO) * 1000.0, 3)
        rec["latency_excludes_final_write"] = True
        append_line(cap_dir, (json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    except Exception as exc:  # fail open
        try:
            cap_dir, _ = resolve_capture_dir(None)
            err = {
                "schema": SCHEMA,
                "hook_event_name": "<internal-error>",
                "error_class": type(exc).__name__,  # class only, never the message
                "start_epoch_ms": round(_T0_WALL * 1000.0, 3),
                "pid": os.getpid(),
            }
            append_line(cap_dir, (json.dumps(err, sort_keys=True) + "\n").encode("utf-8"))
        except Exception:
            pass
    try:
        sys.stdout.write(out + "\n")
        sys.stdout.flush()
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------- selftest

SECRETS = [
    "sk-live-SYNTHETICSECRET0123456789",
    "ghp_SYNTHETICGITHUBTOKEN0123456789",
    "alice.synthetic@example.com",
    "hunter2-synthetic-password",
    "AKIASYNTHETICAWSKEY12345",
    "BEGIN-SYNTHETIC-PRIVATE-KEY",
    "/home/alice-synthetic/private",
    "synthetic prompt text about quarterly layoffs",
    "synthetic chain of thought about the password",
]


def _synthetic_payloads():
    s = SECRETS
    base = {
        "conversation_id": "conv-selftest-1",
        "generation_id": "gen-selftest-1",
        "model": "synthetic-model",
        "model_id": "synthetic",
        "model_params": [{"id": "thinking", "value": s[1]}],
        "cursor_version": "9.9.9",
        "workspace_roots": ["/home/alice-synthetic/private/proj", "/tmp/" + s[2]],
        "user_email": s[2],
        "transcript_path": s[6] + "/transcript.jsonl",
    }

    def mk(event, **extra):
        d = dict(base)
        d["hook_event_name"] = event
        d.update(extra)
        return d

    return [
        mk("sessionStart", session_id="conv-selftest-1", is_background_agent=False,
           composer_mode="agent"),
        mk("preToolUse", tool_name="Shell", tool_use_id="tu-1", cwd="/home/alice-synthetic/private",
           parent_tool_call_id="tc_synthetic_selftest",
           tool_input={"command": "curl -H 'Authorization: %s' https://x" % s[0],
                       "working_directory": s[6], s[0]: "weird-key-with-secret-name"},
           agent_message=s[8], task=s[7], prompt=s[7]),
        mk("preToolUse", tool_name="Task", tool_use_id="tu-task-bg",
           tool_input={"run_in_background": True, "description": "synthetic-task"}),
        mk("postToolUse", tool_name="Shell", tool_use_id="tu-1", cwd="/tmp/" + s[2],
           tool_input={"command": s[3]}, tool_output=json.dumps({"stdout": s[1]}), duration=12),
        mk("postToolUseFailure", tool_name="Shell", tool_use_id="tu-2", error_message=s[0],
           failure_type="error", duration=5, is_interrupt=False, tool_input={"command": s[4]}),
        mk("subagentStart", subagent_id="sub-1", subagent_type="my-custom-agent",
           task=s[7], parent_conversation_id="conv-selftest-1", tool_call_id="tc-1",
           subagent_model="m", is_parallel_worker=True, git_branch="feature/" + s[2]),
        mk("subagentStop", subagent_id="sub-1", subagent_type="my-custom-agent",
           status="completed", task=s[7], child_conversation_id="ses_synthetic_child",
           description=s[8], summary=s[0] + s[5], duration_ms=10, message_count=2,
           tool_call_count=1, loop_count=0, modified_files=[s[6] + "/a.py"],
           agent_transcript_path=s[6] + "/t.txt"),
        mk("beforeShellExecution", command="echo " + s[3], cwd=s[6], sandbox=False),
        mk("afterShellExecution", command="echo " + s[3], output=s[1] + "\n" + s[4], duration=3,
           sandbox=False),
        mk("afterFileEdit", file_path=s[6] + "/.env",
           edits=[{"old_string": s[3], "new_string": s[0]}]),
        mk("preCompact", trigger="auto", context_usage_percent=85, context_tokens=1000,
           context_window_size=2000, message_count=3, messages_to_compact=2,
           is_first_compaction=True),
        mk("stop", status="completed", loop_count=0),
        mk("sessionEnd", session_id="conv-selftest-1", reason="completed", duration_ms=5,
           is_background_agent=False, final_status="done", error_message=s[0]),
        # not registered by CursorFleet, but must still never be stored if misconfigured:
        mk("beforeSubmitPrompt", prompt=s[7], attachments=[{"type": "file", "file_path": s[6]}]),
        mk("afterAgentThought", text=s[8], duration_ms=7),
        mk("afterAgentResponse", text=s[7]),
        mk("beforeReadFile", file_path=s[6] + "/.env", content=s[0] + s[3]),
        # hostile: invalid IDs / enums / event name carrying secrets
        mk("preToolUse", tool_name=s[2], tool_use_id="tu 3 with spaces " + s[3], cwd=s[6]),
        mk(s[0], status=s[7], reason=s[8]),
        # optional opaque IDs: valid scalars kept; invalid / oversized / non-string rejected
        mk("preToolUse", tool_name="Read", tool_use_id="tu-inner-ok",
           parent_tool_call_id="tc_synthetic_ok",
           tool_input={"command": s[3], "path": s[6] + "/secret.txt"},
           prompt=s[7], task=s[7], user_email=s[2]),
        mk("subagentStop", subagent_type="explore", status="completed",
           child_conversation_id="ses_synthetic_ok", task=s[7], summary=s[8]),
        mk("preToolUse", tool_name="Read", tool_use_id="tu-inner-bad",
           parent_tool_call_id=s[2],
           child_conversation_id="ses " + s[3]),
        mk("subagentStop", subagent_type="explore", status="completed",
           child_conversation_id="x" * 129, parent_tool_call_id=12345, task=s[7]),
        mk("preToolUse", tool_name="Read", tool_use_id="tu-inner-obj",
           parent_tool_call_id={"wrapped": "tc_synthetic_nested", "task": s[7]},
           child_conversation_id=["ses_synthetic_list", s[2]]),
    ]


def _run_hook(args, stdin_bytes, env, cwd=None):
    import subprocess

    return subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + args,
        input=stdin_bytes, capture_output=True, env=env, cwd=cwd, timeout=60,
    )


def selftest():
    import shutil
    import subprocess
    import tempfile

    failures = []
    checks = [0]

    def check(cond, msg):
        checks[0] += 1
        if not cond:
            failures.append(msg)
            print("  FAIL: " + msg)

    tmp = tempfile.mkdtemp(prefix="cf-spike-selftest-")
    try:
        # ---- 1. synthetic payloads, explicit capture dir
        cap = os.path.join(tmp, "cap1")
        env = dict(os.environ, CURSORFLEET_SPIKE_DIR=cap)
        payloads = _synthetic_payloads()
        for p in payloads:
            r = _run_hook([], json.dumps(p).encode(), env)
            check(r.returncode == 0, "exit 0 for %s" % p["hook_event_name"][:20])
            want = response_for(p["hook_event_name"])
            check(r.stdout.decode().strip() == want, "stdout %r for %s" % (want, p["hook_event_name"][:20]))
            check(r.stderr == b"", "no stderr output for %s" % p["hook_event_name"][:20])
        path = os.path.join(cap, CAPTURE_FILE)
        text = open(path, encoding="utf-8").read()
        lines = text.splitlines()
        check(len(lines) == len(payloads), "one line per call (%d != %d)" % (len(lines), len(payloads)))
        for sec in SECRETS:
            check(sec not in text, "secret leaked into capture file: %r" % sec[:20])
        for frag in ("/home/alice", "alice-synthetic", "example.com", "curl -H", "Authorization"):
            check(frag not in text, "fragment leaked: %r" % frag)
        recs = [json.loads(l) for l in lines]
        for rec in recs:
            for k in ("latency_ms", "mono_start_ms", "mono_end_ms", "start_epoch_ms", "end_epoch_ms"):
                check(isinstance(rec.get(k), (int, float)), "%s recorded" % k)
            check(rec["latency_ms"] >= 0 and rec["mono_end_ms"] >= rec["mono_start_ms"], "latency sane")
            check(rec["end_epoch_ms"] >= rec["start_epoch_ms"], "wall end >= start")
        by_event = {}
        for rec in recs:
            by_event.setdefault(rec["hook_event_name"], rec)
        sub = by_event["subagentStart"]
        check(sub["ids"]["subagent_id"] == "sub-1", "subagent_id recorded")
        check(sub["ids"]["subagent_type"] == "my-custom-agent", "subagent_type recorded")
        check(sub["ids"]["parent_conversation_id"] == "conv-selftest-1", "parent id recorded")
        check(sub["ids"]["git_branch"] == "<invalid>", "email-like branch rejected")
        check(sub["keys"]["task"] == "str", "key-shape records type of task, not value")
        check("task" not in sub.get("vals", {}), "task value not stored")
        check(sub["vals"]["is_parallel_worker"] is True, "bool value recorded")
        ptu = [r for r in recs if r["hook_event_name"] == "preToolUse"][0]
        check(ptu["keys"]["tool_input"]["keys"].get("command") == "str", "nested key name+type recorded")
        check("<odd-key>" in ptu["keys"]["tool_input"]["keys"], "secret-named nested key masked")
        check(ptu["cwd"]["base"] == "private", "cwd reduced to basename")
        check(ptu["workspace_roots"][0]["base"] == "proj", "workspace root reduced to basename")
        check(ptu["workspace_roots"][1]["base"] == "<redacted-name>", "email-like basename redacted")
        check(ptu["ids"]["parent_tool_call_id"] == "tc_synthetic_selftest",
              "valid parent_tool_call_id retained")
        task_bg = [r for r in recs if (r.get("ids") or {}).get("tool_name") == "Task"]
        check(len(task_bg) == 1, "Task payload captured")
        check(task_bg[0]["vals"].get("run_in_background") is True,
              "nested run_in_background bool recorded")
        check("description" not in task_bg[0].get("vals", {}), "Task description not stored")
        stop0 = by_event["subagentStop"]
        check(stop0["ids"]["child_conversation_id"] == "ses_synthetic_child",
              "valid child_conversation_id retained")
        check(stop0["ids"]["subagent_id"] == "sub-1", "optional stop subagent_id retained")
        check("task" not in stop0.get("vals", {}), "stop task value not stored")
        ok_ptc = [r for r in recs if (r.get("ids") or {}).get("parent_tool_call_id") == "tc_synthetic_ok"]
        check(len(ok_ptc) == 1, "second valid parent_tool_call_id retained")
        ok_child = [r for r in recs if (r.get("ids") or {}).get("child_conversation_id") == "ses_synthetic_ok"]
        check(len(ok_child) == 1, "second valid child_conversation_id retained")
        for rec in recs:
            ids = rec.get("ids") or {}
            for banned in ("task", "prompt", "tool_input", "tool_output", "user_email",
                           "file_path", "command", "summary", "description"):
                check(banned not in ids, "payload field %s must not be stored in ids" % banned)
        check("tc_synthetic_nested" not in text, "object parent_tool_call_id value not copied")
        check("ses_synthetic_list" not in text, "list child_conversation_id value not copied")
        invalid_new = []
        for rec in recs:
            ids = rec.get("ids") or {}
            if ids.get("parent_tool_call_id") == "<invalid>" or ids.get("child_conversation_id") == "<invalid>":
                invalid_new.append(rec)
        check(len(invalid_new) >= 3, "invalid/oversized/non-string new IDs rejected (%d)" % len(invalid_new))
        oversize = [r for r in recs if (r.get("ids") or {}).get("child_conversation_id") == "<invalid>"
                    and (r.get("ids") or {}).get("parent_tool_call_id") == "<invalid>"
                    and r["hook_event_name"] == "subagentStop"]
        check(len(oversize) == 1, "oversized child_conversation_id and non-string parent_tool_call_id rejected")
        check(by_event["preCompact"]["vals"]["context_tokens"] == 1000, "preCompact numerics recorded")
        check("<unknown>" in by_event, "unknown/hostile event name masked")
        hostile = [r for r in recs if r["hook_event_name"] == "<unknown>"][0]
        check(hostile["vals"]["status"] == "<other>", "hostile enum masked")
        check(hostile["hook_event_name_valid"] is False, "invalid event flagged")
        bad_tool = [r for r in recs if r["hook_event_name"] == "preToolUse"
                    and (r.get("ids") or {}).get("tool_name") == "<invalid>"
                    and (r.get("ids") or {}).get("tool_use_id") == "<invalid>"]
        check(len(bad_tool) == 1, "email-like tool_name and spaced tool_use_id rejected")

        # ---- 2. malformed / empty / truncated stdin: fail open, permission hint honoured
        cap2 = os.path.join(tmp, "cap2")
        env2 = dict(os.environ, CURSORFLEET_SPIKE_DIR=cap2)
        r = _run_hook(["preToolUse"], b"{not json " + SECRETS[0].encode(), env2)
        check(r.returncode == 0 and r.stdout.decode().strip() == '{"permission":"allow"}',
              "malformed JSON + permission hint fails open with allow")
        r = _run_hook([], b"", env2)
        check(r.returncode == 0 and r.stdout.decode().strip() == "{}", "empty stdin => {} exit 0")
        r = _run_hook(["stop"], b"[1,2,3]", env2)
        check(r.returncode == 0 and r.stdout.decode().strip() == "{}", "non-object JSON => {}")
        env2b = dict(env2, CURSORFLEET_SPIKE_MAX_STDIN="100")
        big = json.dumps({"hook_event_name": "preToolUse", "tool_input": {"command": SECRETS[0] * 50}}).encode()
        r = _run_hook([], big, env2b)
        check(r.returncode == 0, "oversize stdin exit 0")
        t2 = open(os.path.join(cap2, CAPTURE_FILE), encoding="utf-8").read()
        check(SECRETS[0] not in t2, "malformed/oversize input leaked secret")
        check(all(json.loads(l) for l in t2.splitlines()), "every line valid JSON")
        check(any(json.loads(l).get("stdin_truncated") for l in t2.splitlines()), "truncation flagged")
        check(any(json.loads(l).get("parse_ok") is False for l in t2.splitlines()), "parse failure flagged")

        # ---- 3. unwritable capture dir: fail open
        blocker = os.path.join(tmp, "blocker")
        open(blocker, "w").close()
        env3 = dict(os.environ, CURSORFLEET_SPIKE_DIR=os.path.join(blocker, "sub"))
        r = _run_hook([], json.dumps(payloads[1]).encode(), env3)
        check(r.returncode == 0 and r.stdout.decode().strip() == '{"permission":"allow"}',
              "unwritable dir fails open")

        # ---- 4. fake linked worktree: capture dir resolves to common dir; flags set
        main = os.path.join(tmp, "main")
        wt = os.path.join(tmp, "wt1")
        gitdir = os.path.join(main, ".git", "worktrees", "wt1")
        os.makedirs(gitdir)
        os.makedirs(wt)
        with open(os.path.join(gitdir, "commondir"), "w") as f:
            f.write("../..\n")
        with open(os.path.join(wt, ".git"), "w") as f:
            f.write("gitdir: %s\n" % gitdir)
        env4 = {k: v for k, v in os.environ.items() if k != "CURSORFLEET_SPIKE_DIR"}
        p = dict(payloads[1], workspace_roots=[wt], cwd=wt)
        r = _run_hook([], json.dumps(p).encode(), env4, cwd=wt)
        check(r.returncode == 0, "worktree run exit 0")
        f4 = os.path.join(main, ".git", "cursorfleet-spike", CAPTURE_FILE)
        check(os.path.exists(f4), "capture dir resolved to <git-common-dir>/cursorfleet-spike")
        if os.path.exists(f4):
            rec = json.loads(open(f4, encoding="utf-8").read().splitlines()[0])
            check(rec["capture_dir_source"] == "git-common-dir", "source recorded")
            check(rec["workspace_roots"][0]["git_kind"] == "linked-worktree", "linked worktree flagged")
            check(rec["cwd"]["git_kind"] == "linked-worktree", "cwd linked worktree flagged")
            check(rec["workspace_roots"][0]["base"] == "wt1", "worktree basename")
        pm = dict(payloads[1], workspace_roots=[main], cwd=main)
        _run_hook([], json.dumps(pm).encode(), env4, cwd=main)
        recs4 = [json.loads(l) for l in open(f4, encoding="utf-8").read().splitlines()]
        check(len(recs4) == 2 and recs4[1]["workspace_roots"][0]["git_kind"] == "main",
              "main checkout flagged as main, same capture file")

        # ---- 5. real git worktree if git exists
        if shutil.which("git"):
            real = os.path.join(tmp, "real")
            os.makedirs(real)
            gi = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid",
                      GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid",
                      GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
            try:
                for a in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"],
                          ["worktree", "add", "-q", os.path.join(tmp, "real-wt")]):
                    subprocess.run(["git"] + a, cwd=real, env=gi, check=True, capture_output=True)
                rwt = os.path.join(tmp, "real-wt")
                p = dict(payloads[1], workspace_roots=[rwt], cwd=rwt)
                _run_hook([], json.dumps(p).encode(), env4, cwd=rwt)
                fr = os.path.join(real, ".git", "cursorfleet-spike", CAPTURE_FILE)
                check(os.path.exists(fr), "real git worktree resolves to main .git common dir")
                if os.path.exists(fr):
                    rec = json.loads(open(fr, encoding="utf-8").read().splitlines()[0])
                    check(rec["cwd"]["git_kind"] == "linked-worktree", "real linked worktree detected")
            except subprocess.CalledProcessError as e:
                print("  (skipped real-git check: git failed: %s)" % e.returncode)
        else:
            print("  (skipped real-git check: git not installed)")

        # ---- 6. label file
        cap6 = os.path.join(tmp, "cap6")
        env6 = dict(os.environ, CURSORFLEET_SPIKE_DIR=cap6)
        r = _run_hook(["--set-label", "cli"], b"", env6)
        check(r.returncode == 0, "--set-label exit 0")
        _run_hook([], json.dumps(payloads[0]).encode(), env6)
        rec = json.loads(open(os.path.join(cap6, CAPTURE_FILE), encoding="utf-8").read().splitlines()[0])
        check(rec["label"] == "cli", "label stamped on record")

        # ---- 7. doc-derived examples replay (shape only; they contain placeholder text)
        ex_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doc_examples")
        cap7 = os.path.join(tmp, "cap7")
        env7 = dict(os.environ, CURSORFLEET_SPIKE_DIR=cap7)
        n_ex = 0
        if os.path.isdir(ex_dir):
            for name in sorted(os.listdir(ex_dir)):
                if name.endswith(".json"):
                    n_ex += 1
                    data = open(os.path.join(ex_dir, name), "rb").read()
                    r = _run_hook([], data, env7)
                    check(r.returncode == 0, "doc example %s exit 0" % name)
            if n_ex:
                t7 = open(os.path.join(cap7, CAPTURE_FILE), encoding="utf-8").read()
                for frag in ("npm install", "npm test", "SELECT", "src/auth.ts", "Explore the authentication"):
                    check(frag not in t7, "doc example content %r leaked" % frag)
        check(n_ex >= 12, "at least 12 doc-derived examples present (%d)" % n_ex)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("SELFTEST FAILED: %d of %d checks failed" % (len(failures), checks[0]))
        return 1
    print("SELFTEST PASSED: %d checks" % checks[0])
    return 0


def main(argv):
    if len(argv) > 1 and argv[1].startswith("--"):
        if argv[1] == "--selftest":
            return selftest()
        if argv[1] == "--print-capture-dir":
            print(resolve_capture_dir(None)[0])
            return 0
        if argv[1] == "--set-label":
            if len(argv) < 3 or not LABEL_RE.match(argv[2]):
                print("usage: --set-label NAME  (A-Za-z0-9_.- up to 32 chars)", file=sys.stderr)
                return 2
            d, _ = resolve_capture_dir(None)
            os.makedirs(d, mode=0o700, exist_ok=True)
            with open(os.path.join(d, "LABEL"), "w") as f:
                f.write(argv[2] + "\n")
            print("label=%s dir=%s" % (argv[2], d))
            return 0
        print(__doc__)
        return 0
    return hook_main(argv)


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except Exception:
        rc = 0
    sys.exit(rc)
