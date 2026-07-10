#!/usr/bin/env python3
"""
StemTube Desktop — Tauri Integration Tests
=======================================
Verifies that the project structure is correct for Tauri packaging.
Run from project root: python tests/test_tauri_integration.py
"""

import os
import sys
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestProjectStructure(unittest.TestCase):
    """Verify essential files exist."""

    def test_tauri_conf_exists(self):
        self.assertTrue((PROJECT_ROOT / "src-tauri" / "tauri.conf.json").exists())

    def test_tauri_conf_valid_json(self):
        with open(PROJECT_ROOT / "src-tauri" / "tauri.conf.json") as f:
            conf = json.load(f)
        self.assertEqual(conf["productName"], "StemTube Desktop")
        self.assertIn("nsis", str(conf["bundle"]["targets"]))

    def test_main_rs_exists(self):
        self.assertTrue((PROJECT_ROOT / "src-tauri" / "src" / "main.rs").exists())

    def test_cargo_toml_exists(self):
        self.assertTrue((PROJECT_ROOT / "src-tauri" / "Cargo.toml").exists())

    def test_app_py_exists(self):
        self.assertTrue((PROJECT_ROOT / "app.py").exists())

    def test_nuitka_build_exists(self):
        self.assertTrue((PROJECT_ROOT / "nuitka_build.py").exists())

    def test_build_tauri_exists(self):
        self.assertTrue((PROJECT_ROOT / "build_tauri.py").exists())

    def test_templates_exist(self):
        self.assertTrue((PROJECT_ROOT / "templates" / "index.html").exists())
        self.assertTrue((PROJECT_ROOT / "templates" / "mixer.html").exists())

    def test_icons_exist(self):
        self.assertTrue((PROJECT_ROOT / "src-tauri" / "icons" / "icon.ico").exists())


class TestNuitkaBuildConfig(unittest.TestCase):
    """Verify nuitka_build.py is configured for Tauri sidecar."""

    def test_entry_point_is_app_py(self):
        with open(PROJECT_ROOT / "nuitka_build.py") as f:
            content = f.read()
        self.assertIn('ENTRY_POINT = "app.py"', content)

    def test_console_mode_attach(self):
        with open(PROJECT_ROOT / "nuitka_build.py") as f:
            content = f.read()
        self.assertIn("--windows-console-mode=attach", content)

    def test_output_filename(self):
        with open(PROJECT_ROOT / "nuitka_build.py") as f:
            content = f.read()
        self.assertIn("stemtube-backend.exe", content)

    def test_webview_excluded(self):
        with open(PROJECT_ROOT / "nuitka_build.py") as f:
            content = f.read()
        self.assertIn('"webview"', content)  # In EXCLUDE_PACKAGES


class TestConfigPaths(unittest.TestCase):
    """Verify config.py path resolution works in dev mode."""

    def test_dev_mode_detection(self):
        """In dev mode (venv present), USER_DATA_DIR should equal APP_DIR."""
        from core.config import APP_DIR, USER_DATA_DIR
        # If venv or .dev marker exists, we're in dev mode
        project_root = os.path.dirname(APP_DIR)
        has_venv = os.path.exists(os.path.join(project_root, 'venv'))
        if has_venv:
            self.assertEqual(USER_DATA_DIR, APP_DIR)

    def test_downloads_dir_writable(self):
        from core.config import DOWNLOADS_DIR
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        test_file = os.path.join(DOWNLOADS_DIR, ".write_test")
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except PermissionError:
            self.fail(f"DOWNLOADS_DIR not writable: {DOWNLOADS_DIR}")

    def test_config_file_path(self):
        from core.config import CONFIG_FILE
        # Config should be in a directory that exists
        config_dir = os.path.dirname(CONFIG_FILE)
        self.assertTrue(os.path.exists(config_dir),
                       f"Config directory does not exist: {config_dir}")

    def test_db_dir_exists(self):
        from core.config import DB_DIR
        self.assertTrue(os.path.exists(DB_DIR), f"DB_DIR does not exist: {DB_DIR}")


class TestMainRs(unittest.TestCase):
    """Verify main.rs has the correct structure."""

    def test_contains_port_5011(self):
        with open(PROJECT_ROOT / "src-tauri" / "src" / "main.rs") as f:
            content = f.read()
        self.assertIn("5011", content)

    def test_contains_sidecar_detection(self):
        with open(PROJECT_ROOT / "src-tauri" / "src" / "main.rs") as f:
            content = f.read()
        self.assertIn("stemtube-backend", content)
        self.assertIn("stemtube-backend.exe", content)

    def test_contains_dev_mode_fallback(self):
        with open(PROJECT_ROOT / "src-tauri" / "src" / "main.rs") as f:
            content = f.read()
        self.assertIn("venv", content)
        self.assertIn("python", content.lower())

    def test_contains_cleanup_on_exit(self):
        with open(PROJECT_ROOT / "src-tauri" / "src" / "main.rs") as f:
            content = f.read()
        self.assertIn("kill_backend", content)
        self.assertIn("WindowEvent::Destroyed", content)


class TestRoutes(unittest.TestCase):
    """Verify Flask routes import correctly."""

    def test_routes_import(self):
        from routes import ALL_BLUEPRINTS
        self.assertGreater(len(ALL_BLUEPRINTS), 5)

    def test_no_auth_blueprint(self):
        """Auth blueprint should be removed (single-user desktop)."""
        from routes import ALL_BLUEPRINTS
        bp_names = [bp.name for bp in ALL_BLUEPRINTS]
        self.assertNotIn("auth", bp_names)

    def test_no_admin_blueprint(self):
        """Admin blueprint should be removed."""
        from routes import ALL_BLUEPRINTS
        bp_names = [bp.name for bp in ALL_BLUEPRINTS]
        self.assertNotIn("admin", bp_names)

    def test_has_essential_blueprints(self):
        from routes import ALL_BLUEPRINTS
        bp_names = [bp.name for bp in ALL_BLUEPRINTS]
        for essential in ["pages", "downloads", "extractions", "files", "media"]:
            self.assertIn(essential, bp_names, f"Missing blueprint: {essential}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
