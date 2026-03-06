#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────
# Chatbot KJRI Dubai — Server Setup Script
# Target: Debian (fresh server)
# ─────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[[ $EUID -ne 0 ]] && error "Jalankan script ini sebagai root: sudo bash install.sh"

# ─── 1. Install Docker ───────────────────────
info "Menginstall Docker..."

apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg lsb-release

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker

info "Docker berhasil diinstall: $(docker --version)"

# ─── 2. Install Ollama (native) ──────────────
info "Menginstall Ollama secara native..."

curl -fsSL https://ollama.com/install.sh | sh

systemctl enable ollama
systemctl start ollama

info "Menunggu Ollama siap..."
sleep 5

# ─── 3. Pull model LLM ───────────────────────
MODEL="${LLM_MODEL:-qwen2.5:0.5b}"

if [[ -f ".env" ]]; then
    PARSED=$(grep -E "^LLM_MODEL=" .env | cut -d= -f2-)
    [[ -n "$PARSED" ]] && MODEL="$PARSED"
fi

info "Menarik model $MODEL..."
ollama pull "$MODEL"

info "Model $MODEL berhasil diunduh."

# ─── 4. Setup environment ────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f ".env" ]]; then
    info "Membuat file .env dari .env.example..."
    cp .env.example .env

    warn "File .env telah dibuat. Edit file tersebut sebelum melanjutkan."
    warn "Minimal isi: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, PGADMIN_EMAIL, PGADMIN_PASSWORD"
    echo ""
    read -rp "Tekan ENTER setelah selesai mengedit .env, atau Ctrl+C untuk membatalkan..."
else
    warn ".env sudah ada, melewati pembuatan."
fi

# ─── 5. Start semua service via Docker Compose ──
info "Membangun dan menjalankan semua Docker service..."

docker compose up -d --build

info "Semua service berjalan."
echo ""
echo "────────────────────────────────────────"
echo "  Chatbot KJRI Dubai siap!"
echo ""
echo "  ADK Agent  : http://localhost:8000"
echo "  pgAdmin    : http://localhost:5050"
echo "  Ollama     : http://localhost:11434"
echo "────────────────────────────────────────"
echo ""
info "Cek status service: docker compose ps"
info "Lihat logs agent : docker compose logs -f agent"
