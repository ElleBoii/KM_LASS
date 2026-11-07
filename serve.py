"""Testkör sidan lokalt.

Kör:  python serve.py   och öppna http://localhost:8000
Sidan läser mappen data, som skapas av lenex_extract.py.
"""
import functools
import http.server
from pathlib import Path

PORT = 8000
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(Path(__file__).parent))
print(f"Öppna http://localhost:{PORT}  (Ctrl+C för att avsluta)")
http.server.ThreadingHTTPServer(("", PORT), handler).serve_forever()
