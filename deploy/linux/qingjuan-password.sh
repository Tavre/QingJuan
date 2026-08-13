#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly REPO_DIR="/opt/qingjuan/app"
readonly VENV_DIR="/opt/qingjuan/venv"
readonly BACKEND_FILE="/etc/qingjuan/backend.env"
readonly SERVICE_NAME="qingjuan-backend"

generate_password="false"

usage() {
  cat <<'EOF'
用法：sudo qingjuan-password [选项]

不带选项时，在终端中隐藏输入并修改管理界面密码。

选项：
  --generate        生成并显示一个新的随机管理密码
  -h, --help        显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --generate)
      generate_password="true"
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
  printf '请使用 sudo qingjuan-password 修改管理密码。\n' >&2
  exit 1
fi
if [[ ! -r "$BACKEND_FILE" || ! -x "$VENV_DIR/bin/python" ]]; then
  printf '未找到青卷服务配置，请先完成 Linux 后端安装。\n' >&2
  exit 1
fi
if [[ ! -f "$REPO_DIR/python-backend/app/admin_password.py" ]]; then
  printf '当前服务版本不包含管理密码工具，请先更新青卷后端。\n' >&2
  exit 1
fi

if [[ "$generate_password" == "true" ]]; then
  new_password="$(
    PYTHONPATH="$REPO_DIR/python-backend" "$VENV_DIR/bin/python" -c \
      'from app.admin_auth import generate_admin_password; print(generate_admin_password())'
  )"
else
  if [[ ! -t 0 ]]; then
    printf '交互改密需要终端；自动生成请使用 sudo qingjuan-password --generate。\n' >&2
    exit 1
  fi
  read -r -s -p '输入新的管理密码：' new_password
  printf '\n'
  read -r -s -p '再次输入新的管理密码：' confirmation
  printf '\n'
  if [[ "$new_password" != "$confirmation" ]]; then
    printf '两次输入的密码不一致。\n' >&2
    exit 1
  fi
fi

printf '%s' "$new_password" | \
  PYTHONPATH="$REPO_DIR/python-backend" "$VENV_DIR/bin/python" \
    -m app.admin_password "$BACKEND_FILE"

if [[ "$generate_password" == "true" ]]; then
  printf '新的随机管理密码：%s\n' "$new_password"
fi

if ! systemctl restart "$SERVICE_NAME"; then
  printf '%s\n' \
    '新管理密码已写入配置，但 systemd 服务重启失败。' \
    '修复服务后重新启动 qingjuan-backend；旧会话会在新进程启动时失效。' >&2
  exit 1
fi
port="$(sed -n 's/^QINGJUAN_PORT=//p' "$BACKEND_FILE" | tail -n 1)"
for _ in $(seq 1 60); do
  if curl --fail --silent --max-time 2 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
    printf '%s\n' \
      '管理密码已修改，所有旧的管理界面会话均已退出。' \
      '管理地址：请运行 sudo qingjuan-info 查看。'
    exit 0
  fi
  sleep 1
done

printf '密码已写入，但服务未在 60 秒内通过健康检查。最近日志：\n' >&2
journalctl -u "$SERVICE_NAME" -n 80 --no-pager >&2 || true
exit 1
