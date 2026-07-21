#!/bin/sh

REPO="${REPO:-suzijin876-lgtm/slowlink}"
INSTALL_DIR="${INSTALL_DIR:-/opt/slowlink}"
APP_SERVICE="${APP_SERVICE:-app}"
APP_CONTAINER="${APP_CONTAINER:-slowlink_app}"
REDIS_CONTAINER="${REDIS_CONTAINER:-slowlink_redis}"
WATCHDOG_SERVICE="${WATCHDOG_SERVICE:-slowlink-watchdog.service}"
DEFAULT_WEB_PORT="${DEFAULT_WEB_PORT:-8080}"
PROTECTED_PATHS='.env data sessions redis_data backups backup watchdog.log'
PROTECTED_GLOBS='*.session *.session-journal *.sqlite *.sqlite3 *.db *.rdb *.log'
PROGRAM_PATHS='.dockerignore .env.example .gitattributes .gitignore CHANGELOG.md Dockerfile LICENSE README.md VERSION app docker-compose.yml install.sh manage.sh uninstall.sh ops requirements.txt scripts'

log() {
  printf '[SlowLink] %s\n' "$*"
}

warn() {
  printf '[SlowLink 警告] %s\n' "$*" >&2
}

die() {
  printf '[SlowLink 失败] %s\n' "$*" >&2
  exit 1
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die "请使用 root 或 sudo 运行"
}

check_supported_os() {
  [ -r /etc/os-release ] || die "无法识别 Linux 发行版"
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) ;;
    *) die "当前仅支持 Ubuntu 和 Debian" ;;
  esac
}

install_dependencies() {
  tools_ready=1
  for tool_name in curl jq unzip ss; do
    command -v "$tool_name" >/dev/null 2>&1 || tools_ready=0
  done
  if [ "$tools_ready" -eq 1 ] && [ -r /etc/ssl/certs/ca-certificates.crt ]; then
    log "基础工具已就绪，跳过 APT"
    return
  fi
  log "安装基础工具"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl jq unzip iproute2 >/dev/null
}

validate_web_port() {
  web_port_value=${1:-}
  case "$web_port_value" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "$web_port_value" -ge 1 ] 2>/dev/null && [ "$web_port_value" -le 65535 ] 2>/dev/null
}

read_web_port() {
  web_port_value=""
  if [ -f "$INSTALL_DIR/.env" ]; then
    web_port_value=$(sed -n 's/^[[:space:]]*SLOWLINK_WEB_PORT[[:space:]]*=[[:space:]]*//p' "$INSTALL_DIR/.env" | tail -n 1 | tr -d '[:space:]')
  fi
  if ! validate_web_port "$web_port_value"; then
    web_port_value=$DEFAULT_WEB_PORT
  fi
  printf '%s\n' "$web_port_value"
}

save_web_port() {
  web_port_value=$1
  validate_web_port "$web_port_value" || die "网页端口无效：$web_port_value"
  mkdir -p "$INSTALL_DIR" || die "无法创建安装目录"
  web_port_tmp=$(mktemp "$INSTALL_DIR/.env.tmp.XXXXXX") || die "无法创建端口配置临时文件"
  if [ -f "$INSTALL_DIR/.env" ]; then
    awk '!/^[[:space:]]*SLOWLINK_WEB_PORT[[:space:]]*=/' "$INSTALL_DIR/.env" > "$web_port_tmp" || die "读取现有端口配置失败"
  fi
  printf 'SLOWLINK_WEB_PORT=%s\n' "$web_port_value" >> "$web_port_tmp" || die "写入网页端口失败"
  chmod 600 "$web_port_tmp" || die "设置端口配置权限失败"
  mv -f "$web_port_tmp" "$INSTALL_DIR/.env" || die "保存网页端口失败"
}

port_in_use() {
  web_port_value=$1
  ss -ltnH 2>/dev/null | awk -v suffix=":$web_port_value" '$4 ~ suffix "$" { found=1 } END { exit(found ? 0 : 1) }'
}

app_owns_port() {
  web_port_value=$1
  docker inspect "$APP_CONTAINER" >/dev/null 2>&1 || return 1
  docker port "$APP_CONTAINER" 8080/tcp 2>/dev/null | awk -F: -v port="$web_port_value" '$NF == port { found=1 } END { exit(found ? 0 : 1) }'
}

describe_port_owner() {
  web_port_value=$1
  port_owner=$(ss -ltnp 2>/dev/null | awk -v suffix=":$web_port_value" '$4 ~ suffix "$" { print; found=1 } END { if (!found) exit 1 }' | head -n 1 || true)
  if [ -n "$port_owner" ]; then
    printf '%s\n' "$port_owner"
  else
    printf '未能读取占用进程详情\n'
  fi
}

assert_web_port_available() {
  web_port_value=$1
  validate_web_port "$web_port_value" || {
    warn "网页端口无效：$web_port_value"
    return 1
  }
  if port_in_use "$web_port_value" && ! app_owns_port "$web_port_value"; then
    warn "当前端口已被占用：$web_port_value"
    warn "占用详情：$(describe_port_owner "$web_port_value")"
    warn "不会停止占用端口的现有服务，请为 SlowLink 选择其他端口"
    return 1
  fi
  return 0
}

find_available_port() {
  web_port_value=${1:-$DEFAULT_WEB_PORT}
  validate_web_port "$web_port_value" || web_port_value=$DEFAULT_WEB_PORT
  web_port_limit=$((web_port_value + 1000))
  [ "$web_port_limit" -le 65535 ] || web_port_limit=65535
  while [ "$web_port_value" -le "$web_port_limit" ]; do
    if ! port_in_use "$web_port_value" || app_owns_port "$web_port_value"; then
      printf '%s\n' "$web_port_value"
      return 0
    fi
    web_port_value=$((web_port_value + 1))
  done
  return 1
}

backup_program_files() {
  program_backup_dir=$1
  rm -rf -- "$program_backup_dir" || die "清理程序备份目录失败"
  mkdir -p "$program_backup_dir" || die "创建程序备份目录失败"
  for program_path in $PROGRAM_PATHS; do
    if [ -e "$INSTALL_DIR/$program_path" ]; then
      cp -a "$INSTALL_DIR/$program_path" "$program_backup_dir/" || die "备份旧程序失败：$program_path"
    fi
  done
}

restore_program_files() {
  program_backup_dir=$1
  [ "$INSTALL_DIR" = "/opt/slowlink" ] || die "安装目录安全检查失败"
  [ -d "$program_backup_dir" ] || die "旧程序备份不存在"
  for program_path in $PROGRAM_PATHS; do
    rm -rf -- "$INSTALL_DIR/$program_path" || die "清理失败版本程序文件失败：$program_path"
  done
  cp -a "$program_backup_dir"/. "$INSTALL_DIR"/ || die "恢复旧程序失败"
  find "$INSTALL_DIR/app" -type f -exec touch {} + 2>/dev/null || true
}

ensure_docker() {
  docker_ready=0
  if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
      docker_ready=1
    fi
  fi
  if [ "$docker_ready" -ne 1 ]; then
    log "安装 Docker Engine 和 Docker Compose"
    docker_script=$1/get-docker.sh
    curl -fsSL https://get.docker.com -o "$docker_script" || die "Docker 安装脚本下载失败"
    sh "$docker_script" || die "Docker 安装失败"
  fi
  systemctl enable --now docker >/dev/null 2>&1 || die "Docker 服务启动失败"
}

github_get() {
  github_url=$1
  github_output=${2:-}
  github_accept=${3:-application/vnd.github+json}
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    github_auth="Authorization: Bearer $GITHUB_TOKEN"
  else
    github_auth=""
  fi
  if [ -n "$github_output" ]; then
    if [ -n "$github_auth" ]; then
      curl -fsSL -H "$github_auth" -H "Accept: $github_accept" "$github_url" -o "$github_output"
    else
      curl -fsSL -H "Accept: $github_accept" "$github_url" -o "$github_output"
    fi
  elif [ -n "$github_auth" ]; then
    curl -fsSL -H "$github_auth" -H "Accept: $github_accept" "$github_url"
  else
    curl -fsSL -H "Accept: $github_accept" "$github_url"
  fi
}

download_release() {
  requested_version=$1
  download_dir=$2
  if [ -n "$requested_version" ]; then
    release_api="https://api.github.com/repos/$REPO/releases/tags/v${requested_version#v}"
  else
    release_api="https://api.github.com/repos/$REPO/releases/latest"
  fi

  log "读取 GitHub Release 信息"
  github_get "$release_api" "$download_dir/release.json" || die "读取 GitHub Release 失败，请检查网络或访问频率"
  RELEASE_TAG=$(jq -r '.tag_name // empty' "$download_dir/release.json")
  FULL_NAME=$(jq -r '.assets[] | select(.name | test("_full\\.zip$")) | .name' "$download_dir/release.json" | head -n 1)
  full_url=$(jq -r '.assets[] | select(.name | test("_full\\.zip$")) | .url' "$download_dir/release.json" | head -n 1)
  checksum_url=$(jq -r '.assets[] | select(.name == "SHA256SUMS.txt") | .url' "$download_dir/release.json" | head -n 1)
  [ -n "$RELEASE_TAG" ] || die "Release 缺少版本标签"
  [ -n "$FULL_NAME" ] || die "Release 缺少 full 安装包"
  [ "$FULL_NAME" = "$(basename "$FULL_NAME")" ] || die "Release 文件名不安全"
  [ -n "$full_url" ] || die "Release 缺少 full 安装包下载地址"
  [ -n "$checksum_url" ] || die "Release 缺少 SHA256SUMS.txt"

  FULL_FILE="$download_dir/$FULL_NAME"
  CHECKSUM_FILE="$download_dir/SHA256SUMS.txt"
  log "下载 $RELEASE_TAG"
  github_get "$full_url" "$FULL_FILE" "application/octet-stream" || die "full 安装包下载失败"
  github_get "$checksum_url" "$CHECKSUM_FILE" "application/octet-stream" || die "SHA256SUMS.txt 下载失败"
  grep "  $FULL_NAME\$" "$CHECKSUM_FILE" > "$download_dir/SHA256SUMS.selected" || die "校验文件中找不到 $FULL_NAME"
  (cd "$download_dir" && sha256sum -c SHA256SUMS.selected) || die "安装包 SHA-256 校验失败"
}

validate_release_archive() {
  archive=$1
  archive_list=$(unzip -Z1 "$archive") || die "无法读取安装包目录"
  if printf '%s\n' "$archive_list" | grep -Eq '(^/|(^|/)\.\.(/|$)|(^|/)\.env($|/)|(^|/)data/|(^|/)sessions/|(^|/)\.git/|(^|/)(backup|backups)/|\.session(-journal)?$|\.(sqlite3?|db|rdb|log)$)'; then
    die "安装包包含禁止部署的运行时数据：.env、data/、.git/、session、sqlite、*.log 或 backup"
  fi
}

extract_release_archive() {
  archive=$1
  stage=$2
  mkdir -p "$stage"
  unzip -q "$archive" -d "$stage" || die "安装包解压失败"
  if find "$stage" -type l -print -quit | grep -q .; then
    die "安装包包含不允许的符号链接"
  fi
  for required_file in VERSION Dockerfile docker-compose.yml install.sh manage.sh uninstall.sh scripts/distribution_lib.sh ops/slowlink_watchdog.sh ops/slowlink-watchdog.service; do
    [ -f "$stage/$required_file" ] || die "安装包缺少 $required_file"
  done
  [ -d "$stage/app" ] || die "安装包缺少 app 目录"
}

copy_release_files() {
  stage=$1
  [ "$INSTALL_DIR" = "/opt/slowlink" ] || die "安装目录安全检查失败"
  mkdir -p "$INSTALL_DIR" "$INSTALL_DIR/data/sessions" || die "创建安装目录失败"
  for program_path in $PROGRAM_PATHS; do
    rm -rf -- "$INSTALL_DIR/$program_path" || die "清理旧程序文件失败：$program_path"
  done
  cp -a "$stage"/. "$INSTALL_DIR"/ || die "复制程序文件失败"
  find "$INSTALL_DIR/app" -type f -exec touch {} + || die "刷新应用构建时间失败"
  mkdir -p "$INSTALL_DIR/data/sessions" || die "创建 Session 目录失败"
  chmod 755 "$INSTALL_DIR/install.sh" "$INSTALL_DIR/manage.sh" "$INSTALL_DIR/uninstall.sh" || die "设置管理脚本权限失败"
  chmod 755 "$INSTALL_DIR/scripts/distribution_lib.sh" "$INSTALL_DIR/ops/slowlink_watchdog.sh" || die "设置运维脚本权限失败"
  if [ -f "$INSTALL_DIR/.env" ]; then
    chmod 600 "$INSTALL_DIR/.env" || die "设置配置文件权限失败"
  fi
}

install_watchdog() {
  install -m 644 "$INSTALL_DIR/ops/slowlink-watchdog.service" "/etc/systemd/system/$WATCHDOG_SERVICE" || die "CPU watchdog 服务文件安装失败"
  systemctl daemon-reload || die "systemd 配置刷新失败"
  systemctl enable "$WATCHDOG_SERVICE" >/dev/null 2>&1 || die "CPU watchdog 启用失败"
  systemctl restart "$WATCHDOG_SERVICE" >/dev/null 2>&1 || die "CPU watchdog 启动失败"
}

wait_for_redis_health() {
  timeout_seconds=${1:-60}
  waited=0
  while [ "$waited" -lt "$timeout_seconds" ]; do
    state=$(docker inspect "$REDIS_CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)
    if [ "$state" = "healthy" ]; then
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  return 1
}

wait_for_app_health() {
  timeout_seconds=${1:-90}
  waited=0
  while [ "$waited" -lt "$timeout_seconds" ]; do
    state=$(docker inspect "$APP_CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)
    if [ "$state" = "healthy" ]; then
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  return 1
}

verify_container_version() {
  expected_version=$(cat "$INSTALL_DIR/VERSION")
  actual_version=$(docker exec "$APP_CONTAINER" python -c 'import config; print(config.APP_VERSION)' 2>/dev/null || true)
  [ -n "$actual_version" ] && [ "$actual_version" = "$expected_version" ]
}

show_diagnostics() {
  printf '\n[中文诊断] SlowLink 未通过健康检查\n' >&2
  docker compose -f "$INSTALL_DIR/docker-compose.yml" config 2>&1 | tail -n 40 >&2 || true
  docker inspect "$APP_CONTAINER" --format '容器状态={{.State.Status}} 健康={{if .State.Health}}{{.State.Health.Status}}{{else}}无{{end}} OOM={{.State.OOMKilled}} 错误={{.State.Error}}' 2>&1 >&2 || true
  docker logs --tail 120 "$APP_CONTAINER" 2>&1 >&2 || true
}

verify_installation() {
  web_port_value=$(read_web_port)
  verify_container_version || return 1
  docker exec "$REDIS_CONTAINER" redis-cli --raw PING 2>/dev/null | grep -qx PONG || return 1
  curl -fsS "http://127.0.0.1:$web_port_value/health" 2>/dev/null | grep -q '"status":"ok"' || return 1
  [ "$(systemctl is-active "$WATCHDOG_SERVICE" 2>/dev/null || true)" = "active" ] || return 1
  return 0
}

deploy_application() {
  deploy_mode=$1
  cd "$INSTALL_DIR"
  if [ "$deploy_mode" = "install" ]; then
    log "启动 Redis"
    docker compose up -d redis || die "Redis 启动失败"
  fi
  if ! wait_for_redis_health 60; then
    show_diagnostics
    die "Redis 在 60 秒内未通过健康检查"
  fi
  web_port_value=$(read_web_port)
  assert_web_port_available "$web_port_value" || die "网页端口预检失败"
  log "构建 slowlink_app 镜像"
  docker compose build --no-cache "$APP_SERVICE" || die "slowlink_app 镜像构建失败"
  log "启动 slowlink_app 容器"
  docker compose up -d --no-deps "$APP_SERVICE" || {
    show_diagnostics
    die "slowlink_app 容器启动失败"
  }
  if ! wait_for_app_health 90; then
    show_diagnostics
    die "slowlink_app 在 90 秒内未通过健康检查"
  fi
  if ! verify_container_version; then
    warn "容器版本与发布版本不一致，刷新构建上下文并无缓存重建一次"
    find "$INSTALL_DIR/app" -type f -exec touch {} +
    docker compose build --no-cache "$APP_SERVICE" || die "slowlink_app 无缓存重建失败"
    docker compose up -d --no-deps "$APP_SERVICE" || die "slowlink_app 无缓存重建后启动失败"
    if ! wait_for_app_health 90; then
      show_diagnostics
      die "slowlink_app 无缓存重建后未通过健康检查"
    fi
    verify_container_version || die "容器版本校验失败"
  fi
}
