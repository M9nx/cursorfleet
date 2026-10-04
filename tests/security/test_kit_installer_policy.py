"""Policy tests for the installer: hook allowlist, no content hooks, no network in kit code."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cursorfleet.adapters.cursor import hooksjson
from cursorfleet.adapters.cursor.hook_policy import ALLOWED_V01_HOOKS, FORBIDDEN_HOOKS
from cursorfleet.cli.main import app
from cursorfleet.config.models import FleetConfig, HooksConfig
from kit_helpers import make_repo

ROOT = Path(__file__).resolve().parents[2]


def test_installer_output_never_contains_a_forbidden_hook_name(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "r")
    result = CliRunner().invoke(app, ["init", "--cursor", "--path", str(repo), "--yes"])
    assert result.exit_code == 0
    tree_text = "\n".join(
        p.read_text("utf-8") for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts
    )
    for name in FORBIDDEN_HOOKS:
        assert name not in json.loads((repo / ".cursor/hooks.json").read_text("utf-8"))["hooks"]
        assert name not in result.output.split("Planned changes")[1].split("diff --")[0]
    registered = set(json.loads((repo / ".cursor/hooks.json").read_text("utf-8"))["hooks"])
    assert registered == ALLOWED_V01_HOOKS
    # The generated kit text may *mention* policy elsewhere, but never as a hook key.
    assert not re.search(r'"(' + "|".join(FORBIDDEN_HOOKS) + r')"\s*:', tree_text)


@pytest.mark.parametrize("name", sorted(FORBIDDEN_HOOKS))
def test_config_cannot_request_a_forbidden_hook(name: str) -> None:
    with pytest.raises(ValueError):
        HooksConfig.model_validate({"enabled": [name]})
    with pytest.raises(ValueError):
        FleetConfig.model_validate({"hooks": {"enabled": ["stop", name]}})


def test_default_config_hooks_equal_allowlist() -> None:
    assert set(FleetConfig().hooks.enabled) == ALLOWED_V01_HOOKS


def test_merge_asserts_allowlist_even_when_called_directly() -> None:
    for name in FORBIDDEN_HOOKS:
        with pytest.raises(hooksjson.HooksJsonError):
            hooksjson.merge(None, [name])


def test_hook_entry_template_has_no_fail_closed_or_matcher_or_args() -> None:
    entry = json.loads((ROOT / "templates/cursor/hooks/entry.json").read_text("utf-8"))
    assert entry == {"command": "cursorfleet-hook", "timeout": 5}


KIT_MODULES = (
    "blocks",
    "diagnostics",
    "fsutil",
    "hooksjson",
    "installer",
    "kit",
    "lock",
    "templates",
    "validation",
    "workspace",
)
NETWORK_MODULES = {"socket", "ssl", "http", "urllib", "requests", "httpx", "aiohttp", "ftplib"}


def test_kit_modules_do_not_import_network_libraries() -> None:
    base = ROOT / "src/cursorfleet/adapters/cursor"
    for name in KIT_MODULES:
        tree = ast.parse((base / f"{name}.py").read_text("utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not imported & NETWORK_MODULES, (name, imported & NETWORK_MODULES)


def test_kit_subprocess_calls_use_argv_lists_and_timeouts() -> None:
    base = ROOT / "src/cursorfleet/adapters/cursor"
    for name in KIT_MODULES:
        tree = ast.parse((base / f"{name}.py").read_text("utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
                and node.func.attr in {"run", "Popen", "check_output", "call"}
            ):
                keywords = {k.arg: k.value for k in node.keywords}
                assert "timeout" in keywords, (name, node.lineno)
                assert not (
                    "shell" in keywords
                    and isinstance(keywords["shell"], ast.Constant)
                    and keywords["shell"].value
                )
                assert isinstance(node.args[0], ast.List), (name, node.lineno)


def test_adapter_package_init_stays_import_free() -> None:
    """The hot path imports ``cursorfleet.adapters.cursor``; the kit must not leak into it."""
    code = (
        "import sys\n"
        "import cursorfleet.adapters.cursor.hook_policy\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in {'pydantic','typer','textual'}]\n"
        "assert not bad, bad\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=False
    )
    assert proc.returncode == 0, proc.stderr
