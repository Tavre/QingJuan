#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly REPO_DIR="/opt/qingjuan/app"
readonly VENV_DIR="/opt/qingjuan/venv"
readonly SERVICE_NAME="qingjuan-backend"
readonly SERVICE_USER="qingjuan"

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
  "$REPO_DIR/deploy/linux/uninstall.sh" \
  "/usr/local/sbin/qingjuan-uninstall"
systemctl daemon-reload
systemctl start "$SERVICE_NAME"
restart_required="false"

port="$(sed -n 's/^QINGJUAN_PORT=//p' /etc/qingjuan/backend.env | tail -n 1)"
for _ in $(seq 1 60); do
  if curl --fail --silent --max-time 2 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
    /usr/local/sbin/qingjuan-info
    exit 0
  fi
  sleep 1
done

printf '更新后端未在 60 秒内通过健康检查。\n' >&2
journalctl -u "$SERVICE_NAME" -n 80 --no-pager >&2 || true
exit 1
