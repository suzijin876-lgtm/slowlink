# SlowLink Distribution System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish SlowLink 1.38.73 as a clean public Git repository with tested GitHub Releases, Chinese one-command lifecycle management, safe state-preserving updates, and verified server deployment.

**Architecture:** Keep the forwarding application unchanged and add a distribution layer around it. A Python release builder creates deterministic app/full/update-log/checksum assets; POSIX shell scripts consume GitHub Releases, validate archives, preserve runtime state, and operate only the `slowlink_app` service during updates. GitHub Actions runs the same tests and builder used locally.

**Tech Stack:** Python 3 unittest/zipfile/hashlib, POSIX `sh`, Docker Compose v2, GitHub Actions, GitHub CLI/API, systemd.

---

### Task 1: Clean Repository Boundary

**Files:**
- Create: `.gitignore`
- Create: `.gitattributes`
- Create: `.env.example`
- Create: `README.md`
- Modify: `.dockerignore`
- Move outside repository: `V1.*`, `_v153_bot_runner.py`, `_v153_redis_store.py`

- [ ] **Step 1: Create the external archive directories**

Run:

```powershell
New-Item -ItemType Directory -Force D:\Users\szjhs\Documents\tg\slowlink_releases_archive | Out-Null
New-Item -ItemType Directory -Force D:\Users\szjhs\Documents\tg\slowlink_releases | Out-Null
```

Expected: both directories exist outside the Git repository.

- [ ] **Step 2: Move historical artifacts out of the repository**

Move every root directory matching `V1.*` and both `_v153_*` files to `slowlink_releases_archive`, preserving names. Verify no target path escapes the intended archive directory before moving.

- [ ] **Step 3: Add repository exclusions and line-ending policy**

`.gitignore` must contain:

```gitignore
.env
.env.*
!.env.example
data/
sessions/
*.session
*.session-journal
*.sqlite
*.sqlite3
*.db
*.rdb
appendonlydir/
dump.rdb
*.log
watchdog.log
backups/
backup/
dist/
V1.*/
*.zip
*.tar
*.tar.gz
__pycache__/
*.py[cod]
.pytest_cache/
.coverage
.DS_Store
```

`.gitattributes` must enforce LF for Python, Markdown, text, YAML, shell, service, Docker, ignore, example-env, and `VERSION` files; ZIP and database formats must be binary.

- [ ] **Step 4: Add public documentation and safe example configuration**

Replace the damaged `README.txt` with `README.md` describing purpose, prerequisites, installation command, management commands, update safety, and secret handling. `.env.example` contains only commented/non-secret examples. Extend `.dockerignore` to exclude Git metadata, runtime data, tests caches, docs plans, archives, logs, and backups while keeping application build inputs.

- [ ] **Step 5: Verify the repository boundary**

Run:

```powershell
git status --short
rg -n --hidden -g '!docs/superpowers/**' -g '!.git/**' '(D\*eSd0JrvCtE|api[_-]?hash\s*=|bot[_-]?token\s*=|password\s*=)' .
```

Expected: no historical `V1.*` paths, sessions, databases, logs, backups, real credentials, or tokens are candidates for commit.

### Task 2: Write Distribution Contract Tests

**Files:**
- Create: `tests/test_distribution_system.py`

- [ ] **Step 1: Add failing tests for scripts, workflow, packaging, and repository hygiene**

Create `DistributionSystemTests(unittest.TestCase)` with assertions that:

```python
INSTALL_REQUIRED = (
    'REPO="suzijin876-lgtm/slowlink"',
    'INSTALL_DIR="/opt/slowlink"',
    '/dev/tty',
    'SHA256SUMS.txt',
    'sha256sum -c',
    'docker compose up -d --no-deps --build app',
    'slowlink-watchdog.service',
    '1.安装',
    '2.更新到最新版本',
    '3.卸载',
)

MANAGE_COMMANDS = ('status', 'logs', 'restart', 'update', 'backup', 'uninstall', 'purge')
FORBIDDEN_ROOT_PREFIXES = ('V1.',)
RELEASE_ASSETS = (
    'slowlink_app_v1_38_73.zip',
    'slowlink_v1_38_73_full.zip',
    'slowlink_v1_38_73_update_log.txt',
    'SHA256SUMS.txt',
)
```

Tests must verify PURGE confirmation precedes service stop/deletion, update code never contains `docker compose down`, Redis is not stopped during update/uninstall-preserve, archive guards reject `.env`, `data/`, `.git/`, sessions, databases, logs and backups, workflow has `contents: write` and `v*`, and root has no version directories or deploy ZIPs.

- [ ] **Step 2: Run the new test and confirm it fails**

Run:

```powershell
python -m unittest tests.test_distribution_system -v
```

Expected: failures for missing `install.sh`, `manage.sh`, `uninstall.sh`, release builder, and workflow.

- [ ] **Step 3: Commit the test contract**

```powershell
git add tests/test_distribution_system.py
git commit -m "test: define public distribution contract"
```

### Task 3: Implement the Release Builder

**Files:**
- Create: `scripts/build_release.py`
- Create: `CHANGELOG.md`
- Modify: `app/config.py`
- Modify: `VERSION`

- [ ] **Step 1: Add release-builder unit coverage**

Extend `tests/test_distribution_system.py` to import `scripts.build_release` and test:

```python
self.assertEqual(build_release.file_version('1.38.73'), '1_38_73')
self.assertEqual(build_release.extract_changelog('1.38.73'), expected_section)
self.assertEqual(set(build_release.expected_asset_names('1.38.73')), set(RELEASE_ASSETS))
```

Build into a temporary directory and inspect both ZIP member lists. Assert no member matches runtime/secret patterns and every checksum validates with `hashlib.sha256`.

- [ ] **Step 2: Run the builder tests and confirm they fail**

Run `python -m unittest tests.test_distribution_system -v`.

Expected: import or function failures because `scripts/build_release.py` does not exist.

- [ ] **Step 3: Implement the builder**

The builder must expose four exact public functions. `file_version(version: str) -> str` validates three numeric version components and replaces dots with underscores. `extract_changelog(version: str, changelog: Path = ROOT / 'CHANGELOG.md') -> str` returns the complete matching `## [version]` section and raises `ValueError` when absent. `expected_asset_names(version: str) -> tuple[str, str, str, str]` returns the four required filenames. `build(version: str, output_dir: Path) -> list[Path]` validates `VERSION`, creates a clean output directory, writes the four assets, verifies every checksum, and returns their paths in app/full/log/checksum order.

Use explicit allowlists. App ZIP contains `app/` only. Full ZIP contains `.dockerignore`, `.env.example`, `.gitattributes`, `.gitignore`, `CHANGELOG.md`, `Dockerfile`, `README.md`, `VERSION`, `app/`, `docker-compose.yml`, `install.sh`, `manage.sh`, `uninstall.sh`, `ops/`, `requirements.txt`, and `scripts/distribution_lib.sh`. Exclude caches and generated artifacts. Write the current changelog section as the update log, then write and verify `SHA256SUMS.txt` for the first three assets.

- [ ] **Step 4: Bump version and changelog**

Set both `VERSION` and `app.config.APP_VERSION` to `1.38.73`. Add a `CHANGELOG.md` section describing only distribution-system changes and explicitly state that forwarding business logic is unchanged.

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m compileall -q app scripts tests
python -m unittest tests.test_distribution_system -v
```

Expected: builder tests pass; script-contract tests still fail only for not-yet-created shell/workflow files.

- [ ] **Step 6: Commit**

```powershell
git add VERSION app/config.py CHANGELOG.md scripts/build_release.py tests/test_distribution_system.py
git commit -m "build: add verified release packaging"
```

### Task 4: Implement Shared Distribution Library and Installer

**Files:**
- Create: `scripts/distribution_lib.sh`
- Create: `install.sh`
- Test: `tests/test_distribution_system.py`

- [ ] **Step 1: Add failing installer safety assertions**

Assert `/dev/tty` menu input, Ubuntu/Debian guard, Docker/Compose installation, GitHub API asset `.url`, `Accept: application/octet-stream`, SHA-256 verification, archive path traversal/runtime-data rejection, fixed `/opt/slowlink`, health wait, Chinese diagnostics, and the exact app-only update command. Assert `docker compose down`, `docker stop slowlink_redis`, and Redis volume deletion are absent from install/update paths.

- [ ] **Step 2: Implement reusable distribution functions**

`scripts/distribution_lib.sh` must provide POSIX functions for logging, failure diagnostics, temporary-directory cleanup, OS checks, Docker installation, GitHub API requests, latest/specified Release resolution, asset download, SHA verification, ZIP safety checks, staged copy preserving protected paths, app-only rebuild, health wait, watchdog install, and status snapshots.

Protected paths are:

```sh
PROTECTED_PATHS='.env data sessions redis_data backups backup watchdog.log'
```

The staged copy must use a full-package allowlist and never delete protected or unknown runtime files.

- [ ] **Step 3: Implement the Chinese installer menu**

`install.sh` sources the library and implements the required main/uninstall menus. Command-line support includes `--version VERSION`, `--update`, `--uninstall`, `--purge`, and `--help`. Fresh install may start Redis when absent and then runs `docker compose up -d --no-deps --build app`; update always runs only that app command. Install/update must install the watchdog unit and wait up to 90 seconds for `/health` and container health.

- [ ] **Step 4: Validate shell syntax and tests**

Run using Git for Windows shell paths when native `bash`/`dash` are unavailable:

```powershell
bash -n install.sh scripts/distribution_lib.sh
dash -n install.sh scripts/distribution_lib.sh
python -m unittest tests.test_distribution_system -v
```

Expected: installer tests pass; management/workflow tests remain pending.

- [ ] **Step 5: Commit**

```powershell
git add install.sh scripts/distribution_lib.sh tests/test_distribution_system.py
git commit -m "feat: add safe one-command installer"
```

### Task 5: Implement Management, Backup, and Uninstall

**Files:**
- Create: `manage.sh`
- Create: `uninstall.sh`
- Test: `tests/test_distribution_system.py`

- [ ] **Step 1: Add failing management and purge-order tests**

Test all required commands, app-only restart/update behavior, backup contents, preserve-mode Redis exclusions, fixed install-path guard, and that `[ "$answer" = "PURGE" ]` appears before any `systemctl disable`, Docker stop/remove, volume removal, or `rm -rf` operation.

- [ ] **Step 2: Implement `manage.sh`**

Implement:

```text
status     health/version/container/Redis/listener/watchdog summary
logs       docker logs -f --tail 100 slowlink_app
restart    docker compose restart app, then health wait
update     download current main install.sh and run --update
backup     create timestamped archive outside the install directory
uninstall  run uninstall.sh preserve mode
purge      run uninstall.sh --purge
```

Backup must include existing `.env`, `data/`, selected user configuration, Redis `dump.rdb` copied through `docker cp` after `redis-cli BGSAVE`, and a manifest. Backup failure must not delete source data.

- [ ] **Step 3: Implement protected uninstall**

Preserve mode disables/removes only the SlowLink watchdog and removes only `slowlink_app`; it leaves `/opt/slowlink/.env`, `/opt/slowlink/data`, `slowlink_redis`, the Redis volume, and database files intact. Purge mode reads from `/dev/tty`, requires exact `PURGE`, validates `INSTALL_DIR=/opt/slowlink`, then removes SlowLink app, Redis container, project Redis volume, watchdog, and install directory. It must not act on unrelated containers or services.

- [ ] **Step 4: Validate**

Run:

```powershell
bash -n manage.sh uninstall.sh
dash -n manage.sh uninstall.sh
python -m unittest tests.test_distribution_system -v
```

Expected: all script-contract tests except workflow/repository-finalization tests pass.

- [ ] **Step 5: Commit**

```powershell
git add manage.sh uninstall.sh tests/test_distribution_system.py
git commit -m "feat: add lifecycle management and protected uninstall"
```

### Task 6: Add GitHub Actions Release Automation

**Files:**
- Create: `.github/workflows/release.yml`
- Test: `tests/test_distribution_system.py`

- [ ] **Step 1: Add failing workflow assertions**

Assert `push.tags: v*`, `permissions.contents: write`, Python setup, compileall, unittest discovery, bash/dash syntax checks, builder invocation, checksum verification, and `gh release create` with `${{ github.token }}`.

- [ ] **Step 2: Implement workflow**

The workflow runs on Ubuntu latest, checks that `${GITHUB_REF_NAME#v}` equals `VERSION`, installs project requirements, executes all tests, invokes:

```bash
python scripts/build_release.py --version "$version" --output dist
(cd dist && sha256sum -c SHA256SUMS.txt)
```

Then publish exactly the four expected assets with `gh release create "$GITHUB_REF_NAME" dist/* --verify-tag --title "SlowLink $GITHUB_REF_NAME" --generate-notes` and `GH_TOKEN: ${{ github.token }}`.

- [ ] **Step 3: Run tests and commit**

```powershell
python -m unittest tests.test_distribution_system -v
git add .github/workflows/release.yml tests/test_distribution_system.py
git commit -m "ci: publish verified tag releases"
```

### Task 7: Finalize Documentation and Full Test Suite

**Files:**
- Modify: `README.md`
- Create: `docs/OPERATIONS.md`
- Modify: `tests/test_distribution_system.py`

- [ ] **Step 1: Document public operations**

Document the `curl | sudo bash` command, menu behavior, `manage.sh` commands, update state preservation, backup location, watchdog, health checks, uninstall/purge difference, and troubleshooting. Do not include any real server IP, password, token, Session, or private configuration.

- [ ] **Step 2: Run complete verification**

Run:

```powershell
python -m compileall -q app scripts tests
python -m unittest discover -s tests
bash -n install.sh manage.sh uninstall.sh scripts/distribution_lib.sh ops/slowlink_watchdog.sh
dash -n install.sh manage.sh uninstall.sh scripts/distribution_lib.sh ops/slowlink_watchdog.sh
python scripts/build_release.py --version 1.38.73 --output dist
```

Expected: all existing 69 tests plus distribution tests pass, shell syntax succeeds, and four assets are generated.

- [ ] **Step 3: Inspect package contents and secrets**

Verify both ZIP member lists contain no protected paths. Search tracked candidates for credentials. Confirm `git status` contains only intentional files and `git diff -- app/` shows only `app/config.py` version change.

- [ ] **Step 4: Commit source release**

```powershell
git add .
git commit -m "release: prepare SlowLink 1.38.73"
```

### Task 8: Generate External Local Release Archive

**Files:**
- Create outside repository: `D:\Users\szjhs\Documents\tg\slowlink_releases\V1.38.73\*`

- [ ] **Step 1: Rebuild into a clean external directory**

Run the builder with output `D:\Users\szjhs\Documents\tg\slowlink_releases\V1.38.73` after deleting only that exact target if it already exists and has been path-validated.

- [ ] **Step 2: Verify four assets and checksums**

Expected files are exactly the four names in `RELEASE_ASSETS`; every line in `SHA256SUMS.txt` validates.

### Task 9: Push, Release, Deploy, and Verify

**Files:**
- Git remote/tag state
- Server: `/opt/slowlink`

- [ ] **Step 1: Configure and verify Git remote**

```powershell
git remote add origin https://github.com/suzijin876-lgtm/slowlink.git
git remote -v
git status --short --branch
```

Expected: clean `main`, no sensitive or archived files tracked.

- [ ] **Step 2: Push main and release tag**

```powershell
git push -u origin main
git tag -a v1.38.73 -m "SlowLink 1.38.73"
git push origin v1.38.73
```

- [ ] **Step 3: Verify GitHub Release**

Poll the GitHub API until `v1.38.73` is published. Confirm it is public and contains exactly the app ZIP, full ZIP, update log, and `SHA256SUMS.txt`; download and validate checksums.

- [ ] **Step 4: Capture server baseline**

Before deployment record all Docker container IDs, names, statuses, start times, Redis state, app health/version, Session paths, listener state keys, watchdog status, and host service state needed to prove unrelated services were not restarted.

- [ ] **Step 5: Deploy through the new release updater**

Download public `install.sh` on the server and execute `sh install.sh --update`. The update must preserve `.env`, `data`, Session and Redis data, and rebuild only Compose service `app`.

- [ ] **Step 6: Verify deployment**

Confirm `/health` reports `1.38.73`, `slowlink_app` is healthy, web HTTP responds, `slowlink_redis` container ID/start time is unchanged, Session files remain, Redis keys `listener_desired_state`, `bot_status`, `tg_logged_in`, and `target_chat` are sane, watchdog is active, recent logs contain no new traceback, and every unrelated container/service start time is unchanged.

- [ ] **Step 7: Record final result**

Report local Git commit/tag, GitHub Release URL and four assets, local archive path, server version/health/listener/watchdog state, and any residual risk without exposing credentials.
