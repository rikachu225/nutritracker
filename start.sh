#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "  [ERROR] Virtual environment not found. Run ./install.sh first."
    exit 1
fi

source venv/bin/activate
python -m backend.server "$@"
