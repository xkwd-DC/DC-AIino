#!/usr/bin/env python3
"""Localhost static server with HTTP Basic Auth for the DC project cockpit.

Reads the expected password from a sibling .dash_pass file (chmod 600).
Binds to 127.0.0.1 only; public reach is via the cloudflared tunnel in front.
"""
import base64
import hmac
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
USER = os.environ.get("DASH_USER", "darcy")

with open(os.path.join(DIRECTORY, ".dash_pass"), encoding="utf-8") as fh:
    PASSWORD = fh.read().strip()

EXPECTED = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()


class AuthHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def _authorized(self):
        header = self.headers.get("Authorization", "")
        # constant-time compare to avoid leaking match progress via timing
        return hmac.compare_digest(header, EXPECTED)

    def _challenge(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="DC Cockpit"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._authorized():
            self._challenge()
            return
        super().do_GET()

    def do_HEAD(self):
        if not self._authorized():
            self._challenge()
            return
        super().do_HEAD()

    def log_message(self, *args):  # silence per-request logging
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
    HTTPServer(("127.0.0.1", port), AuthHandler).serve_forever()
