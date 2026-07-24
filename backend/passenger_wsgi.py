"""
passenger_wsgi.py
------------------
cPanel Phusion Passenger WSGI entry point for OrbitAvanya FastAPI backend.

This file bridges the FastAPI ASGI application (`app` in server.py) with cPanel's
Phusion Passenger WSGI interface.
"""

import sys
import os

# Ensure backend root directory is in sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Attempt to include virtualenv site-packages if present under backend or home
for venv_path in [
    os.path.join(os.path.dirname(__file__), ".venv", "lib", f"python3.{sys.version_info.minor}", "site-packages"),
    os.path.expanduser(f"~/virtualenv/backend/3.{sys.version_info.minor}/lib/python3.{sys.version_info.minor}/site-packages"),
]:
    if os.path.exists(venv_path) and venv_path not in sys.path:
        sys.path.insert(0, venv_path)

from server import app as fastapi_app

# Convert FastAPI (ASGI) to Passenger (WSGI) via a2wsgi
try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(fastapi_app)  # type: ignore[arg-type]
except ImportError as err:
    import logging
    logging.error(f"[passenger_wsgi] Failed to import a2wsgi: {err}")
    raise RuntimeError(
        "Missing required dependency 'a2wsgi'. Please run 'pip install a2wsgi' in your cPanel Python environment."
    ) from err

