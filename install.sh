#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo ""
echo "  ┌──────────────────────────────────────────────┐"
echo "  │           NutriTracker Installer              │"
echo "  │   Private food tracking with AI analysis      │"
echo "  └──────────────────────────────────────────────┘"
echo ""

# Check for Python 3
if ! command -v python3 &>/dev/null; then
    echo "  [!] Python 3 not found."
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "  Install with: brew install python3"
    else
        echo "  Install with: sudo apt install python3 python3-venv python3-pip"
    fi
    exit 1
fi

echo "  [OK] Python found: $(python3 --version)"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "  [*] Creating virtual environment..."
    python3 -m venv venv
    echo "  [OK] Virtual environment created."
else
    echo "  [OK] Virtual environment exists."
fi

# Activate and install
echo "  [*] Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet

# Generate icons if missing
if [ ! -f "frontend/assets/icons/icon-192.png" ]; then
    echo "  [*] Generating app icons..."
    pip install Pillow --quiet 2>/dev/null || true
    python generate_icons.py 2>/dev/null || echo "  [SKIP] Icon generation skipped."
fi

# Initialize database
echo "  [*] Initializing database..."
python -c "from backend.database import init_db; init_db(); print('  [OK] Database ready.')"

echo ""
echo "  ┌──────────────────────────────────────────────┐"
echo "  │           Installation Complete!              │"
echo "  │                                               │"
echo "  │   Run ./start.sh to launch the server.        │"
echo "  │   Then open the URL on your phone.            │"
echo "  └──────────────────────────────────────────────┘"
echo ""
