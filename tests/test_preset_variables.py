"""Tests for the preset variables mechanism ({{ var.* }} substitution)."""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from specify_cli.presets import (  # noqa: E402
    PresetManager,
    PresetManifest,
    PresetValidationError,
    resolve_preset_variables,
    substitute_preset_variables,
)


@pytest.fixture
def temp_dir():
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir)


@pytest.fixture
def var_pack_data():
    return {
        "schema_version": "1.0",
        "preset": {
            "id": "var-pack",
            "name": "Variable Preset",
            "version": "1.0.0",
            "description": "A preset with variables",
        },
        "requires": {"speckit_version": ">=0.1.0"},
        "variables": {
            "tenancy_column": {
                "default": "organizationId",
                "description": "Tenant key column",
            },
            "package_scope": "@delta-global",
        },
        "provides": {
            "templates": [
                {
                    "type": "template",
                    "name": "spec-template",
                    "file": "templates/spec-template.md",
                    "replaces": "spec-template",
                }
            ]
        },
    }


@pytest.fixture
def var_pack_dir(temp_dir, var_pack_data):
    p_dir = temp_dir / "var-pack"
    (p_dir / "templates").mkdir(parents=True)
    (p_dir / "preset.yml").write_text(yaml.safe_dump(var_pack_data))
    (p_dir / "templates" / "spec-template.md").write_text(
        "Column: {{ var.tenancy_column }}\n"
        "Scope: {{ var.package_scope }}/db\n"
        "Unknown: {{ var.does_not_exist }}\n"
    )
    return p_dir


@pytest.fixture
def project_dir(temp_dir):
    proj = temp_dir / "project"
    (proj / ".specify" / "templates" / "commands").mkdir(parents=True)
    return proj


class TestSubstitution:
    def test_substitutes_known_variables(self):
        out = substitute_preset_variables(
            "a {{ var.x }} b {{var.y}} c", {"x": "1", "y": 2}
        )
        assert out == "a 1 b 2 c"

    def test_leaves_unknown_variables_visible(self):
        out = substitute_preset_variables("{{ var.missing }}", {})
        assert out == "{{ var.missing }}"

    def test_does_not_touch_workflow_expressions(self):
        content = "{{ inputs.feature_name }} and {{ steps.plan.output }}"
        assert substitute_preset_variables(content, {"feature_name": "x"}) == content


class TestManifestVariables:
    def test_variables_normalized(self, var_pack_dir):
        manifest = PresetManifest(var_pack_dir / "preset.yml")
        assert manifest.variables == {
            "tenancy_column": "organizationId",
            "package_scope": "@delta-global",
        }

    def test_no_variables_section_is_empty(self, temp_dir, var_pack_data):
        del var_pack_data["variables"]
        p_dir = temp_dir / "novar"
        (p_dir / "templates").mkdir(parents=True)
        (p_dir / "preset.yml").write_text(yaml.safe_dump(var_pack_data))
        (p_dir / "templates" / "spec-template.md").write_text("x")
        assert PresetManifest(p_dir / "preset.yml").variables == {}

    def test_invalid_variable_name_rejected(self, temp_dir, var_pack_data):
        var_pack_data["variables"] = {"Bad-Name": "x"}
        p_dir = temp_dir / "bad"
        p_dir.mkdir()
        (p_dir / "preset.yml").write_text(yaml.safe_dump(var_pack_data))
        with pytest.raises(PresetValidationError, match="Invalid variable name"):
            PresetManifest(p_dir / "preset.yml")

    def test_mapping_without_default_rejected(self, temp_dir, var_pack_data):
        var_pack_data["variables"] = {"x": {"description": "no default"}}
        p_dir = temp_dir / "bad2"
        p_dir.mkdir()
        (p_dir / "preset.yml").write_text(yaml.safe_dump(var_pack_data))
        with pytest.raises(PresetValidationError, match="requires a 'default'"):
            PresetManifest(p_dir / "preset.yml")


class TestResolveOverrides:
    def test_defaults_without_overrides(self, var_pack_dir, project_dir):
        manifest = PresetManifest(var_pack_dir / "preset.yml")
        resolved = resolve_preset_variables(manifest, project_dir)
        assert resolved["tenancy_column"] == "organizationId"

    def test_scoped_override_wins(self, var_pack_dir, project_dir):
        (project_dir / ".specify" / "preset-variables.yml").write_text(
            yaml.safe_dump({"var-pack": {"tenancy_column": "ownerId"}})
        )
        manifest = PresetManifest(var_pack_dir / "preset.yml")
        resolved = resolve_preset_variables(manifest, project_dir)
        assert resolved["tenancy_column"] == "ownerId"
        assert resolved["package_scope"] == "@delta-global"

    def test_flat_override_applies_to_declared_vars(self, var_pack_dir, project_dir):
        (project_dir / ".specify" / "preset-variables.yml").write_text(
            yaml.safe_dump({"tenancy_column": "userId"})
        )
        manifest = PresetManifest(var_pack_dir / "preset.yml")
        resolved = resolve_preset_variables(manifest, project_dir)
        assert resolved["tenancy_column"] == "userId"

    def test_scoped_beats_flat(self, var_pack_dir, project_dir):
        (project_dir / ".specify" / "preset-variables.yml").write_text(
            yaml.safe_dump(
                {"tenancy_column": "flat", "var-pack": {"tenancy_column": "scoped"}}
            )
        )
        manifest = PresetManifest(var_pack_dir / "preset.yml")
        assert resolve_preset_variables(manifest, project_dir)["tenancy_column"] == "scoped"

    def test_invalid_overrides_file_is_ignored(self, var_pack_dir, project_dir):
        (project_dir / ".specify" / "preset-variables.yml").write_text(": not yaml [")
        manifest = PresetManifest(var_pack_dir / "preset.yml")
        assert resolve_preset_variables(manifest, project_dir)["tenancy_column"] == "organizationId"


class TestInstallAppliesVariables:
    def test_installed_copy_is_substituted(self, var_pack_dir, project_dir):
        (project_dir / ".specify" / "preset-variables.yml").write_text(
            yaml.safe_dump({"var-pack": {"package_scope": "@acme"}})
        )
        manager = PresetManager(project_dir)
        manager.install_from_directory(var_pack_dir, "1.0.0")

        installed = (
            project_dir / ".specify" / "presets" / "var-pack" / "templates" / "spec-template.md"
        ).read_text()
        assert "Column: organizationId" in installed
        assert "Scope: @acme/db" in installed
        # Unknown variables stay visible
        assert "{{ var.does_not_exist }}" in installed
        # Source preset untouched
        source = (var_pack_dir / "templates" / "spec-template.md").read_text()
        assert "{{ var.tenancy_column }}" in source


class TestBundledPresetsDeclareTheirVariables:
    """Every {{ var.* }} used in a bundled preset must be declared."""

    @pytest.mark.parametrize("preset_id", ["nextjs", "delta-global", "lean"])
    def test_used_variables_are_declared(self, preset_id):
        import re

        preset_dir = Path(__file__).parent.parent / "presets" / preset_id
        manifest = PresetManifest(preset_dir / "preset.yml")
        declared = set(manifest.variables)
        used = set()
        for f in preset_dir.rglob("*.md"):
            used.update(re.findall(r"\{\{\s*var\.([a-z][a-z0-9_]*)\s*\}\}", f.read_text()))
        assert used <= declared, f"undeclared variables in {preset_id}: {used - declared}"
