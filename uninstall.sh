#!/bin/sh
set -eu

INSTALL_DIR="/opt/slowlink"
APP_CONTAINER="slowlink_app"
REDIS_CONTAINER="slowlink_redis"
WATCHDOG_SERVICE="slowlink-watchdog.service"
PURGE=0

if [ "${1:-}" = "--purge" ]; then
  PURGE=1
elif [ "$#" -gt 0 ]; then
  printf '[卸载失败] 未知参数：%s\n' "$1" >&2
  exit 1
fi

[ "$(id -u)" -eq 0 ] || {
  printf '[卸载失败] 请使用 root 或 sudo 运行\n' >&2
  exit 1
}

if [ "$PURGE" -eq 1 ]; then
  cat > /dev/tty <<'EOF'
警告：此操作会删除 SlowLink 程序、配置、Telegram Session、Redis 数据和数据库。
请输入 PURGE 确认彻底删除：
EOF
  answer=""
  IFS= read -r answer < /dev/tty || answer=""
  [ "$answer" = "PURGE" ] || {
    printf '已取消彻底删除。\n' > /dev/tty
    exit 0
  }
  [ "$INSTALL_DIR" = "/opt/slowlink" ] || {
    printf '[卸载失败] 安装目录安全检查失败\n' >&2
    exit 1
  }

  systemctl disable --now "$WATCHDOG_SERVICE" >/dev/null 2>&1 || true
  rm -f -- "/etc/systemd/system/$WATCHDOG_SERVICE"
  systemctl daemon-reload

  redis_volume=""
  if docker inspect "$REDIS_CONTAINER" >/dev/null 2>&1; then
    redis_volume=$(docker inspect "$REDIS_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' 2>/dev/null || true)
  fi
  if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
    cd "$INSTALL_DIR"
    docker compose stop app >/dev/null 2>&1 || true
    docker compose rm -f app >/dev/null 2>&1 || true
  else
    docker rm -f "$APP_CONTAINER" >/dev/null 2>&1 || true
  fi
  docker stop "$REDIS_CONTAINER" >/dev/null 2>&1 || true
  docker rm "$REDIS_CONTAINER" >/dev/null 2>&1 || true
  if [ -n "$redis_volume" ]; then
    case "$redis_volume" in
      slowlink*_redis_data|slowlink_redis_data) docker volume rm "$redis_volume" >/dev/null 2>&1 || true ;;
      *) printf '[卸载警告] Redis 卷名称异常，未自动删除：%s\n' "$redis_volume" >&2 ;;
    esac
  fi
  rm -rf -- "$INSTALL_DIR"
  printf 'SlowLink 已彻底删除。\n'
  exit 0
fi

# 保留数据卸载
systemctl disable --now "$WATCHDOG_SERVICE" >/dev/null 2>&1 || true
rm -f -- "/etc/systemd/system/$WATCHDOG_SERVICE"
systemctl daemon-reload
if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
  cd "$INSTALL_DIR"
  docker compose stop app >/dev/null 2>&1 || true
  docker compose rm -f app >/dev/null 2>&1 || true
else
  docker rm -f "$APP_CONTAINER" >/dev/null 2>&1 || true
fi
printf 'SlowLink 程序已卸载，已保留配置、Telegram Session、Redis 数据和数据库。\n'
printf '保留目录：%s\n' "$INSTALL_DIR"
