#!/bin/sh
set -eu

REPO="suzijin876-lgtm/slowlink"
INSTALL_DIR="/opt/slowlink"
APP_CONTAINER="slowlink_app"
REDIS_CONTAINER="slowlink_redis"
WATCHDOG_SERVICE="slowlink-watchdog.service"
BACKUP_DIR="/var/backups/slowlink"

if [ ! -r "$INSTALL_DIR/scripts/distribution_lib.sh" ]; then
  printf '[管理失败] 缺少 %s/scripts/distribution_lib.sh\n' "$INSTALL_DIR" >&2
  exit 1
fi
# shellcheck disable=SC1091
. "$INSTALL_DIR/scripts/distribution_lib.sh"

usage() {
  cat <<'EOF'
用法：sudo /opt/slowlink/manage.sh COMMAND

  status     查看版本、容器、Redis、监听和 watchdog 状态
  logs       实时查看 slowlink_app 日志
  restart    只重启 slowlink_app
  update     更新到最新 GitHub Release
  backup     备份配置、Telegram Session 和 Redis 数据
  uninstall  卸载程序并保留配置和数据
  purge      彻底删除 SlowLink 自有资源
EOF
}

redis_value() {
  redis_key=$1
  docker exec "$REDIS_CONTAINER" redis-cli --raw GET "$redis_key" 2>/dev/null || printf '不可用'
}

show_status() {
  version=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || printf '未知')
  printf '版本：%s\n' "$version"
  if docker inspect "$APP_CONTAINER" >/dev/null 2>&1; then
    docker inspect "$APP_CONTAINER" --format '应用：{{.State.Status}} / {{if .State.Health}}{{.State.Health.Status}}{{else}}无健康检查{{end}}，重启={{.RestartCount}}，OOM={{.State.OOMKilled}}'
    docker stats --no-stream --format '资源：CPU {{.CPUPerc}}，内存 {{.MemUsage}}' "$APP_CONTAINER" 2>/dev/null || true
  else
    printf '应用：未安装或未运行\n'
  fi
  if docker inspect "$REDIS_CONTAINER" >/dev/null 2>&1; then
    docker inspect "$REDIS_CONTAINER" --format 'Redis：{{.State.Status}} / {{if .State.Health}}{{.State.Health.Status}}{{else}}无健康检查{{end}}'
    printf '监听期望：%s\n' "$(redis_value listener_desired_state)"
    printf '监听状态：%s\n' "$(redis_value bot_status)"
    printf 'Telegram 登录：%s\n' "$(redis_value tg_logged_in)"
    printf '转发目标：%s\n' "$(redis_value target_chat)"
    flow_stats=$(redis_value listener_flow_stats)
    printf '最近消息流：%s\n' "${flow_stats:-暂无}"
  else
    printf 'Redis：未运行\n'
  fi
  printf 'Telegram Session 文件：%s 个\n' "$(find "$INSTALL_DIR/data/sessions" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')"
  printf 'CPU watchdog：%s\n' "$(systemctl is-active "$WATCHDOG_SERVICE" 2>/dev/null || printf 'inactive')"
}

restart_app() {
  cd "$INSTALL_DIR"
  docker compose restart app || die "slowlink_app 重启失败"
  if ! wait_for_app_health 90; then
    show_diagnostics
    die "slowlink_app 重启后未通过健康检查"
  fi
  log "slowlink_app 已重启并通过健康检查"
}

download_installer() {
  installer_output=$1
  installer_url="https://raw.githubusercontent.com/$REPO/main/install.sh"
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" "$installer_url" -o "$installer_output"
  else
    curl -fsSL "$installer_url" -o "$installer_output"
  fi
}

backup_runtime() {
  timestamp=$(date '+%Y%m%d_%H%M%S')
  mkdir -p "$BACKUP_DIR"
  backup_stage=$(mktemp -d /tmp/slowlink-backup.XXXXXX)
  trap 'rm -rf -- "$backup_stage"' 0
  mkdir -p "$backup_stage/runtime"

  if [ -f "$INSTALL_DIR/.env" ]; then
    cp -a "$INSTALL_DIR/.env" "$backup_stage/runtime/.env"
  fi
  if [ -d "$INSTALL_DIR/data" ]; then
    cp -a "$INSTALL_DIR/data" "$backup_stage/runtime/data"
  fi

  if docker inspect "$REDIS_CONTAINER" >/dev/null 2>&1; then
    log "请求 Redis 生成持久化快照"
    docker exec "$REDIS_CONTAINER" redis-cli BGSAVE >/dev/null || die "Redis BGSAVE 失败"
    backup_wait=0
    while [ "$backup_wait" -lt 60 ]; do
      progress=$(docker exec "$REDIS_CONTAINER" redis-cli --raw INFO persistence 2>/dev/null | tr -d '\r' | sed -n 's/^rdb_bgsave_in_progress://p')
      status=$(docker exec "$REDIS_CONTAINER" redis-cli --raw INFO persistence 2>/dev/null | tr -d '\r' | sed -n 's/^rdb_last_bgsave_status://p')
      if [ "$progress" = "0" ] && [ "$status" = "ok" ]; then
        break
      fi
      sleep 1
      backup_wait=$((backup_wait + 1))
    done
    [ "$backup_wait" -lt 60 ] || die "Redis 快照在 60 秒内未完成"
    docker cp "$REDIS_CONTAINER:/data/dump.rdb" "$backup_stage/runtime/redis_dump.rdb" >/dev/null || die "复制 Redis 快照失败"
  else
    warn "Redis 容器未运行，本次备份不包含 Redis 快照"
  fi

  {
    printf 'created_at=%s\n' "$(date -Iseconds)"
    printf 'version=%s\n' "$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || printf '未知')"
    printf 'app_container=%s\n' "$(docker inspect "$APP_CONTAINER" --format '{{.Id}}' 2>/dev/null || printf 'missing')"
    printf 'redis_container=%s\n' "$(docker inspect "$REDIS_CONTAINER" --format '{{.Id}}' 2>/dev/null || printf 'missing')"
  } > "$backup_stage/runtime/MANIFEST.txt"

  backup_file="$BACKUP_DIR/slowlink_backup_$timestamp.tar.gz"
  tar -C "$backup_stage/runtime" -czf "$backup_file" . || die "创建备份压缩包失败"
  chmod 600 "$backup_file"
  log "备份完成：$backup_file"
}

require_root
[ "$#" -ge 1 ] || { usage; exit 1; }

case "$1" in
  status)
    show_status
    ;;
  logs)
    exec docker logs -f --tail 100 "$APP_CONTAINER"
    ;;
  restart)
    restart_app
    ;;
  update)
    update_installer=$(mktemp /tmp/slowlink-update.XXXXXX)
    trap 'rm -f -- "$update_installer"' 0
    download_installer "$update_installer" || die "下载安装脚本失败"
    sh "$update_installer" --update
    ;;
  backup)
    backup_runtime
    ;;
  uninstall)
    exec "$INSTALL_DIR/uninstall.sh"
    ;;
  purge)
    exec "$INSTALL_DIR/uninstall.sh" --purge
    ;;
  --help|-h|help)
    usage
    ;;
  *)
    die "未知命令：$1"
    ;;
esac
