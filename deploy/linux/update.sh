#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly REPO_DIR="/opt/qingjuan/app"
readonly VENV_DIR="/opt/qingjuan/venv"
readonly SERVICE_NAME="qingjuan-backend"
readonly SERVICE_USER="qingjuan"
readonly CONFIG_DIR="/etc/qingjuan"
readonly BACKEND_FILE="/etc/qingjuan/backend.env"
readonly CLIENT_FILE="/etc/qingjuan/client.env"
readonly PASSWORD_COMMAND="/usr/local/sbin/qingjuan-password"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  printf '更新脚本必须使用 sudo 或 root 运行。\n' >&2
  exit 1
fi
if [[ ! -d "$REPO_DIR/.git" ]]; then
  printf '未找到 %s/.git，无法从远端更新。\n' "$REPO_DIR" >&2
  exit 1
fi
if [[ -n "$(git -C "$REPO_DIR" status --porcelain --untracked-files=no)" ]]; then
  printf '服务器仓库存在已跟踪的未提交改动，已拒绝覆盖。\n' >&2
  exit 1
fi

systemctl stop "$SERVICE_NAME"
restart_required="true"
on_exit() {
  if [[ "$restart_required" == "true" ]]; then
    systemctl start "$SERVICE_NAME" >/dev/null 2>&1 || true
  fi
}
trap on_exit EXIT

git -C "$REPO_DIR" pull --ff-only
"$VENV_DIR/bin/python" -m pip install -r "$REPO_DIR/python-backend/requirements.txt"
"$VENV_DIR/bin/python" -m pip check
admin_static_dir="$REPO_DIR/python-backend/app/admin_static"
if [[ ! -f "$admin_static_dir/index.html" ]] || \
   ! grep -Fq 'id="root"' "$admin_static_dir/index.html" || \
   ! compgen -G "$admin_static_dir/assets/*.js" >/dev/null; then
  printf '更新版本缺少已构建的管理界面。\n' >&2
  exit 1
fi

initial_admin_password=""
admin_password_hash="$(sed -n 's/^QINGJUAN_ADMIN_PASSWORD_HASH=//p' "$BACKEND_FILE" | tail -n 1)"
if [[ -z "$admin_password_hash" ]]; then
  initial_admin_password="$(
    PYTHONPATH="$REPO_DIR/python-backend" "$VENV_DIR/bin/python" -c \
      'from app.admin_auth import generate_admin_password; print(generate_admin_password())'
  )"
  printf '%s' "$initial_admin_password" | \
    PYTHONPATH="$REPO_DIR/python-backend" "$VENV_DIR/bin/python" \
      -m app.admin_password "$BACKEND_FILE"
else
  PYTHONPATH="$REPO_DIR/python-backend" "$VENV_DIR/bin/python" \
    -m app.admin_password --ensure-session-secret "$BACKEND_FILE"
fi
install -d -o root -g "$SERVICE_USER" -m 0750 "$CONFIG_DIR"
if grep -q '^QINGJUAN_CONNECTION_TOKEN_FILE=' "$BACKEND_FILE"; then
  sed -i "s|^QINGJUAN_CONNECTION_TOKEN_FILE=.*$|QINGJUAN_CONNECTION_TOKEN_FILE=$CLIENT_FILE|" "$BACKEND_FILE"
else
  printf 'QINGJUAN_CONNECTION_TOKEN_FILE=%s\n' "$CLIENT_FILE" >> "$BACKEND_FILE"
fi
chmod 0600 "$BACKEND_FILE"
chown root:root "$BACKEND_FILE"
if [[ -f "$CLIENT_FILE" ]]; then
  chmod 0640 "$CLIENT_FILE"
  chown root:"$SERVICE_USER" "$CLIENT_FILE"
fi
# Restore service access after pip creates files under the script's restrictive umask.
chown -R root:"$SERVICE_USER" "$VENV_DIR"
chmod -R u=rwX,g=rX,o= "$VENV_DIR"
install -o root -g root -m 0644 \
  "$REPO_DIR/deploy/linux/qingjuan-backend.service" \
  "/etc/systemd/system/${SERVICE_NAME}.service"
install -o root -g root -m 0755 \
  "$REPO_DIR/deploy/linux/qingjuan-info.sh" \
  "/usr/local/sbin/qingjuan-info"
install -o root -g root -m 0755 \
  "$REPO_DIR/deploy/linux/qingjuan-password.sh" \
  "$PASSWORD_COMMAND"
install -o root -g root -m 0755 \
  "$REPO_DIR/deploy/linux/uninstall.sh" \
  "/usr/local/sbin/qingjuan-uninstall"
systemctl daemon-reload
systemctl start "$SERVICE_NAME"
restart_required="false"

print_initial_admin_password() {
  if [[ -z "$initial_admin_password" ]]; then
    return
  fi
  printf '%s\n' \
    '============================================================' \
    '已为管理界面生成首次登录密码（仅显示这一次）' \
    "管理密码：${initial_admin_password}" \
    '请妥善保存；遗失时运行 sudo qingjuan-password --generate。' \
    '============================================================'
}

port="$(sed -n 's/^QINGJUAN_PORT=//p' /etc/qingjuan/backend.env | tail -n 1)"
for _ in $(seq 1 60); do
  if curl --fail --silent --max-time 2 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
    /usr/local/sbin/qingjuan-info
    print_initial_admin_password
    exit 0
  fi
  sleep 1
done

print_initial_admin_password
printf '更新后端未在 60 秒内通过健康检查。\n' >&2
journalctl -u "$SERVICE_NAME" -n 80 --no-pager >&2 || true
exit 1
