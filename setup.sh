#!/usr/bin/env bash
# Job Bot — Kurulum & Calistirma (WSL2 Ubuntu 24.04)
set -e
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$BOT_DIR/.venv"

echo "================================================"
echo "  JOB_BOT Kurulum"
echo "================================================"

python3 -c "import sys; assert (3,10) <= sys.version_info[:2] < (3,13)" 2>/dev/null \
    || { echo "❌ Python 3.10-3.12 gerekli"; exit 1; }

[ ! -d "$VENV_DIR" ] && { echo "🔧 venv olusturuluyor..."; python3 -m venv "$VENV_DIR"; }
source "$VENV_DIR/bin/activate"
echo "📦 Bagimliliklar yukleniyor..."
pip install --quiet --upgrade pip
pip install --quiet -r "$BOT_DIR/requirements.txt"
mkdir -p "$HOME/.job_bot"

if [ ! -f "$BOT_DIR/.env" ]; then
    cp "$BOT_DIR/.env.example" "$BOT_DIR/.env"
    echo "🧩 .env olusturuldu. Telegram bildirimi istiyorsan bu dosyayi doldur."
fi

if ! find "$BOT_DIR/profiles" -maxdepth 1 -name "*.yaml" ! -name "example.yaml" | grep -q .; then
    cp "$BOT_DIR/profiles/example.yaml" "$BOT_DIR/profiles/ben.yaml"
    echo "🧩 profiles/ben.yaml olusturuldu. Kendi arama terimlerinle duzenle."
fi

echo ""
echo "✅ Kurulum tamam!"
echo ""
echo "▶  Baslat:   source $VENV_DIR/bin/activate && python $BOT_DIR/run.py"
echo "▶  Dashboard: http://localhost:8765"
echo ""
read -p "Simdi baslatilsin mi? [E/h]: " -n 1 -r; echo
if [[ $REPLY =~ ^[Ee]$ ]] || [[ -z $REPLY ]]; then
    python "$BOT_DIR/run.py"
fi
