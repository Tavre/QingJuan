#!/usr/bin/env bash
set -Eeuo pipefail

readonly CONFIG_DIR="/etc/qingjuan"
readonly CLIENT_FILE="$CONFIG_DIR/client.env"
readonly BACKEND_FILE="$CONFIG_DIR/backend.env"
readonly SERVICE_NAME="qingjuan-backend"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  printf '请使用 sudo qingjuan-info 查看连接 Token。\n' >&2
  exit 1
fi

if [[ ! -r "$CLIENT_FILE" || ! -r "$BACKEND_FILE" ]]; then
  printf '未找到青卷连接配置，请先运行 deploy/linux/install.sh。\n' >&2
  exit 1
fi

read_value() {
  local file="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$file" | tail -n 1
}

backend_url="$(read_value "$CLIENT_FILE" QINGJUAN_BACKEND_URL)"
admin_url="${backend_url%/}/admin/"
connection_token="$(read_value "$CLIENT_FILE" QINGJUAN_CONNECTION_TOKEN)"
port="$(read_value "$BACKEND_FILE" QINGJUAN_PORT)"
service_state="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)"
health_state="不可用"
if curl --fail --silent --max-time 3 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
  health_state="正常"
fi

printf '%s\n' \
  '============================================================' \
  '青卷服务连接与管理信息' \
  "FastAPI 地址：${backend_url}" \
  "连接 Token：${connection_token}" \
  "管理界面：${admin_url}" \
  "systemd 状态：${service_state}" \
  "健康检查：${health_state}" \
  '客户端地址不要附加 /api/v1。' \
  '修改管理密码：sudo qingjuan-password' \
  '服务日志：sudo journalctl -u qingjuan-backend -f' \
  '============================================================'
