#!/usr/bin/env bash
# Job Bot — Kurulum & Calistirma (WSL2 Ubuntu 24.04)
set -e
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$BOT_DIR/.venv"

echo "================================================"
echo "  JOB_BOT Kurulum"
echo "================================================"

python3 -c "import sys; assert sys.version_info >= (3,10)" 2>/dev/null \
    || { echo "❌ Python 3.10+ gerekli"; exit 1; }

if grep -q "BURAYA" "$BOT_DIR/config.yaml"; then
    echo ""
    echo "⚠️  ONCE config.yaml doldur:"
    echo "   telegram.bot_token  -> @BotFather > /newbot"
    echo "   telegram.chat_id    -> @userinfobot"
    echo ""
    echo "   Sonra ./setup.sh tekrar calistir."
    exit 1
fi

[ ! -d "$VENV_DIR" ] && { echo "🔧 venv olusturuluyor..."; python3 -m venv "$VENV_DIR"; }
source "$VENV_DIR/bin/activate"
echo "📦 Bagimliliklar yukleniyor..."
pip install --quiet --upgrade pip
pip install --quiet -r "$BOT_DIR/requirements.txt"
mkdir -p "$HOME/.job_bot"

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
