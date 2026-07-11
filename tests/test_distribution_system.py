import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DistributionSystemTests(unittest.TestCase):
    def read_required(self, relative_path: str) -> str:
        path = ROOT / relative_path
        self.assertTrue(path.is_file(), f"missing {relative_path}")
        return path.read_text(encoding="utf-8")

    def test_install_script_has_public_release_contract(self):
        text = self.read_required("install.sh")

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
        text = self.read_required("install.sh")

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

        guard = text.index("安装包包含禁止部署的运行时数据")
        copy = text.index('copy_release_files "$STAGE"')
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

    def test_repository_root_contains_no_historical_packages_or_runtime_data(self):
        version_dirs = [path.name for path in ROOT.iterdir() if path.is_dir() and path.name.startswith("V1.")]
        deploy_archives = [path.name for path in ROOT.iterdir() if path.is_file() and path.suffix.lower() == ".zip"]

        self.assertEqual(version_dirs, [])
        self.assertEqual(deploy_archives, [])
        for relative_path in (".env", "data", "watchdog.log"):
            self.assertFalse((ROOT / relative_path).exists(), relative_path)


if __name__ == "__main__":
    unittest.main()
