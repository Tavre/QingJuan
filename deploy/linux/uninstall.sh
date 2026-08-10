#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly APP_ROOT="/opt/qingjuan"
readonly REPO_DIR="$APP_ROOT/app"
readonly VENV_DIR="$APP_ROOT/venv"
readonly CONFIG_DIR="/etc/qingjuan"
readonly DATA_DIR="/var/lib/qingjuan"
readonly SERVICE_NAME="qingjuan-backend"
readonly SERVICE_USER="qingjuan"
readonly SERVICE_UNIT="/etc/systemd/system/${SERVICE_NAME}.service"
readonly INFO_COMMAND="/usr/local/sbin/qingjuan-info"
readonly UNINSTALL_COMMAND="/usr/local/sbin/qingjuan-uninstall"

purge_data="false"

usage() {
  cat <<'EOF'
用法：sudo bash deploy/linux/uninstall.sh [选项]

默认卸载程序、服务和配置，但保留 /var/lib/qingjuan 书库数据。

选项：
  --purge-data       同时永久删除书库数据和 qingjuan 系统用户
  -h, --help         显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge-data)
      purge_data="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '未知参数：%s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  printf '卸载脚本必须使用 sudo 或 root 运行。\n' >&2
  exit 1
fi

remove_tree() {
  local target="$1"
  case "$target" in
    "$REPO_DIR"|"$VENV_DIR"|"$CONFIG_DIR"|"$DATA_DIR") ;;
    *)
      printf '拒绝删除未授权路径：%s\n' "$target" >&2
      exit 1
      ;;
  esac
  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf -- "$target"
  fi
}

systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
rm -f -- "$SERVICE_UNIT" "$INFO_COMMAND" "$UNINSTALL_COMMAND"
systemctl daemon-reload
systemctl reset-failed "$SERVICE_NAME" >/dev/null 2>&1 || true

remove_tree "$REPO_DIR"
remove_tree "$VENV_DIR"
remove_tree "$CONFIG_DIR"
rmdir "$APP_ROOT" >/dev/null 2>&1 || true

if [[ "$purge_data" == "true" ]]; then
  remove_tree "$DATA_DIR"
  if id -u "$SERVICE_USER" >/dev/null 2>&1; then
    userdel "$SERVICE_USER"
  fi
  if command -v getent >/dev/null 2>&1 && \
     getent group "$SERVICE_USER" >/dev/null 2>&1; then
    groupdel "$SERVICE_USER" >/dev/null 2>&1 || true
  fi
  printf '青卷后端和书库数据已卸载。\n'
else
  printf '%s\n' \
    '青卷后端已卸载。' \
    '书库数据仍保留在 /var/lib/qingjuan。' \
    '如需永久删除，请在卸载前使用 --purge-data。'
fi
