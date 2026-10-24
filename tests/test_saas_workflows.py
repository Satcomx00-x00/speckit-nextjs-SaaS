"""Engine validation of the bundled SaaS workflows and gate check: support.

These workflows shipped for months without ever passing the engine's own
validation (wrong step-field names, fan-out/switch schema drift, gates whose
failure options the engine silently treated as approval). This suite pins
them to the engine schema so that drift is caught at commit time.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from specify_cli.workflows.base import StepContext, StepStatus  # noqa: E402
from specify_cli.workflows.engine import WorkflowEngine  # noqa: E402
from specify_cli.workflows.steps.gate import GateStep  # noqa: E402
from specify_cli.workflows.steps.shell import ShellStep  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
WORKFLOW_IDS = ["speckit", "saas-feature", "hotfix", "migration-only", "feature-research"]


class TestBundledWorkflowsValidate:
    @pytest.mark.parametrize("workflow_id", WORKFLOW_IDS)
    def test_workflow_passes_engine_validation(self, workflow_id, tmp_path):
        engine = WorkflowEngine(tmp_path)
        definition = engine.load_workflow(
            REPO_ROOT / "workflows" / workflow_id / "workflow.yml"
        )
        errors = engine.validate(definition)
        assert errors == [], f"{workflow_id} fails engine validation: {errors}"

    def test_saas_feature_wires_verify_before_review(self):
        content = (REPO_ROOT / "workflows" / "saas-feature" / "workflow.yml").read_text()
        assert "speckit.verify" in content
        assert content.index("speckit.verify") < content.index("id: ready-for-review")

    @pytest.mark.parametrize("workflow_id", ["saas-feature", "hotfix", "migration-only"])
    def test_fork_workflows_include_verify(self, workflow_id):
        content = (REPO_ROOT / "workflows" / workflow_id / "workflow.yml").read_text()
        assert "speckit.verify" in content, f"{workflow_id} lost its verify step"

    def test_feature_research_runs_research_before_specify(self):
        content = (REPO_ROOT / "workflows" / "feature-research" / "workflow.yml").read_text()
        assert content.index("command: speckit.research") < content.index("command: speckit.specify")

    @pytest.mark.parametrize("workflow_id", WORKFLOW_IDS)
    def test_bundled_workflow_is_packaged(self, workflow_id):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text()
        assert f'"workflows/{workflow_id}" = "specify_cli/core_pack/workflows/{workflow_id}"' in pyproject

    @pytest.mark.parametrize("workflow_id", WORKFLOW_IDS)
    def test_bundled_workflow_is_in_catalog(self, workflow_id):
        import json

        catalog = json.loads((REPO_ROOT / "workflows" / "catalog.json").read_text())
        assert workflow_id in catalog["workflows"]

    @pytest.mark.parametrize("workflow_id", ["saas-feature", "hotfix", "migration-only", "feature-research"])
    def test_workflow_uses_only_supported_filters(self, workflow_id):
        """The expression engine knows default/join/map/contains — any other
        filter is silently ignored and leaves the raw value in a shell command
        (migration-only used `replace` and built an invalid branch name)."""
        import re

        content = (REPO_ROOT / "workflows" / workflow_id / "workflow.yml").read_text()
        filters = set(re.findall(r"\{\{[^}]*\|\s*(\w+)", content))
        assert filters <= {"default", "join", "map", "contains"}, filters


class TestShellTimeout:
    def _context(self):
        return StepContext(inputs={}, steps={})

    def test_validate_accepts_integer_timeout(self):
        errors = ShellStep().validate({"id": "s", "type": "shell", "run": "true", "timeout": 1200})
        assert errors == []

    @pytest.mark.parametrize("bad", [0, -5, "600", 1.5, True])
    def test_validate_rejects_bad_timeout(self, bad):
        errors = ShellStep().validate({"id": "s", "type": "shell", "run": "true", "timeout": bad})
        assert any("'timeout'" in e for e in errors)

    def test_timeout_is_honoured(self):
        cmd = f'"{sys.executable}" -c "import time; time.sleep(5)"'
        result = ShellStep().execute({"id": "s", "run": cmd, "timeout": 1}, self._context())
        assert result.status == StepStatus.FAILED
        assert "timed out after 1 seconds" in (result.error or "")


class TestGateCheck:
    def _context(self):
        return StepContext(inputs={}, steps={})

    def test_validate_accepts_check_string(self):
        step = GateStep()
        errors = step.validate(
            {"id": "g", "type": "gate", "message": "m", "check": "true"}
        )
        assert errors == []

    def test_validate_rejects_non_string_check(self):
        step = GateStep()
        errors = step.validate(
            {"id": "g", "type": "gate", "message": "m", "check": ["ls"]}
        )
        assert any("'check' must be a string" in e for e in errors)

    def test_validate_rejects_bad_on_check_fail(self):
        step = GateStep()
        errors = step.validate(
            {"id": "g", "type": "gate", "message": "m", "on_check_fail": "explode"}
        )
        assert any("on_check_fail" in e for e in errors)

    def test_failing_check_blocks_gate(self):
        step = GateStep()
        result = step.execute(
            {"id": "g", "message": "m", "check": "exit 3"}, self._context()
        )
        assert result.status == StepStatus.FAILED
        assert "pre-condition failed" in (result.error or "")
        assert result.output["check"]["exit_code"] == 3

    def test_failing_check_with_warn_does_not_block(self):
        step = GateStep()
        with patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            result = step.execute(
                {
                    "id": "g",
                    "message": "m",
                    "check": "exit 3",
                    "on_check_fail": "warn",
                },
                self._context(),
            )
        # Non-TTY pauses for resume instead of failing
        assert result.status == StepStatus.PAUSED
        assert result.output["check"]["exit_code"] == 3

    def test_passing_check_proceeds_to_prompt(self):
        step = GateStep()
        with patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            result = step.execute(
                {"id": "g", "message": "m", "check": "true"}, self._context()
            )
        assert result.status == StepStatus.PAUSED
        assert result.output["check"]["exit_code"] == 0

    def test_check_failure_blocks_even_when_non_tty(self):
        """CI runs must not pause past a failed machine pre-condition."""
        step = GateStep()
        with patch("sys.stdin") as stdin:
            stdin.isatty.return_value = False
            result = step.execute(
                {"id": "g", "message": "m", "check": "false"}, self._context()
            )
        assert result.status == StepStatus.FAILED


class TestBundledPresetManifestsMatchDisk:
    """Every declared file exists; every command file on disk is declared."""

    @pytest.mark.parametrize("preset_id", ["lean", "nextjs", "delta-global"])
    def test_declared_files_exist(self, preset_id):
        import yaml

        preset_dir = REPO_ROOT / "presets" / preset_id
        data = yaml.safe_load((preset_dir / "preset.yml").read_text())
        missing = [
            t["file"]
            for t in data["provides"]["templates"]
            if not (preset_dir / t["file"]).is_file()
        ]
        assert missing == [], f"{preset_id} declares missing files: {missing}"

    @pytest.mark.parametrize("preset_id", ["nextjs", "delta-global"])
    def test_all_command_files_are_declared(self, preset_id):
        import yaml

        preset_dir = REPO_ROOT / "presets" / preset_id
        data = yaml.safe_load((preset_dir / "preset.yml").read_text())
        declared = {
            t["file"]
            for t in data["provides"]["templates"]
            if t.get("type") == "command"
        }
        on_disk = {
            f"commands/{f.name}" for f in (preset_dir / "commands").glob("*.md")
        }
        undeclared = on_disk - declared
        assert undeclared == set(), (
            f"{preset_id} ships undeclared command files (they would never "
            f"install): {sorted(undeclared)}"
        )


class TestDeltaGlobalMatchesThePlatform:
    """The delta-global preset encodes the real platform (CONVENTIONS.md).
    These tokens belong to the stack it replaced and must not come back."""

    STALE = [
        "orgScopedProcedure",  # tRPC procedure builder — tRPC removed (spec 024)
        "createCaller",  # tRPC server caller
        "ioredis",  # cache is reached through injected redis, not this client
        "retry_label",  # retry copy is an i18n key now
        "Inngest",  # background work is Temporal only
        "scaffold.trpc",
        "ff-[",  # flag keys have no ff- prefix
        "ff-<",
    ]

    def test_no_stale_stack_tokens(self):
        roots = [REPO_ROOT / "presets" / "delta-global"] + [
            REPO_ROOT / "workflows" / w for w in ("saas-feature", "hotfix", "migration-only", "feature-research")
        ]
        hits = []
        for root in roots:
            for f in root.rglob("*"):
                if f.is_file() and f.suffix in {".md", ".yml"}:
                    text = f.read_text(encoding="utf-8")
                    hits += [f"{f.relative_to(REPO_ROOT)}: {t}" for t in self.STALE if t in text]
        assert hits == []

    def test_research_command_is_declared(self):
        import yaml

        data = yaml.safe_load((REPO_ROOT / "presets" / "delta-global" / "preset.yml").read_text())
        names = {t["name"] for t in data["provides"]["templates"]}
        assert {"speckit.research", "speckit.scaffold-graphql", "spec-template"} <= names

    def test_preset_commands_are_not_mistaken_for_extension_overrides(self):
        """A `speckit.<x>.<y>` name is treated as an override of extension <x>
        and silently skipped when that extension is absent — delta-global's
        own commands must use two segments or they never install."""
        import yaml

        data = yaml.safe_load((REPO_ROOT / "presets" / "delta-global" / "preset.yml").read_text())
        three_part = [
            t["name"]
            for t in data["provides"]["templates"]
            if t.get("type") == "command" and len(t["name"].split(".")) >= 3
        ]
        assert three_part == []
