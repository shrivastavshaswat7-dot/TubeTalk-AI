"""Make the frontend modules (app.py's siblings) importable from the tests."""
import os
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[1]
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

# The app refuses to start without a backend address; tests never reach it (api_client is patched).
os.environ.setdefault("API_BASE_URL", "http://backend.test")
