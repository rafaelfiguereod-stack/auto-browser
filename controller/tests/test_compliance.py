from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.compliance import (
    VALID_PRESETS,
    VALID_TEMPLATES,
    apply_compliance_template,
    write_compliance_manifest,
)


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.require_auth_state_encryption = False
    settings.require_operator_id = False
    settings.pii_scrub_enabled = False
    settings.pii_scrub_screenshot = False
    settings.pii_scrub_network = False
    settings.pii_scrub_console = False
    settings.require_approval_for_uploads = False
    settings.witness_enabled = False
    settings.auth_state_max_age_hours = 72.0
    settings.session_isolation_mode = "shared_browser_node"
    return settings


class ComplianceTests(unittest.TestCase):
    def test_all_presets_apply(self) -> None:
        for preset in sorted(VALID_PRESETS):
            with self.subTest(preset=preset):
                settings = _settings()

                overrides = apply_compliance_template(settings, preset)

                self.assertIsInstance(overrides, dict)
                self.assertTrue(overrides)

    def test_strict_sets_encryption(self) -> None:
        settings = _settings()
        apply_compliance_template(settings, "strict")
        self.assertTrue(settings.require_auth_state_encryption)

    def test_strict_sets_isolation(self) -> None:
        settings = _settings()
        apply_compliance_template(settings, "strict")
        self.assertEqual(settings.session_isolation_mode, "docker_ephemeral")

    def test_strict_short_max_age(self) -> None:
        settings = _settings()
        apply_compliance_template(settings, "strict")
        self.assertEqual(settings.auth_state_max_age_hours, 4.0)

    def test_balanced_no_encryption_requirement(self) -> None:
        settings = _settings()
        apply_compliance_template(settings, "balanced")
        self.assertFalse(settings.require_auth_state_encryption)
        self.assertTrue(settings.require_operator_id)

    def test_invalid_preset_raises(self) -> None:
        settings = _settings()
        with self.assertRaisesRegex(ValueError, "Unknown compliance preset"):
            apply_compliance_template(settings, "fakecompliance")

    def test_case_insensitive(self) -> None:
        settings = _settings()
        overrides = apply_compliance_template(settings, "STRICT")
        self.assertTrue(overrides)

    def test_deprecated_alias_maps_to_strict(self) -> None:
        settings = _settings()
        with self.assertLogs("app.compliance", level="WARNING") as cm:
            apply_compliance_template(settings, "HIPAA")
        self.assertTrue(any("deprecated alias" in msg for msg in cm.output))
        self.assertTrue(settings.require_auth_state_encryption)
        self.assertEqual(settings.session_isolation_mode, "docker_ephemeral")

    def test_deprecated_alias_maps_to_balanced(self) -> None:
        settings = _settings()
        with self.assertLogs("app.compliance", level="WARNING"):
            apply_compliance_template(settings, "SOC2")
        self.assertTrue(settings.require_operator_id)
        self.assertFalse(settings.require_auth_state_encryption)

    def test_valid_templates_includes_aliases(self) -> None:
        self.assertIn("HIPAA", VALID_TEMPLATES)
        self.assertIn("strict", VALID_TEMPLATES)

    def test_write_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"

            write_compliance_manifest(
                template_name="balanced",
                overrides={"pii_scrub_enabled": True},
                output_path=manifest_path,
            )

            self.assertTrue(manifest_path.exists())
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(data["template"], "balanced")
            self.assertIn("applied_overrides", data)
