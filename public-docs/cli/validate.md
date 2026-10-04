# `cursorfleet validate`

```bash
cursorfleet validate [--json] [--path DIR]
```

Read-only check of committed config, the roster, generated kit files, and
work artifacts. It never writes.

| Option | Default | Meaning |
| --- | --- | --- |
| `--json` | off | Machine-readable report (`schema`: `cursorfleet.validate/1`). |
| `--path DIR` | cwd | A directory inside the Git repo. |

Exit **1** if any finding is an error. Warnings do not fail the command.

Like [`doctor`](doctor.md), `validate` may run from a subdirectory. It
prints the same repository resolution (input, realpath, root, common dir,
marker, boundary, status) and never walks past an inner Git boundary.

## What it checks

- **Config** (`.cursorfleet/config.toml`) and **roster**
  (`.cursorfleet/roster.toml`) against the models.
- **Roster consistency:** unique Cursor subagent names; the coordinator is
  not a subagent file; empty enabled set is a warning.
- **Generated files** and managed `AGENTS.md` blocks against the templates
  (drift versus the install lockfile).
- **Subagent frontmatter** keys (only `name`, `description`, `model`,
  `readonly`, `is_background`).
- **Rules:** `.mdc` extension, frontmatter, and length (strictly under 500
  lines).
- **Skills:** frontmatter.
- **Work artifacts** under the work directory (size, frontmatter, paths).

Findings in CursorFleet's own generated files are **errors**. Findings in
your own rules or agents are **warnings**.

If resolution itself fails, `validate` adds a `repo.resolution` error and
still inspects the given directory as-is.

`--json` includes `ok`, `counts`, `stats`, `resolution`, and `findings`.
