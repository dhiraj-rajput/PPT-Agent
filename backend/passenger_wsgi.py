"""
passenger_wsgi.py
------------------
cPanel Phusion Passenger / LiteSpeed WSGI entry point for OrbitAvanya FastAPI backend.

Provides a thread-safe WSGI adapter for FastAPI on LiteSpeed/Passenger.
"""

import asyncio
import os
import sys

# Ensure backend root directory is in sys.path
sys.path.insert(0, os.path.dirname(__file__))

# Attempt to include virtualenv site-packages if present
for venv_path in [
    os.path.join(os.path.dirname(__file__), ".venv", "lib", f"python3.{sys.version_info.minor}", "site-packages"),
    os.path.expanduser(f"~/virtualenv/backend/3.{sys.version_info.minor}/lib/python3.{sys.version_info.minor}/site-packages"),
]:
    if os.path.exists(venv_path) and venv_path not in sys.path:
        sys.path.insert(0, venv_path)

from server import app as fastapi_app

# Try a2wsgi with explicit sync loop runner, fallback to native asyncio execution
try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(fastapi_app)  # type: ignore

except Exception as err:
    import logging
    logging.getLogger("passenger_wsgi").warning(
        "a2wsgi is not installed; falling back to native asyncio WSGI adapter. "
        "For optimal production performance under Phusion Passenger, install a2wsgi: pip install a2wsgi. Error: %s", err
    )
    def application(environ, start_response):
        """Native lightweight WSGI-to-ASGI converter for LiteSpeed pre-fork mode."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        path_info = environ.get('PATH_INFO', '/')
        script_name = environ.get('SCRIPT_NAME', '')

        scope = {
            'type': 'http',
            'asgi': {'version': '3.0', 'spec_version': '2.0'},
            'http_version': environ.get('SERVER_PROTOCOL', 'HTTP/1.1').split('/')[-1],
            'method': environ.get('REQUEST_METHOD', 'GET'),
            'scheme': environ.get('wsgi.url_scheme', 'http'),
            'path': path_info,
            'raw_path': path_info.encode('latin1'),
            'query_string': environ.get('QUERY_STRING', '').encode('latin1'),
            'root_path': script_name,
            'headers': [
                (k[5:].lower().replace('_', '-').encode('latin1'), v.encode('latin1'))
                for k, v in environ.items() if k.startswith('HTTP_')
            ],
            'client': (environ.get('REMOTE_ADDR', '127.0.0.1'), int(environ.get('REMOTE_PORT', 0) or 0)),
            'server': (environ.get('SERVER_NAME', 'localhost'), int(environ.get('SERVER_PORT', 80) or 80)),
        }

        if environ.get('CONTENT_TYPE'):
            scope['headers'].append((b'content-type', environ['CONTENT_TYPE'].encode('latin1')))
        if environ.get('CONTENT_LENGTH'):
            scope['headers'].append((b'content-length', environ['CONTENT_LENGTH'].encode('latin1')))

        body_bytes = b''
        if 'wsgi.input' in environ:
            try:
                content_len = int(environ.get('CONTENT_LENGTH', 0) or 0)
                if content_len > 0:
                    body_bytes = environ['wsgi.input'].read(content_len)
            except Exception:
                pass

        response_status = 200
        response_headers = []
        response_body = []

        async def receive():
            nonlocal body_bytes
            data = body_bytes
            body_bytes = b''
            return {'type': 'http.request', 'body': data, 'more_body': False}

        async def send(message):
            nonlocal response_status, response_headers
            if message['type'] == 'http.response.start':
                response_status = message['status']
                response_headers = [
                    (name.decode('latin1'), value.decode('latin1'))
                    for name, value in message.get('headers', [])
                ]
            elif message['type'] == 'http.response.body':
                body = message.get('body', b'')
                if body:
                    response_body.append(body)

        try:
            loop.run_until_complete(fastapi_app(scope, receive, send))
            reason = "OK" if response_status == 200 else ""
            start_response(f"{response_status} {reason}".strip(), response_headers)
            return response_body
        finally:
            loop.close()


