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

public_url=""
bind_host="127.0.0.1"
port="19453"
rotate_token="false"
install_packages="true"

usage() {
  cat <<'EOF'
用法：sudo bash deploy/linux/install.sh --url <客户端地址> [选项]

必需：
  --url URL           Windows 客户端使用的 FastAPI 根地址，不含 /api/v1

选项：
  --bind HOST         Uvicorn 监听地址，默认 127.0.0.1
  --port PORT         监听端口，默认 19453
  --rotate-token      重新生成连接 Token
  --skip-packages     不使用 apt 安装系统依赖
  -h, --help          显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      if [[ $# -lt 2 ]]; then
        printf '%s 缺少参数值。\n' "$1" >&2
        exit 2
      fi
      public_url="${2:-}"
      shift 2
      ;;
    --bind)
      if [[ $# -lt 2 ]]; then
        printf '%s 缺少参数值。\n' "$1" >&2
        exit 2
      fi
      bind_host="${2:-}"
      shift 2
      ;;
    --port)
      if [[ $# -lt 2 ]]; then
        printf '%s 缺少参数值。\n' "$1" >&2
        exit 2
      fi
      port="${2:-}"
      shift 2
      ;;
    --rotate-token)
      rotate_token="true"
      shift
      ;;
    --skip-packages)
      install_packages="false"
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
  printf '安装脚本必须使用 sudo 或 root 运行。\n' >&2
  exit 1
fi
if [[ -z "$public_url" ]]; then
  printf '必须通过 --url 指定 Windows 客户端连接地址。\n' >&2
  usage >&2
  exit 2
fi
if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
  printf '端口必须是 1 到 65535 之间的整数。\n' >&2
  exit 2
fi
if [[ ! -f "$REPO_DIR/python-backend/app/main.py" ]]; then
  printf '未找到 %s，请先将仓库克隆到 /opt/qingjuan/app。\n' "$REPO_DIR" >&2
  exit 1
fi

install_system_packages() {
  if [[ "$install_packages" != "true" ]]; then
    return
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    printf '当前系统没有 apt-get；请手动安装 Python 3.11+、venv、Git、curl、Chromium 与 Noto CJK 字体。\n' >&2
    return
  fi
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates curl fonts-noto-cjk git python3 python3-venv
  if ! command -v chromium >/dev/null 2>&1 && \
     ! command -v chromium-browser >/dev/null 2>&1 && \
     ! command -v google-chrome >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y chromium
  fi
}

find_browser() {
  local candidate
  for candidate in chromium chromium-browser google-chrome; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

install_system_packages

for command_name in python3 git curl systemctl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf '缺少系统命令：%s\n' "$command_name" >&2
    exit 1
  fi
done

python3 - "$public_url" "$bind_host" <<'PY'
import ipaddress
import socket
import sys
from urllib.parse import urlsplit

public_url, bind_host = sys.argv[1:]
if any(character.isspace() or not character.isprintable() for character in public_url):
    raise SystemExit("--url 不得包含空白或控制字符")
parsed = urlsplit(public_url)
if parsed.scheme not in {"http", "https"} or not parsed.hostname:
    raise SystemExit("--url 必须是有效的 http/https FastAPI 根地址")
if parsed.username or parsed.password or parsed.query or parsed.fragment:
    raise SystemExit("--url 不得包含账号、密码、查询参数或片段")
if public_url.rstrip("/").endswith("/api/v1"):
    raise SystemExit("--url 不得包含 /api/v1")
try:
    parsed.port
except ValueError as error:
    raise SystemExit("--url 端口无效") from error

private_networks = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)
if parsed.scheme == "http":
    try:
        addresses = {ipaddress.ip_address(parsed.hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(parsed.hostname, parsed.port or 80)
            }
        except socket.gaierror as error:
            raise SystemExit("HTTP 客户端地址无法解析；请使用私有 IP 或配置 HTTPS") from error
    if not addresses or any(
        not any(address in network for network in private_networks)
        for address in addresses
    ):
        raise SystemExit("HTTP 只允许私有网络地址；公网地址必须使用 HTTPS 反向代理")
if not bind_host.strip() or any(character.isspace() for character in bind_host):
    raise SystemExit("--bind 不能为空或包含空白字符")
try:
    ipaddress.ip_address(bind_host.strip("[]"))
except ValueError:
    if bind_host != "localhost":
        raise SystemExit("--bind 必须是 IP 地址或 localhost")
PY

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("青卷 Linux 后端要求 Python 3.11 或更高版本")
PY

browser_path="$(find_browser || true)"
if [[ -z "$browser_path" ]]; then
  printf '未找到 Chromium/Chrome，请安装后重试。\n' >&2
  exit 1
fi

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
install -d -o root -g root -m 0755 "$APP_ROOT"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$DATA_DIR"
install -d -o root -g root -m 0700 "$CONFIG_DIR"
install -d -o root -g systemd-journal -m 2755 /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal >/dev/null 2>&1 || true
systemctl restart systemd-journald

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$REPO_DIR/python-backend/requirements.txt"
"$VENV_DIR/bin/python" -m pip check

client_file="$CONFIG_DIR/client.env"
connection_token=""
if [[ "$rotate_token" != "true" && -f "$client_file" ]]; then
  connection_token="$(sed -n 's/^QINGJUAN_CONNECTION_TOKEN=//p' "$client_file" | tail -n 1)"
fi
if [[ ! "$connection_token" =~ ^[0-9a-f]{64}$ ]]; then
  connection_token="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
fi
token_digest="$(printf '%s' "$connection_token" | python3 -c '
import hashlib
import sys
print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())
')"
public_url="${public_url%/}"

printf '%s\n' \
  "QINGJUAN_AUTH_TOKEN_SHA256=$token_digest" \
  "QINGJUAN_DATA_DIR=$DATA_DIR" \
  "QINGJUAN_BROWSER_EXECUTABLE=$browser_path" \
  "QINGJUAN_PUBLIC_URL=$public_url" \
  "QINGJUAN_BIND_HOST=$bind_host" \
  "QINGJUAN_PORT=$port" \
  > "$CONFIG_DIR/backend.env"

printf '%s\n' \
  "QINGJUAN_BACKEND_URL=$public_url" \
  "QINGJUAN_CONNECTION_TOKEN=$connection_token" \
  > "$client_file"

chmod 0600 "$CONFIG_DIR/backend.env" "$client_file"
chown root:root "$CONFIG_DIR/backend.env" "$client_file"
install -o root -g root -m 0644 "$REPO_DIR/deploy/linux/qingjuan-backend.service" "$SERVICE_UNIT"
install -o root -g root -m 0755 "$REPO_DIR/deploy/linux/qingjuan-info.sh" "$INFO_COMMAND"

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

healthy="false"
for _ in $(seq 1 60); do
  if curl --fail --silent --max-time 2 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
    healthy="true"
    break
  fi
  sleep 1
done
if [[ "$healthy" != "true" ]]; then
  printf '后端未在 60 秒内通过健康检查。最近日志：\n' >&2
  journalctl -u "$SERVICE_NAME" -n 80 --no-pager >&2 || true
  exit 1
fi

"$INFO_COMMAND"
