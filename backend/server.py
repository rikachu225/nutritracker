"""
NutriTracker Server Entry Point
================================
Starts the Flask app with waitress (production WSGI server).
Binds to 0.0.0.0 so the app is accessible from any device on the local network.
"""

import sys
import json
import socket
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import app
from backend import database as db

DEFAULT_PORT = 8888
CONFIG_PATH = PROJECT_ROOT / "data" / "config.json"


def get_local_ip():
    """Get the machine's local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def load_config():
    """Load or create config file."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(config):
    """Save config to file."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def main():
    # Initialize database
    db.init_db()

    # Load config
    config = load_config()
    port = config.get('port', DEFAULT_PORT)

    # Allow port override via command line
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    # Save port to config
    config['port'] = port
    save_config(config)

    local_ip = get_local_ip()
    app_name = db.get_setting('app_name', 'NutriTracker')

    # Force UTF-8 output on Windows
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    try:
        print()
        print("  ┌──────────────────────────────────────────────────────┐")
        print(f"  │  {app_name:^52} │")
        print("  │                                                      │")
        print(f"  │  Local:    http://localhost:{port:<24} │")
        print(f"  │  Network:  http://{local_ip}:{port:<22} │")
        print("  │                                                      │")
        print("  │  Open the network URL on your phone to get started.  │")
        print("  │  Press Ctrl+C to stop the server.                    │")
        print("  └──────────────────────────────────────────────────────┘")
        print()
    except UnicodeEncodeError:
        # Fallback for terminals that can't render box-drawing chars
        print()
        print(f"  {app_name}")
        print(f"  Local:   http://localhost:{port}")
        print(f"  Network: http://{local_ip}:{port}")
        print(f"  Open the network URL on your phone to get started.")
        print(f"  Press Ctrl+C to stop the server.")
        print()

    from waitress import serve
    serve(app, host='0.0.0.0', port=port, threads=4)


if __name__ == '__main__':
    main()
