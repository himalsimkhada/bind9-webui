#!/usr/bin/env bash
#
# BIND9 Web UI — API backend installer.
#
# This service is the API-only backend; the user interface lives in the
# companion webui facade (himalsimkhada/webui), which proxies to it.
#
# Offers two deployment modes:
#   1. Full Docker stack   : BIND9 container + API container
#   2. Host BIND + Docker  : manage an existing HOST BIND with the API container
#
# The one-liner does NOT clone the repository: it creates a directory
# (default ~/bind9-webui) and fetches only the compose file (+ shared BIND
# config for mode 1) needed for the mode you pick.
#
# Usage:  sudo ./install.sh   (or: ./install.sh --check | --help)
# One-liner:  curl -fsSL https://raw.githubusercontent.com/himalsimkhada/bind9-webui/main/install.sh | bash

set -euo pipefail

REPO_URL="https://github.com/himalsimkhada/bind9-webui.git"
RAW_BASE="https://raw.githubusercontent.com/himalsimkhada/bind9-webui/main"
WEBUI_REPO_URL="https://github.com/himalsimkhada/webui.git"
WEBUI_PORT="${WEBUI_PORT:-8080}"

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# ── Output helpers ───────────────────────────────────────────────────────

if [ -t 1 ]; then
  C_RESET=$'\e[0m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'; C_RED=$'\e[31m'; C_BOLD=$'\e[1m'
else
  C_RESET=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BOLD=""
fi

info()  { printf '%s\n' "${C_BOLD}==>${C_RESET} $*"; }
ok()    { printf '%s%s%s\n' "${C_GREEN}    $*${C_RESET}"; }
warn()  { printf '%s%s%s\n' "${C_YELLOW}!!  $*${C_RESET}"; }
die()   { printf '%s%s%s\n' "${C_RED}FATAL:$*${C_RESET}" >&2; exit 1; }

has_cmd() { command -v "$1" >/dev/null 2>&1; }

# ── Input helpers ────────────────────────────────────────────────────────
# Under `curl ... | bash` stdin is the script stream, so bare `read` never
# sees a prompt. Read from the controlling terminal when one exists. For
# headless runs (no terminal) the variables below can be pre-set in the
# environment instead of prompting.

have_tty() { ( exec </dev/tty ) 2>/dev/null; }

read_input() {
  local var="$1" prompt="${2:-}"
  local envval=""
  case "$var" in
    target) envval="${TARGET_DIR:-}";;
    choice) envval="${BIND9_MODE:-}";;
    ans)    envval="${BIND9_YES:-}";;
  esac
  if [ -n "$envval" ]; then
    printf -v "$var" '%s' "$envval"
    return 0
  fi
  if have_tty; then
    read -r -p "$prompt" "$var" < /dev/tty
    return 0
  fi
  if [ "$var" = "target" ]; then
    printf -v "$var" '%s' "$PWD/bind9-webui"   # headless default: ./bind9-webui subdir
    return 0
  fi
  die "No terminal available and \$$var was not set (${prompt%:}). Re-run from a terminal or set the env var."
}

read_input_silent() {
  local var="$1" prompt="${2:-}"
  if have_tty; then
    read -r -s -p "$prompt" "$var" < /dev/tty
  else
    die "No terminal available for password input. Set WEBUI_PASSWORD=... and re-run."
  fi
  echo ""
}

# ── Streaming bootstrap ──────────────────────────────────────────────────
# Runs when the script is streamed (curl ... | bash) and there is no local
# checkout: ask where to install, create that directory and fetch the files
# for the chosen mode later (ensure_mode_files). No full repo clone.

if [ ! -f "$DIR/docker-compose.yml" ] && [ ! -f "$DIR/docker-compose-w-bind9.yml" ]; then
  echo "==> One-liner install: no project checkout in \"$DIR\"."
  has_cmd curl || has_cmd wget || die "curl or wget is required for the one-liner install."
  has_cmd git || warn "git is not installed — only the files needed by the installer will be fetched."

  default_target="$PWD/bind9-webui"
  target=""
  read_input target "Install the project into [$default_target]: "
  target="${target:-$default_target}"

  mkdir -p "$target"
  cd "$target"
  DIR="$target"
  info "Project dir: $DIR (the compose file is fetched for the mode you choose)"
fi

# ── File fetch (no repo clone) ───────────────────────────────────────────

fetch_file() {
  local rel="$1"
  local dest="$DIR/$rel"
  mkdir -p "$(dirname "$dest")"
  if has_cmd curl; then
    curl -fsSL "$RAW_BASE/$rel" -o "$dest"
  elif has_cmd wget; then
    wget -qO "$dest" "$RAW_BASE/$rel"
  else
    die "curl or wget is required to fetch $rel"
  fi
}

ensure_mode_files() {
  # The compose file is always saved as docker-compose.yml — whatever mode is
  # picked, `docker compose up` picks it up with no -f flag.
  local mode="$1"
  if [ "$mode" = "1" ]; then
    # The full-stack manifest ships in the repo as docker-compose-w-bind9.yml.
    if [ -f "$DIR/docker-compose-w-bind9.yml" ]; then
      cp -f "$DIR/docker-compose-w-bind9.yml" "$DIR/docker-compose.yml"
    elif has_cmd curl; then
      curl -fsSL "$RAW_BASE/docker-compose-w-bind9.yml" -o "$DIR/docker-compose.yml"
    elif has_cmd wget; then
      wget -qO "$DIR/docker-compose.yml" "$RAW_BASE/docker-compose-w-bind9.yml"
    else
      die "curl or wget is required to fetch docker-compose.yml"
    fi
    for f in named.conf named.conf.options named.conf.local named.conf.default-zones rndc.key root.hints db.local db.127 db.0 db.255; do
      [ -f "$DIR/docker/bind/$f" ] || fetch_file "docker/bind/$f"
    done
  else
    [ -f "$DIR/docker-compose.yml" ] || fetch_file "docker-compose.yml"
  fi
  ok "Mode $mode files present in $DIR (compose file: docker-compose.yml)"
}

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

# ── Generic helpers ──────────────────────────────────────────────────────

random_secret() {
  if has_cmd openssl; then
    openssl rand -hex 32
  else
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

ask_password() {
  # Accepts WEBUI_PASSWORD from the environment (headless runs) or prompts.
  if [ -z "${WEBUI_PASSWORD:-}" ]; then
    WEBUI_PASSWORD=""
    while [ -z "$WEBUI_PASSWORD" ]; do
      read_input_silent WEBUI_PASSWORD "    Web UI password (used to log in): "
      if [ -z "$WEBUI_PASSWORD" ]; then
        warn "Password cannot be empty."
      else
        read_input_silent WEBUI_PASSWORD_CONFIRM "    Confirm password: "
        if [ "$WEBUI_PASSWORD" != "$WEBUI_PASSWORD_CONFIRM" ]; then
          warn "Passwords do not match. Try again."
          WEBUI_PASSWORD=""
        fi
      fi
    done
  else
    ok "Using WEBUI_PASSWORD from the environment"
  fi
  SECRET_KEY="$(random_secret)"
}

write_env_file() {
  # Writes .env from an array of KEY=VALUE lines passed on stdin.
  local envpath="$DIR/.env"
  info "Writing $envpath"
  cat > "$envpath"
  chmod 600 "$envpath" 2>/dev/null || true
}

# ── webui admin facade (companion dashboard) ────────────────────────────

webui_detected() {
  # True when the webui admin facade is already answering on the expected port.
  if has_cmd curl && curl -fsS --max-time 3 "http://127.0.0.1:${WEBUI_PORT}/healthz" >/dev/null 2>&1; then
    return 0
  fi
  if has_cmd docker && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^webui-admin$'; then
    return 0
  fi
  return 1
}

offer_webui_portal() {
  # The dashboard UI lives in the companion webui facade. If it is not running,
  # offer to install it now.
  local tgt="$HOME/webui"
  if webui_detected; then
    ok "webui admin dashboard already running on http://127.0.0.1:${WEBUI_PORT}"
    return
  fi

  if [ -d "$tgt" ] && [ -f "$tgt/install.sh" ]; then
    warn "The webui admin dashboard is NOT running but a checkout exists at $tgt (port $WEBUI_PORT)."
  else
    warn "The webui admin dashboard (himalsimkhada/webui) was not detected on http://127.0.0.1:${WEBUI_PORT}."
  fi
  info "The BIND dashboard is hosted by the webui facade; without it you only get the API."
  ans=""
  read_input ans "    Install the webui admin dashboard now? [Y/n] "
  if [ "${ans:-y}" = "n" ] || [ "${ans:-y}" = "N" ]; then
    warn "Install it later with:  curl -fsSL https://raw.githubusercontent.com/himalsimkhada/webui/main/install.sh | bash"
    return
  fi

  has_cmd git || die "git is required to clone the webui dashboard."
  mkdir -p "$HOME"
  if [ ! -f "$tgt/install.sh" ]; then
    info "Cloning $WEBUI_REPO_URL into $tgt"
    git clone --quiet --depth 1 "$WEBUI_REPO_URL" "$tgt"
  fi
  info "Running the webui dashboard installer (choose Docker or Manual mode)"
  bash "$tgt/install.sh"
  ok "webui admin dashboard installed. Open http://localhost:${WEBUI_PORT}"
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
    ans=""
    read_input ans "    Install Docker now? [y/N] "
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
  fi

  if ! docker compose version >/dev/null 2>&1; then
    die "Docker compose plugin is missing. Install docker-compose and re-run."
  fi
  if ! docker info >/dev/null 2>&1; then
    warn "Docker daemon is not reachable. Starting the docker service..."
    sudo systemctl enable --now docker >/dev/null 2>&1 || true
    sleep 2
  fi
  docker info >/dev/null 2>&1 \
    || die "Docker daemon is not reachable. Start it (sudo systemctl start docker) and re-run."
  ok "Docker + compose plugin available and the daemon is running"
}

ensure_host_bind() {
  if ! has_cmd named; then
    warn "BIND9 (named) is not installed."
    ans=""
    read_input ans "    Install BIND9 now? [y/N] "
    if [ "${ans:-n}" != "y" ] && [ "${ans:-n}" != "Y" ]; then
      die "BIND9 is required for this mode."
    fi
    # shellcheck disable=SC2046
    pkg_install $(bind_packages)
  fi
  ok "BIND9 present"
  ensure_rndc_key
}

# ── Mode 1: Full Docker stack ────────────────────────────────────────────

seed_bind_volume() {
  # The full-stack compose keeps the whole /etc/bind in one named volume
  # (bind9-vol). The ISC image's own /etc/bind only ships bind.keys +
  # named.conf, so on first run we copy the shipped config files in.
  local vol="bind9-vol"
  if ! docker volume inspect "$vol" >/dev/null 2>&1; then
    info "Initializing $vol from the shipped BIND config (docker/bind)"
    docker run --rm --entrypoint sh \
      -v "$vol":/etc/bind \
      -v "$DIR/docker/bind":/seed:ro \
      internetsystemsconsortium/bind9:9.18 -c '\
        cp -a /seed/. /etc/bind/ && \
        mkdir -p /etc/bind/zones && \
        chown -R 53:53 /etc/bind/zones'
    ok "bind9-vol seeded — edit config with: docker run --rm -it -v bind9-vol:/etc/bind sh"
  else
    ok "bind9-vol already initialized"
  fi
}

mode_docker_full() {
  info "Mode 1: Full Docker stack (BIND9 + API containers)"
  ensure_mode_files 1
  ensure_docker
  seed_bind_volume
  ask_password
  write_env_file <<EOF
WEBUI_PASSWORD=$WEBUI_PASSWORD
SECRET_KEY=$SECRET_KEY
EOF
  info "Starting containers (pulls the API image on first run)"
  # Brings the project down first so the per-project network is recreated
  # fresh: reusing a stale network can crash-loop the BIND container (it dies
  # shortly after start, before named even opens its log).
  docker compose -f docker-compose.yml down >/dev/null 2>&1 || true
  # Containers keep the pinned names across projects; compose can only remove
  # its own, so clear the names when an overlapping install left them behind.
  docker rm -f bind9 bind9-webui >/dev/null 2>&1 || true
  docker compose -f docker-compose.yml up -d
  ok "Deployed. API at http://localhost:5000 (UI lives in the webui facade)"
  ok "DNS is published on host 127.0.0.1:5353 (rndc on 127.0.0.1:9353)"

  offer_webui_portal
}

# ── Mode 2: Host BIND + Docker API ────────────────────────────────────────

mode_host_bind_docker() {
  info "Mode 2: Host BIND9 + API container"
  ensure_mode_files 2
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

  info "Starting the API container (pulls the image on first run)"
  docker compose -f docker-compose.yml down >/dev/null 2>&1 || true
  docker rm -f bind9-webui >/dev/null 2>&1 || true
  docker compose -f docker-compose.yml up -d
  ok "Deployed. API at http://localhost:5000 (UI lives in the webui facade)"
  ok "Mounted host BIND config from: $bdir"
  ok "Tailing logs from:             $ldir/named.log"

  offer_webui_portal
}

# ── Main menu / flags ────────────────────────────────────────────────────

show_menu() {
  echo ""
  echo "Select how you want to run the BIND9 backend:"
  echo ""
  echo "  1) Full Docker stack   - BIND9 and the API both in containers"
  echo "  2) Host BIND + Docker  - API container managing BIND installed on this machine"
  echo ""
  while :; do
    choice=""
    read_input choice "Enter your choice [1-2]: "
    case "$choice" in
      1) mode_docker_full; return;;
      2) mode_host_bind_docker; return;;
      *) warn "Please choose 1 or 2.";;
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
  echo ""
}

case "${1:-}" in
  --check|-c) do_check; exit 0;;
  --help|-h)
    sed -n '1,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
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