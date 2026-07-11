#!/bin/sh
set -eu

REPO="suzijin876-lgtm/slowlink"
INSTALL_DIR="/opt/slowlink"
REQUESTED_VERSION=""
UPDATE_ONLY=0
SHOW_MENU=0
TMP_DIR=""
BOOTSTRAP_LIB=""

[ "$#" -eq 0 ] && SHOW_MENU=1

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || pwd)
if [ -f "$SCRIPT_DIR/VERSION" ] && [ -r "$SCRIPT_DIR/scripts/distribution_lib.sh" ]; then
  # shellcheck disable=SC1091
  . "$SCRIPT_DIR/scripts/distribution_lib.sh"
else
  BOOTSTRAP_LIB=$(mktemp /tmp/slowlink-distribution-lib.XXXXXX)
  curl -fsSL "https://raw.githubusercontent.com/$REPO/main/scripts/distribution_lib.sh" -o "$BOOTSTRAP_LIB" || {
    printf '[SlowLink 失败] 下载分发辅助脚本失败\n' >&2
    exit 1
  }
  # shellcheck disable=SC1090
  . "$BOOTSTRAP_LIB"
fi

cleanup() {
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf -- "$TMP_DIR"
  fi
  if [ -n "$BOOTSTRAP_LIB" ] && [ -f "$BOOTSTRAP_LIB" ]; then
    rm -f -- "$BOOTSTRAP_LIB"
  fi
}

trap cleanup 0
trap 'exit 130' INT
trap 'exit 143' TERM

usage() {
  cat <<'EOF'
用法：sudo sh install.sh [--version 1.38.73] [--update]

  --version VERSION  安装指定 GitHub Release
  --update           保留配置和数据并更新到最新版本
  --uninstall        卸载程序并保留配置和数据
  --purge            进入彻底删除确认流程
  --help             显示帮助
EOF
}

run_installed_uninstall() {
  uninstall_mode=$1
  if [ ! -f "$INSTALL_DIR/uninstall.sh" ]; then
    printf '[提示] 尚未检测到已安装的 SlowLink。\n' > /dev/tty
    return 1
  fi
  if [ "$uninstall_mode" = "purge" ]; then
    sh "$INSTALL_DIR/uninstall.sh" --purge
  else
    sh "$INSTALL_DIR/uninstall.sh"
  fi
}

uninstall_menu() {
  while true; do
    cat > /dev/tty <<'EOF'
卸载方式
1.卸载程序但保留配置、Telegram Session、Redis 数据和数据库
2.彻底删除
0.返回
请选择：
EOF
    choice=""
    IFS= read -r choice < /dev/tty || choice=""
    case "$choice" in
      1) run_installed_uninstall preserve && exit 0 ;;
      2) run_installed_uninstall purge && exit 0 ;;
      0) return ;;
      *) printf '[输入错误] 请输入 1、2 或 0。\n' > /dev/tty ;;
    esac
  done
}

main_menu() {
  while true; do
    cat > /dev/tty <<'EOF'
SlowLink 管理
1.安装
2.更新到最新版本
3.卸载
0.退出
请选择：
EOF
    choice=""
    IFS= read -r choice < /dev/tty || choice=""
    case "$choice" in
      1) UPDATE_ONLY=0; return ;;
      2)
        if [ ! -f "$INSTALL_DIR/docker-compose.yml" ]; then
          printf '[提示] 尚未检测到安装，请先选择 1 安装。\n' > /dev/tty
        else
          UPDATE_ONLY=1
          return
        fi
        ;;
      3) uninstall_menu ;;
      0) printf '已退出。\n' > /dev/tty; exit 0 ;;
      *) printf '[输入错误] 请输入 1、2、3 或 0。\n' > /dev/tty ;;
    esac
  done
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      [ "$#" -ge 2 ] || die "--version 缺少版本号"
      REQUESTED_VERSION=${2#v}
      shift 2
      ;;
    --update)
      UPDATE_ONLY=1
      shift
      ;;
    --uninstall)
      require_root
      run_installed_uninstall preserve
      exit $?
      ;;
    --purge)
      require_root
      run_installed_uninstall purge
      exit $?
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *) die "未知参数：$1" ;;
  esac
done

require_root
if [ "$SHOW_MENU" -eq 1 ]; then
  main_menu
fi
if [ "$UPDATE_ONLY" -eq 1 ] && [ ! -f "$INSTALL_DIR/docker-compose.yml" ]; then
  die "尚未检测到安装，请先执行安装"
fi

check_supported_os
TMP_DIR=$(mktemp -d /tmp/slowlink-install.XXXXXX)
install_dependencies
ensure_docker "$TMP_DIR"
download_release "$REQUESTED_VERSION" "$TMP_DIR"
validate_release_archive "$FULL_FILE"
STAGE="$TMP_DIR/stage"
extract_release_archive "$FULL_FILE" "$STAGE"
copy_release_files "$STAGE"

if [ "$UPDATE_ONLY" -eq 1 ]; then
  deploy_application update
else
  deploy_application install
fi
install_watchdog

installed_version=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || printf '未知')
log "完成：SlowLink $installed_version，容器健康检查已通过"
printf '管理命令：sudo %s/manage.sh status\n' "$INSTALL_DIR"
