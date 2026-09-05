#!/usr/bin/env bash
#
# BIND9 Web UI — interactive installer.
#
# Offers three deployment modes:
#   1. Full Docker stack   : BIND9 container + web UI container
#   2. Host BIND + Docker  : manage an existing HOST BIND with the web-UI container
#   3. Manual (all-host)   : BIND + web UI installed directly on this machine
#
# Usage:  sudo ./install.sh   (or: ./install.sh --check | --help)

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# ── Output helpers ───────────────────────────────────────────────────────

if [ -t 1 ]; then
  C_RESET=$'\e[0m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'; C_RED=$'\e[31m'; C_BOLD=$'\e[1m'
else
  C_RESET=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BOLD=""
fi

info()  { printf '%s' "${C_BOLD}==>${C_RESET} $*\n"; }
ok()    { printf '%s%s%s\n' "${C_GREEN}    $*${C_RESET}"; }
warn()  { printf '%s%s%s\n' "${C_YELLOW}!!  $*${C_RESET}"; }
die()   { printf '%s%s%s\n' "${C_RED}FATAL:$*${C_RESET}" >&2; exit 1; }

# ── System detection ─────────────────────────────────────────────────────

OS_ID="unknown"
OS_NAME="unknown"
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_NAME="${NAME:-$OS_ID}"
fi

is_deb() { case "$OS_ID" in debian|ubuntu|linuxmint|pop|elementary|kali|raspbian) return 0;; *) return 1;; esac; }
is_rpm() { case "$OS_ID" in rhel|fedora|centos|almalinux|rocky|ol|amazon) return 0;; *) return 1;; esac; }
is_arch() { case "$OS_ID" in arch|manjaro|endeavouros) return 0;; *) return 1;; esac; }

pkg_install() {
  if is_deb; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq "$@"
  elif is_rpm; then
    if command -v dnf >/dev/null 2>&1; then sudo dnf install -y "$@"
    else sudo yum install -y "$@"; fi
  elif is_arch; then
    sudo pacman -S --noconfirm --needed "$@"
  else
    die "Unsupported distro ($OS_NAME). Please install dependencies manually."
  fi
}

# BIND package names / paths per family (overridable via BIND_CONF_DIR env).
bind_packages() {
  if is_deb; then echo "bind9 bind9utils bind9-dnsutils"
  elif is_rpm; then echo "bind bind-utils"
  elif is_arch; then echo "bind"
  fi
}

bind_conf_dir() {
  if [ -n "${BIND_CONF_DIR:-}" ]; then echo "$BIND_CONF_DIR"; return; fi
  if is_deb; then echo "/etc/bind"; else echo "/etc/named"; fi
}

bind_log_dir() {
  if [ -n "${HOST_BIND_LOG_DIR:-}" ]; then echo "$HOST_BIND_LOG_DIR"; return; fi
  if is_deb; then echo "/var/log/bind"; else echo "/var/log/named"; fi
}

rndc_key_path() {
  local dir; dir="$(bind_conf_dir)"
  if [ -n "${RNDC_KEY:-}" ]; then echo "$RNDC_KEY"; return; fi
  if is_deb; then echo "$dir/rndc.key"; else echo "/etc/rndc.key"; fi
}

named_service() { echo "named"; }

has_cmd() { command -v "$1" >/dev/null 2>&1; }

# ── Generic helpers ──────────────────────────────────────────────────────

random_secret() {
  if has_cmd openssl; then
    openssl rand -hex 32
  else
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

ask_password() {
  # Prompts until a non-empty password is given; stores in WEBUI_PASSWORD.
  WEBUI_PASSWORD=""
  while [ -z "$WEBUI_PASSWORD" ]; do
    read -r -s -p "    Web UI password (used to log in): " WEBUI_PASSWORD
    echo ""
    if [ -z "$WEBUI_PASSWORD" ]; then
      warn "Password cannot be empty. Leave blank on the login page is not supported."
    else
      read -r -s -p "    Confirm password: " WEBUI_PASSWORD_CONFIRM
      echo ""
      if [ "$WEBUI_PASSWORD" != "$WEBUI_PASSWORD_CONFIRM" ]; then
        warn "Passwords do not match. Try again."
        WEBUI_PASSWORD=""
      fi
    fi
  done
  SECRET_KEY="$(random_secret)"
}

write_env_file() {
  # Writes .env from an array of KEY=VALUE lines passed on stdin.
  local envpath="$DIR/.env"
  info "Writing $envpath"
  cat > "$envpath"
  chmod 600 "$envpath" 2>/dev/null || true
}

ensure_named_running() {
  info "Starting named if it is not running"
  sudo systemctl enable named >/dev/null 2>&1 || true
  sudo systemctl start named 2>/dev/null || sudo named 2>/dev/null || true
  sleep 1
  if ! sudo rndc status >/dev/null 2>&1; then
    warn "named may not be running. Check with: sudo rndc status"
  else
    ok "named is running"
  fi
}

ensure_rndc_key() {
  local key; key="$(rndc_key_path)"
  local dir; dir="$(bind_conf_dir)"
  if [ ! -f "$key" ]; then
    info "Generating rndc key at $key"
    sudo rndc-confgen -a
  fi
  if [ -d "$dir" ] && [ -f "$key" ]; then
    sudo chmod 640 "$key" 2>/dev/null || true
    sudo chown root:bind "$key" 2>/dev/null || sudo chown root:named "$key" 2>/dev/null || true
  fi
}

add_logging_channel() {
  # Adds a file channel + default category so the Logs tab has content.
  local dir; dir="$(bind_conf_dir)"
  local conf="$dir/named.conf.options"
  local logfile="$(bind_log_dir)/named.log"
  local marker="# BIND9-WEBUI-LOGGING"
  if [ ! -f "$conf" ]; then
    conf="$dir/named.conf"
  fi
  if ! sudo grep -qF "$marker" "$conf" 2>/dev/null; then
    info "Adding a file logging channel ($logfile) to $conf"
    {
      echo ""
      echo "$marker"
      echo "logging {"
      echo "    channel bind_webui_file { file \"$logfile\" versions 3 size 5m; severity info; };"
      echo "    category default { bind_webui_file; };"
      echo "};"
    } | sudo tee -a "$conf" >/dev/null
    sudo systemctl restart named || true
  else
    ok "Logging channel already present"
  fi
  local ldir; ldir="$(bind_log_dir)"
  sudo mkdir -p "$ldir"
  sudo chown root:bind "$ldir" 2>/dev/null || sudo chown root:named "$ldir" 2>/dev/null || true
}

add_rndc_controls() {
  # Ensures host named listens on TCP 953 for the web-UI container, restricted
  # to loopback + Docker bridge subnets.
  local dir; dir="$(bind_conf_dir)"
  local keyfile; keyfile="$(rndc_key_path)"
  local keyname
  keyname="$(sudo sed -n 's/^key *"\([^"]*\)".*/\1/p' "$keyfile" 2>/dev/null | head -n1)"
  keyname="${keyname:-rndc-key}"
  local marker="# BIND9-WEBUI-CONTROLS"
  local conf="$dir/named.conf"

  if ! grep -q 'port 953' "$conf" 2>/dev/null && ! sudo grep -qF "$marker" "$conf" 2>/dev/null; then
    warn "Host '$dir/named.conf' has no rndc 'controls' block listening on TCP 953,"
    warn "which the web-UI container needs to manage BIND. Adding a restricted one:"
    {
      echo ""
      echo "$marker"
      echo "controls { inet 0.0.0.0 port 953 allow { 127.0.0.1; ::1; 172.16.0.0/12; } keys { \"$keyname\"; }; };"
    } | sudo tee -a "$conf" >/dev/null
    info "Restarting named to apply the controls block"
    sudo systemctl restart named
    ok "rndc TCP 953 control channel enabled (restricted to loopback + 172.16.0.0/12)"
  else
    ok "rndc 953 controls block already present"
  fi
}

ensure_docker() {
  if ! has_cmd docker || ! docker compose version >/dev/null 2>&1; then
    warn "Docker with the compose plugin is required but not installed."
    read -r -p "    Install Docker now? [y/N] " ans
    if [ "${ans:-n}" != "y" ] && [ "${ans:-n}" != "Y" ]; then
      die "Docker is required for this mode. Re-run after installing Docker."
    fi
    info "Installing Docker"
    if is_deb; then
      sudo apt-get update -qq
      sudo apt-get install -y -qq docker.io docker-compose-v2
    elif is_rpm; then
      sudo dnf install -y moby-engine docker-compose-plugin 2>/dev/null \
        || sudo dnf install -y moby-engine || \
        warn "Could not auto-install Docker. Install it manually and re-run."
    elif is_arch; then
      sudo pacman -S --noconfirm --needed docker docker-compose 2>/dev/null \
        || sudo pacman -S --noconfirm --needed docker
    else
      die "Unsupported distro for automatic Docker install. Install Docker manually."
    fi
    sudo systemctl enable --now docker || true
  fi
  docker compose version >/dev/null 2>&1 \
    || die "Docker compose plugin is missing. Install docker-compose."
  ok "Docker + compose plugin available"
}

ensure_host_bind() {
  if ! has_cmd named; then
    warn "BIND9 (named) is not installed."
    read -r -p "    Install BIND9 now? [y/N] " ans
    if [ "${ans:-n}" != "y" ] && [ "${ans:-n}" != "Y" ]; then
      die "BIND9 is required for this mode."
    fi
    # shellcheck disable=SC2046
    pkg_install $(bind_packages)
  fi
  ok "BIND9 present"
  ensure_rndc_key
}

ensure_python_tools() {
  if ! has_cmd python3; then
    info "Installing python3"
  fi
  if is_deb; then
    pkg_install python3 python3-venv
  elif is_rpm; then
    pkg_install python3 python3-pip
  elif is_arch; then
    pkg_install python python-virtualenv
  fi
  has_cmd python3 || die "python3 is required"
}

# ── Mode 1: Full Docker stack ────────────────────────────────────────────

mode_docker_full() {
  info "Mode 1: Full Docker stack (BIND9 + web UI containers)"
  ensure_docker
  ask_password
  write_env_file <<EOF
WEBUI_PASSWORD=$WEBUI_PASSWORD
SECRET_KEY=$SECRET_KEY
EOF
  info "Starting containers (this builds the web UI image on first run)"
  docker compose -f docker-compose-w-bind9.yml up -d --build
  ok "Deployed. Open http://localhost:5000"
}

# ── Mode 2: Host BIND + Docker web UI ────────────────────────────────────

mode_host_bind_docker() {
  info "Mode 2: Host BIND9 + web UI container"
  ensure_docker
  ensure_host_bind
  ensure_named_running
  add_rndc_controls
  add_logging_channel

  local bdir; bdir="$(bind_conf_dir)"
  local ldir; ldir="$(bind_log_dir)"
  ask_password
  write_env_file <<EOF
RNDC_HOST=host.docker.internal
RNDC_PORT=953
BIND_HOST_DIR=$bdir
HOST_BIND_LOG_DIR=$ldir
LOG_FILE=$ldir/named.log
WEBUI_PORT=5000
WEBUI_PASSWORD=$WEBUI_PASSWORD
SECRET_KEY=$SECRET_KEY
EOF

  info "Starting the web UI container (builds the image on first run)"
  docker compose -f docker-compose.yml up -d --build
  ok "Deployed. Open http://localhost:5000"
  ok "Mounted host BIND config from: $bdir"
  ok "Tailing logs from:             $ldir/named.log"
}

# ── Mode 3: Manual (all on host) ─────────────────────────────────────────

mode_manual() {
  info "Mode 3: Manual install (BIND + web UI on this machine)"
  ensure_host_bind
  ensure_named_running
  add_logging_channel
  ensure_python_tools

  info "Setting up Python venv"
  python3 -m venv venv
  ./venv/bin/pip install -q -r requirements.txt
  ok "Dependencies installed"

  ask_password
  info "Writing credentials to /etc/bind9-webui.env"
  local envout="/etc/bind9-webui.env"
  sudo tee "$envout" >/dev/null <<EOF
WEBUI_PASSWORD=$WEBUI_PASSWORD
SECRET_KEY=$SECRET_KEY
EOF
  sudo chmod 600 "$envout"

  info "Installing systemd service"
  {
    echo "[Unit]"
    echo "Description=BIND9 Web UI"
    echo "After=network.target named.service"
    echo "Requires=named.service"
    echo ""
    echo "[Service]"
    echo "Type=simple"
    echo "User=root"
    echo "WorkingDirectory=$DIR"
    echo "ExecStart=$DIR/venv/bin/python3 app.py"
    echo "EnvironmentFile=-/etc/bind9-webui.env"
    echo "Restart=on-failure"
    echo "RestartSec=5"
    echo ""
    echo "[Install]"
    echo "WantedBy=multi-user.target"
  } | sudo tee /etc/systemd/system/bind9-webui.service >/dev/null

  sudo systemctl daemon-reload
  sudo systemctl enable bind9-webui
  sudo systemctl restart bind9-webui
  ok "Deployed. Open http://localhost:5000"
  ok "Manage with: sudo systemctl status bind9-webui"
}

# ── Main menu / flags ────────────────────────────────────────────────────

show_menu() {
  echo ""
  echo "Select how you want to run the BIND9 Web UI:"
  echo ""
  echo "  1) Full Docker stack   - BIND9 and the web UI both in containers"
  echo "  2) Host BIND + Docker  - web UI container managing BIND installed on this machine"
  echo "  3) Manual              - BIND and the web UI both installed directly on this machine"
  echo ""
  while :; do
    read -r -p "Enter your choice [1-3]: " choice
    case "$choice" in
      1) mode_docker_full; return;;
      2) mode_host_bind_docker; return;;
      3) mode_manual; return;;
      *) warn "Please choose 1, 2 or 3.";;
    esac
  done
}

do_check() {
  echo "── System check ─────────────────────────────"
  echo "Distro        : $OS_NAME ($OS_ID)"
  echo "Package tool  : $(is_deb && echo 'apt' || (is_rpm && echo 'rpm/dnf' || (is_arch && echo 'pacman' || echo 'unknown')))"
  echo "BIND dir      : $(bind_conf_dir)"
  echo "Log dir       : $(bind_log_dir)"
  echo "rndc key      : $(rndc_key_path)"
  echo ""
  if has_cmd named; then
    echo "BIND9         : installed"
  else
    echo "BIND9         : NOT installed"
  fi
  if has_cmd docker && docker compose version >/dev/null 2>&1; then
    echo "Docker+compose: available"
  else
    echo "Docker+compose: missing"
  fi
  if has_cmd python3; then
    echo "python3       : $(command -v python3)"
  else
    echo "python3       : missing"
  fi
  echo ""
}

case "${1:-}" in
  --check|-c) do_check; exit 0;;
  --help|-h)
    sed -n '1,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  "")
    if [ "$(id -u)" -eq 0 ]; then
      warn "Running as root. Prefer running as a normal sudo user on some distros."
    fi
    show_menu
    echo ""
    echo "Done!"
    ;;
  *) echo "Unknown option: $1 (use --help)"; exit 1;;
esac