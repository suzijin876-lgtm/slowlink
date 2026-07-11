import hashlib
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DistributionSystemTests(unittest.TestCase):
    def read_required(self, relative_path: str) -> str:
        path = ROOT / relative_path
        self.assertTrue(path.is_file(), f"missing {relative_path}")
        return path.read_text(encoding="utf-8")

    def test_install_script_has_public_release_contract(self):
        install_text = self.read_required("install.sh")
        library_text = self.read_required("scripts/distribution_lib.sh")
        text = install_text + "\n" + library_text

        for fragment in (
            'REPO="suzijin876-lgtm/slowlink"',
            'INSTALL_DIR="/opt/slowlink"',
            "/dev/tty",
            "SHA256SUMS.txt",
            "sha256sum -c",
            "application/octet-stream",
            "get.docker.com",
            "docker compose version",
            "slowlink-watchdog.service",
            "docker compose up -d --no-deps --build app",
            "1.安装",
            "2.更新到最新版本",
            "3.卸载",
            "0.退出",
        ):
            self.assertIn(fragment, text)

        self.assertIn("ubuntu|debian", text)
        self.assertIn("--version", text)
        self.assertIn("--update", text)
        self.assertNotIn("browser_download_url", text)
        self.assertNotIn("docker compose down", text)
        self.assertNotIn("docker stop slowlink_redis", text)

    def test_install_script_protects_runtime_data_before_copying(self):
        install_text = self.read_required("install.sh")
        library_text = self.read_required("scripts/distribution_lib.sh")
        text = install_text + "\n" + library_text

        for fragment in (
            ".env",
            "data/",
            ".git/",
            "session",
            "sqlite",
            "*.log",
            "backup",
        ):
            self.assertIn(fragment, text)

        guard = install_text.index('validate_release_archive "$FULL_FILE"')
        copy = install_text.index('copy_release_files "$STAGE"')
        self.assertLess(guard, copy)

    def test_manage_script_exposes_scoped_commands(self):
        text = self.read_required("manage.sh")

        for command in ("status", "logs", "restart", "update", "backup", "uninstall", "purge"):
            self.assertIn(f"{command})", text)
        self.assertIn("slowlink_app", text)
        self.assertIn("slowlink_redis", text)
        self.assertIn("slowlink-watchdog.service", text)
        self.assertIn("docker compose restart app", text)
        self.assertNotIn("docker compose down", text)

    def test_uninstall_requires_confirmation_before_destructive_actions(self):
        text = self.read_required("uninstall.sh")

        for fragment in (
            '/opt/slowlink',
            'slowlink_app',
            'slowlink_redis',
            'slowlink-watchdog.service',
            '--purge',
            '/dev/tty',
            'PURGE',
            '保留配置、Telegram Session、Redis 数据和数据库',
        ):
            self.assertIn(fragment, text)

        confirmation = text.index('[ "$answer" = "PURGE" ]')
        fixed_path_guard = text.index('[ "$INSTALL_DIR" = "/opt/slowlink" ]')
        service_stop = text.index('systemctl disable --now "$WATCHDOG_SERVICE"')
        permanent_delete = text.index('rm -rf -- "$INSTALL_DIR"')
        self.assertLess(confirmation, fixed_path_guard)
        self.assertLess(fixed_path_guard, service_stop)
        self.assertLess(service_stop, permanent_delete)

    def test_release_workflow_builds_four_verified_assets(self):
        text = self.read_required(".github/workflows/release.yml")

        for fragment in (
            'tags:',
            'v*',
            'contents: write',
            'python -m unittest discover -s tests',
            'python -m compileall -q app scripts tests',
            'python scripts/build_release.py',
            'sha256sum -c SHA256SUMS.txt',
            'gh release create',
            'GH_TOKEN:',
        ):
            self.assertIn(fragment, text)

    def test_release_builder_creates_exact_verified_assets(self):
        builder_path = ROOT / "scripts" / "build_release.py"
        self.assertTrue(builder_path.is_file(), "missing scripts/build_release.py")

        spec = importlib.util.spec_from_file_location("slowlink_build_release", builder_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        version = "1.38.73"
        expected_names = (
            "slowlink_app_v1_38_73.zip",
            "slowlink_v1_38_73_full.zip",
            "slowlink_v1_38_73_update_log.txt",
            "SHA256SUMS.txt",
        )
        self.assertEqual(module.file_version(version), "1_38_73")
        self.assertEqual(module.expected_asset_names(version), expected_names)
        self.assertIn("## [1.38.73]", module.extract_changelog(version))

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            assets = module.build(version, output_dir)
            self.assertEqual(tuple(path.name for path in assets), expected_names)
            self.assertEqual({path.name for path in output_dir.iterdir()}, set(expected_names))

            app_zip, full_zip, update_log, checksum_file = assets
            with zipfile.ZipFile(app_zip) as archive:
                app_members = archive.namelist()
            with zipfile.ZipFile(full_zip) as archive:
                full_members = archive.namelist()

            self.assertTrue(app_members)
            self.assertTrue(all(name.startswith("app/") for name in app_members))
            for required in (
                "VERSION",
                "Dockerfile",
                "docker-compose.yml",
                "install.sh",
                "manage.sh",
                "uninstall.sh",
                "scripts/distribution_lib.sh",
            ):
                self.assertIn(required, full_members)

            forbidden_parts = (
                "/.env",
                "/data/",
                "/sessions/",
                "/.git/",
                "/backups/",
                "/backup/",
                "/__pycache__/",
            )
            for member in app_members + full_members:
                normalized = f"/{member.lower()}"
                self.assertFalse(any(part in normalized for part in forbidden_parts), member)
                self.assertFalse(normalized.endswith((".session", ".sqlite", ".sqlite3", ".db", ".rdb", ".log")), member)

            self.assertIn("## [1.38.73]", update_log.read_text(encoding="utf-8"))
            checksum_lines = checksum_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(checksum_lines), 3)
            for line in checksum_lines:
                digest, name = line.split("  ", 1)
                payload = (output_dir / name).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)

    def test_repository_root_contains_no_historical_packages_or_runtime_data(self):
        version_dirs = [path.name for path in ROOT.iterdir() if path.is_dir() and path.name.startswith("V1.")]
        deploy_archives = [path.name for path in ROOT.iterdir() if path.is_file() and path.suffix.lower() == ".zip"]

        self.assertEqual(version_dirs, [])
        self.assertEqual(deploy_archives, [])
        for relative_path in (".env", "data", "watchdog.log"):
            self.assertFalse((ROOT / relative_path).exists(), relative_path)


if __name__ == "__main__":
    unittest.main()
