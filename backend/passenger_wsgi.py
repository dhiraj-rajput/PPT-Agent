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

from server import app as fastapi_app

# Convert FastAPI (ASGI) to Passenger (WSGI) via a2wsgi if installed,
# otherwise export raw ASGI application for Passenger 6+ native ASGI support.
try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(fastapi_app)  # type: ignore[arg-type]
except ImportError:
    application = fastapi_app
