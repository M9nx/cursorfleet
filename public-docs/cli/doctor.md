# `cursorfleet doctor`

```bash
cursorfleet doctor [--json] [--path DIR] [--no-probe-cursor]
```

Read-only environment, install, and hook diagnostics. It never writes.

| Option | Default | Meaning |
| --- | --- | --- |
| `--json` | off | Machine-readable report (`schema`: `cursorfleet.doctor/1`). |
| `--path DIR` | cwd | A directory inside the Git repo. |
| `--probe-cursor` / `--no-probe-cursor` | probe on | When on, run `cursor --version` (argv list, 5 s timeout) if `CURSOR_VERSION` is unset. |

Exit **0** when no check is `fail` (warnings are fine). Exit **1** otherwise,
including when the path is not inside Git (`git.repo` failed).

Unlike [`init`](init.md), `doctor` may be run from a subdirectory. It
resolves the enclosing repository and **prints the resolution** it used.

## Resolution report

Plain text starts with a `Repository resolution:` block. `--json` includes
the same mapping under `resolution`. Fields:

| Field | Meaning |
| --- | --- |
| `input_path` | The path you passed (or the current directory). |
| `resolved_path` | That path after realpath. |
| `repository_root` | Detected Git top level, or null. |
| `common_dir` | `git-common-dir` of that root, or null. |
| `marker_path` | Expected `.cursorfleet/config.toml` at the detected root. |
| `marker_present` | Whether that path exists. |
| `marker_valid` | Whether it is a regular file after realpath (symlink-to-elsewhere is refused). |
| `boundary` | How the walk classified the path. |
| `status` | `ok` or `fail`. |
| `reason` | Short explanation. |

`boundary` values include `repository-root`, `ordinary-descendant`,
`linked-worktree`, `nested-repository`, `submodule`, `non-git`,
`external-symlink`, and `ambiguous-multi-root`.

The walk never continues outward after an inner Git boundary. `doctor`
never creates files or directories.

## What it checks

- Python >= 3.11
- `cursorfleet-hook` on `PATH`
- Git repo and runtime directory (`<git-common-dir>/cursorfleet/`)
- Runtime permissions (0700 / 0600 on POSIX; Windows ACLs best effort)
- Config and roster load
- Install lockfile and drift from it
- Effective hooks at enterprise, team (not visible from disk), project, and
  user level. Content-bearing hooks registered by anyone are a warning.
- Cursor version from `CURSOR_VERSION` or `cursor --version`. The version is
  never invented. Versions not listed in `[cursor].validated_versions` warn
  (PROVISIONAL: no live capture has been reviewed).

`--no-probe-cursor` skips the `cursor --version` subprocess. Use it when
Cursor is not on `PATH` or you do not want a probe.

Team hooks are cloud-distributed and cannot be listed from disk. Enterprise
paths are documented only and unverified on a live machine.
