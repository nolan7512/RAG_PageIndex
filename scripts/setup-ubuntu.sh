#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="rag-pageindex"
DEFAULT_APP_DIR="/opt/rag-pageindex"
APP_DIR="${APP_DIR:-$DEFAULT_APP_DIR}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
API_PROVIDER="${API_PROVIDER:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-}"
OPENAI_CHAT_MODEL="${OPENAI_CHAT_MODEL:-}"
OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-}"
OPENAI_EMBEDDING_DIMENSIONS="${OPENAI_EMBEDDING_DIMENSIONS:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
USE_FAKE_OPENAI="${USE_FAKE_OPENAI:-false}"
ENABLE_RAG_ANYTHING="${ENABLE_RAG_ANYTHING:-true}"
PDF_OCR_ENABLED="${PDF_OCR_ENABLED:-true}"
PDF_OCR_ENGINE="${PDF_OCR_ENGINE:-auto}"
PDF_OCR_LANG="${PDF_OCR_LANG:-vie+eng}"
PDF_OCR_SCALE="${PDF_OCR_SCALE:-2.0}"
PDF_OCR_MAX_PAGES="${PDF_OCR_MAX_PAGES:-100}"
PADDLE_OCR_LANG="${PADDLE_OCR_LANG:-vi}"
PADDLE_OCR_DEVICE="${PADDLE_OCR_DEVICE:-cpu}"
PAGEINDEX_MIN_PAGES="${PAGEINDEX_MIN_PAGES:-30}"
ASSUME_YES="${ASSUME_YES:-false}"

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

is_interactive() {
  [[ -t 0 && "$ASSUME_YES" != "true" ]]
}

prompt_text() {
  local prompt="$1"
  local default_value="${2:-}"
  local answer
  if ! is_interactive; then
    printf "%s" "$default_value"
    return
  fi
  if [[ -n "$default_value" ]]; then
    printf "%s [%s]: " "$prompt" "$default_value" >&2
    read -r answer
    printf "%s" "${answer:-$default_value}"
  else
    printf "%s: " "$prompt" >&2
    read -r answer
    printf "%s" "$answer"
  fi
}

prompt_secret() {
  local prompt="$1"
  local answer
  if ! is_interactive; then
    printf "%s" "${OPENAI_API_KEY:-}"
    return
  fi
  printf "%s: " "$prompt" >&2
  read -r -s answer
  printf "\n" >&2
  printf "%s" "$answer"
}

prompt_menu() {
  local prompt="$1"
  shift
  local options=("$@")
  local answer
  if ! is_interactive; then
    printf "1"
    return
  fi
  printf "\n%s\n" "$prompt" >&2
  local index=1
  for option in "${options[@]}"; do
    printf "  %s) %s\n" "$index" "$option" >&2
    index=$((index + 1))
  done
  while true; do
    printf "Choose [1-%s]: " "${#options[@]}" >&2
    read -r answer
    if [[ "$answer" =~ ^[0-9]+$ ]] && (( answer >= 1 && answer <= ${#options[@]} )); then
      printf "%s" "$answer"
      return
    fi
    warn "Invalid choice."
  done
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
  set_env_value ENABLE_RAG_ANYTHING "$ENABLE_RAG_ANYTHING"
  set_env_value PDF_OCR_ENABLED "$PDF_OCR_ENABLED"
  set_env_value PDF_OCR_ENGINE "$PDF_OCR_ENGINE"
  set_env_value PDF_OCR_LANG "$PDF_OCR_LANG"
  set_env_value PDF_OCR_SCALE "$PDF_OCR_SCALE"
  set_env_value PDF_OCR_MAX_PAGES "$PDF_OCR_MAX_PAGES"
  set_env_value PADDLE_OCR_LANG "$PADDLE_OCR_LANG"
  set_env_value PADDLE_OCR_DEVICE "$PADDLE_OCR_DEVICE"
  set_env_value PAGEINDEX_MIN_PAGES "$PAGEINDEX_MIN_PAGES"

  local current_pg_password
  current_pg_password="$(get_env_value POSTGRES_PASSWORD)"
  set_env_value DATABASE_URL "postgresql+psycopg://rag:${current_pg_password}@postgres:5432/rag_pageindex"

  configure_api_provider

  printf "%s" "$(get_env_value ADMIN_PASSWORD)" > .admin-password.generated
  chmod 600 .admin-password.generated
}

configure_api_provider() {
  local provider="${API_PROVIDER}"
  if [[ -z "$provider" && is_interactive ]]; then
    local choice
    choice="$(prompt_menu "Select AI API provider" \
      "OpenAI" \
      "Google Gemini OpenAI-compatible" \
      "OpenRouter OpenAI-compatible" \
      "Together AI OpenAI-compatible" \
      "Custom OpenAI-compatible endpoint" \
      "Demo mode without API key")"
    case "$choice" in
      1) provider="openai" ;;
      2) provider="gemini" ;;
      3) provider="openrouter" ;;
      4) provider="together" ;;
      5) provider="custom" ;;
      6) provider="fake" ;;
    esac
  fi
  provider="${provider:-openai}"

  case "$provider" in
    openai)
      OPENAI_BASE_URL="${OPENAI_BASE_URL:-}"
      OPENAI_CHAT_MODEL="${OPENAI_CHAT_MODEL:-gpt-5.4-mini}"
      OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}"
      OPENAI_EMBEDDING_DIMENSIONS="${OPENAI_EMBEDDING_DIMENSIONS:-1536}"
      ;;
    gemini)
      OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://generativelanguage.googleapis.com/v1beta/openai/}"
      OPENAI_CHAT_MODEL="${OPENAI_CHAT_MODEL:-gemini-2.5-flash}"
      OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-text-embedding-004}"
      OPENAI_EMBEDDING_DIMENSIONS="${OPENAI_EMBEDDING_DIMENSIONS:-768}"
      ;;
    openrouter)
      OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://openrouter.ai/api/v1}"
      OPENAI_CHAT_MODEL="${OPENAI_CHAT_MODEL:-google/gemini-2.5-flash}"
      OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}"
      OPENAI_EMBEDDING_DIMENSIONS="${OPENAI_EMBEDDING_DIMENSIONS:-1536}"
      warn "OpenRouter may not provide embeddings for every account/model. If ingestion fails, use OpenAI/Gemini embeddings or a custom embedding-compatible endpoint."
      ;;
    together)
      OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.together.xyz/v1}"
      OPENAI_CHAT_MODEL="${OPENAI_CHAT_MODEL:-meta-llama/Llama-3.3-70B-Instruct-Turbo}"
      OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-BAAI/bge-large-en-v1.5}"
      OPENAI_EMBEDDING_DIMENSIONS="${OPENAI_EMBEDDING_DIMENSIONS:-1024}"
      ;;
    custom)
      OPENAI_BASE_URL="${OPENAI_BASE_URL:-$(prompt_text "OpenAI-compatible base URL" "$(get_env_value OPENAI_BASE_URL)")}"
      OPENAI_CHAT_MODEL="${OPENAI_CHAT_MODEL:-$(prompt_text "Default chat model" "$(get_env_value OPENAI_CHAT_MODEL)")}"
      OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-$(prompt_text "Default embedding model" "$(get_env_value OPENAI_EMBEDDING_MODEL)")}"
      OPENAI_EMBEDDING_DIMENSIONS="${OPENAI_EMBEDDING_DIMENSIONS:-$(prompt_text "Embedding dimensions" "$(get_env_value OPENAI_EMBEDDING_DIMENSIONS)")}"
      ;;
    fake)
      USE_FAKE_OPENAI="true"
      OPENAI_BASE_URL=""
      OPENAI_CHAT_MODEL="${OPENAI_CHAT_MODEL:-fake-chat}"
      OPENAI_EMBEDDING_MODEL="${OPENAI_EMBEDDING_MODEL:-fake-embedding}"
      OPENAI_EMBEDDING_DIMENSIONS="${OPENAI_EMBEDDING_DIMENSIONS:-1536}"
      ;;
    *)
      die "Unsupported API_PROVIDER '${provider}'. Use openai, gemini, openrouter, together, custom, or fake."
      ;;
  esac

  if [[ "$provider" != "fake" ]]; then
    local existing_key
    existing_key="$(get_env_value OPENAI_API_KEY)"
    if [[ -z "$OPENAI_API_KEY" && is_interactive ]]; then
      if [[ -n "$existing_key" ]]; then
        local keep
        keep="$(prompt_text "Existing API key found. Keep it? (Y/n)" "Y")"
        if [[ "$keep" =~ ^[Nn] ]]; then
          OPENAI_API_KEY="$(prompt_secret "Paste API key")"
        else
          OPENAI_API_KEY="$existing_key"
        fi
      else
        OPENAI_API_KEY="$(prompt_secret "Paste API key")"
      fi
    fi
    OPENAI_API_KEY="${OPENAI_API_KEY:-$existing_key}"
    if [[ -z "$OPENAI_API_KEY" ]]; then
      warn "API key is empty. The app will start, but ingestion/search/chat will fail until OPENAI_API_KEY is set."
    else
      check_api_and_choose_models "$provider"
    fi
  fi

  set_env_value API_PROVIDER "$provider"
  set_env_value USE_FAKE_OPENAI "$USE_FAKE_OPENAI"
  set_env_value OPENAI_API_KEY "$OPENAI_API_KEY"
  set_env_value OPENAI_BASE_URL "$OPENAI_BASE_URL"
  set_env_value OPENAI_CHAT_MODEL "$OPENAI_CHAT_MODEL"
  set_env_value OPENAI_EMBEDDING_MODEL "$OPENAI_EMBEDDING_MODEL"
  set_env_value OPENAI_EMBEDDING_DIMENSIONS "$OPENAI_EMBEDDING_DIMENSIONS"
}

check_api_and_choose_models() {
  local provider="$1"
  local base_url="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
  local models_url="${base_url%/}/models"
  local response_file
  local status_file
  response_file="$(mktemp)"
  status_file="$(mktemp)"

  log "Checking API connection for ${provider}"
  local http_code
  http_code="$(curl -sS -L \
    -H "Authorization: Bearer ${OPENAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -o "$response_file" \
    -w "%{http_code}" \
    "$models_url" 2>"$status_file" || true)"

  if [[ "$http_code" =~ ^2 ]]; then
    log "API key check passed"
    if command -v python3 >/dev/null 2>&1; then
      choose_models_from_response "$response_file"
    fi
  else
    warn "Could not verify API key at ${models_url}. HTTP ${http_code}. Continuing with default model settings."
    if [[ -s "$status_file" ]]; then
      warn "$(cat "$status_file")"
    fi
  fi

  rm -f "$response_file" "$status_file"
}

choose_models_from_response() {
  local response_file="$1"
  local chat_models_file
  local embedding_models_file
  chat_models_file="$(mktemp)"
  embedding_models_file="$(mktemp)"

  python3 - "$response_file" "$chat_models_file" "$embedding_models_file" <<'PY'
import json
import sys

response_path, chat_path, embedding_path = sys.argv[1:4]
try:
    data = json.load(open(response_path, encoding="utf-8"))
except Exception:
    data = {}

items = data.get("data", data if isinstance(data, list) else [])
ids = []
for item in items:
    if isinstance(item, dict):
        mid = item.get("id") or item.get("name")
    else:
        mid = str(item)
    if mid:
        ids.append(str(mid))

chat_markers = ("gpt", "gemini", "claude", "llama", "qwen", "deepseek", "mistral", "mixtral")
embed_markers = ("embed", "embedding", "bge", "e5", "gte")
chat = [mid for mid in ids if any(marker in mid.lower() for marker in chat_markers)]
embedding = [mid for mid in ids if any(marker in mid.lower() for marker in embed_markers)]

open(chat_path, "w", encoding="utf-8").write("\n".join(chat[:30]))
open(embedding_path, "w", encoding="utf-8").write("\n".join(embedding[:30]))
PY

  if is_interactive && [[ -s "$chat_models_file" ]]; then
    OPENAI_CHAT_MODEL="$(choose_model_from_file "Select chat model" "$chat_models_file" "$OPENAI_CHAT_MODEL")"
  fi
  if is_interactive && [[ -s "$embedding_models_file" ]]; then
    OPENAI_EMBEDDING_MODEL="$(choose_model_from_file "Select embedding model" "$embedding_models_file" "$OPENAI_EMBEDDING_MODEL")"
    OPENAI_EMBEDDING_DIMENSIONS="$(prompt_text "Embedding dimensions for ${OPENAI_EMBEDDING_MODEL}" "$OPENAI_EMBEDDING_DIMENSIONS")"
  fi

  rm -f "$chat_models_file" "$embedding_models_file"
}

choose_model_from_file() {
  local prompt="$1"
  local file="$2"
  local default_model="$3"
  mapfile -t models < "$file"
  models+=("Keep default: ${default_model}")
  local choice
  choice="$(prompt_menu "$prompt" "${models[@]}")"
  if (( choice == ${#models[@]} )); then
    printf "%s" "$default_model"
  else
    printf "%s" "${models[$((choice - 1))]}"
  fi
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
API provider:      $(get_env_value API_PROVIDER)
Chat model:        $(get_env_value OPENAI_CHAT_MODEL)
Embedding model:   $(get_env_value OPENAI_EMBEDDING_MODEL)

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
