#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="rag-pageindex"
DEFAULT_APP_DIR="/opt/rag-pageindex"
APP_DIR="${APP_DIR:-$DEFAULT_APP_DIR}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
USE_FAKE_OPENAI="${USE_FAKE_OPENAI:-false}"
ENABLE_RAG_ANYTHING="${ENABLE_RAG_ANYTHING:-true}"
PAGEINDEX_MIN_PAGES="${PAGEINDEX_MIN_PAGES:-30}"

log() {
  printf "\n\033[1;32m[%s]\033[0m %s\n" "$APP_NAME" "$*"
}

warn() {
  printf "\n\033[1;33m[%s]\033[0m %s\n" "$APP_NAME" "$*" >&2
}

die() {
  printf "\n\033[1;31m[%s]\033[0m %s\n" "$APP_NAME" "$*" >&2
  exit 1
}

require_ubuntu() {
  if [[ ! -r /etc/os-release ]]; then
    die "Cannot detect OS. This installer supports Ubuntu only."
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    die "Detected ${PRETTY_NAME:-unknown OS}. This installer supports Ubuntu only."
  fi
}

as_root_prefix() {
  if [[ "${EUID}" -eq 0 ]]; then
    SUDO=""
  else
    command -v sudo >/dev/null 2>&1 || die "sudo is required when not running as root."
    SUDO="sudo"
  fi
}

random_hex() {
  openssl rand -hex "$1"
}

detect_public_host() {
  if [[ -n "$PUBLIC_HOST" ]]; then
    return
  fi
  PUBLIC_HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -z "$PUBLIC_HOST" ]]; then
    PUBLIC_HOST="localhost"
  fi
}

install_base_packages() {
  log "Installing base packages"
  $SUDO apt-get update
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates \
    curl \
    git \
    gnupg \
    lsb-release \
    openssl \
    rsync
}

configure_docker_repo_for_suite() {
  local suite="$1"
  local arch
  arch="$(dpkg --print-architecture)"

  $SUDO install -m 0755 -d /etc/apt/keyrings
  $SUDO curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  $SUDO chmod a+r /etc/apt/keyrings/docker.asc

  $SUDO tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${suite}
Components: stable
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/docker.asc
EOF
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker and Compose plugin already installed"
    return
  fi

  log "Installing Docker Engine and Compose plugin"
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get remove -y \
    docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc \
    >/dev/null 2>&1 || true

  # shellcheck disable=SC1091
  . /etc/os-release
  local suite="${UBUNTU_CODENAME:-${VERSION_CODENAME:-noble}}"

  configure_docker_repo_for_suite "$suite"
  if ! $SUDO apt-get update || [[ "$(apt-cache policy docker-ce | awk '/Candidate:/ {print $2}')" == "(none)" ]]; then
    warn "Docker packages were not available for Ubuntu suite '${suite}'. Falling back to Docker's Ubuntu 24.04 'noble' repository."
    configure_docker_repo_for_suite "noble"
    $SUDO apt-get update
  fi

  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

  $SUDO systemctl enable --now docker

  if [[ -n "${SUDO:-}" ]]; then
    $SUDO usermod -aG docker "$USER" || true
    warn "User '$USER' was added to the docker group. You may need to log out and back in for docker without sudo."
  fi
}

sync_project_to_app_dir() {
  local source_dir
  source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

  if [[ "$source_dir" == "$APP_DIR" ]]; then
    log "Project already lives at ${APP_DIR}"
    return
  fi

  log "Copying project to ${APP_DIR}"
  $SUDO mkdir -p "$APP_DIR"
  $SUDO rsync -a --delete \
    --exclude ".env" \
    --exclude ".git" \
    --exclude ".serena" \
    --exclude "backend/.venv" \
    --exclude "frontend/node_modules" \
    --exclude "frontend/.next" \
    --exclude "data" \
    "${source_dir}/" "${APP_DIR}/"
  $SUDO chown -R "${USER:-root}:${USER:-root}" "$APP_DIR" || true
}

ensure_env_file() {
  cd "$APP_DIR"
  if [[ ! -f .env ]]; then
    log "Creating .env"
    cp .env.example .env
  else
    log ".env already exists; preserving existing values"
  fi

  local postgres_password secret admin_password frontend_origin api_base
  postgres_password="$(random_hex 18)"
  secret="$(random_hex 32)"
  admin_password="${ADMIN_PASSWORD:-$(random_hex 10)}"
  frontend_origin="http://${PUBLIC_HOST}:3111"
  api_base="http://${PUBLIC_HOST}:8111"

  set_env_if_default POSTGRES_PASSWORD "rag_password" "$postgres_password"
  set_env_if_default SECRET_KEY "replace-with-a-long-random-secret" "$secret"
  set_env_value ADMIN_EMAIL "$ADMIN_EMAIL"
  if [[ -n "$ADMIN_PASSWORD" ]]; then
    set_env_value ADMIN_PASSWORD "$ADMIN_PASSWORD"
  else
    set_env_if_default ADMIN_PASSWORD "change-me-now" "$admin_password"
  fi
  set_env_value FRONTEND_ORIGIN "$frontend_origin"
  set_env_value NEXT_PUBLIC_API_BASE_URL "$api_base"
  set_env_value USE_FAKE_OPENAI "$USE_FAKE_OPENAI"
  set_env_value ENABLE_RAG_ANYTHING "$ENABLE_RAG_ANYTHING"
  set_env_value PAGEINDEX_MIN_PAGES "$PAGEINDEX_MIN_PAGES"

  local current_pg_password
  current_pg_password="$(get_env_value POSTGRES_PASSWORD)"
  set_env_value DATABASE_URL "postgresql+psycopg://rag:${current_pg_password}@postgres:5432/rag_pageindex"

  if [[ -n "$OPENAI_API_KEY" ]]; then
    set_env_value OPENAI_API_KEY "$OPENAI_API_KEY"
  elif [[ "$USE_FAKE_OPENAI" != "true" && -z "$(get_env_value OPENAI_API_KEY)" ]]; then
    warn "OPENAI_API_KEY is empty. The app will run, but ingestion/search/chat will fail unless you set OPENAI_API_KEY or run with USE_FAKE_OPENAI=true."
  fi

  printf "%s" "$(get_env_value ADMIN_PASSWORD)" > .admin-password.generated
  chmod 600 .admin-password.generated
}

get_env_value() {
  local key="$1"
  grep -E "^${key}=" .env | tail -n 1 | cut -d= -f2- || true
}

set_env_value() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')"
  if grep -qE "^${key}=" .env; then
    sed -i "s/^${key}=.*/${key}=${escaped}/" .env
  else
    printf "\n%s=%s\n" "$key" "$value" >> .env
  fi
}

set_env_if_default() {
  local key="$1"
  local default_value="$2"
  local new_value="$3"
  local current
  current="$(get_env_value "$key")"
  if [[ -z "$current" || "$current" == "$default_value" ]]; then
    set_env_value "$key" "$new_value"
  fi
}

open_firewall_ports() {
  if command -v ufw >/dev/null 2>&1 && $SUDO ufw status | grep -q "Status: active"; then
    log "Opening UFW ports 3111 and 8111"
    $SUDO ufw allow 3111/tcp
    $SUDO ufw allow 8111/tcp
  fi
}

start_stack() {
  cd "$APP_DIR"
  log "Building and starting Docker Compose stack"
  $SUDO docker compose pull postgres redis || true
  $SUDO docker compose up --build -d
}

print_summary() {
  local admin_password
  admin_password="$(cat "${APP_DIR}/.admin-password.generated" 2>/dev/null || true)"

  log "Setup complete"
  cat <<EOF

Project directory: ${APP_DIR}
Frontend:          http://${PUBLIC_HOST}:3111
API docs:          http://${PUBLIC_HOST}:8111/docs

Admin email:       $(get_env_value ADMIN_EMAIL)
Admin password:    ${admin_password}

Useful commands:
  cd ${APP_DIR}
  sudo docker compose ps
  sudo docker compose logs -f api worker
  sudo docker compose restart
  sudo docker compose down

EOF
}

main() {
  require_ubuntu
  as_root_prefix
  detect_public_host
  install_base_packages
  install_docker
  sync_project_to_app_dir
  ensure_env_file
  open_firewall_ports
  start_stack
  print_summary
}

main "$@"
